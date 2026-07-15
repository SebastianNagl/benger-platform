"""LLM generation Celery-task implementations (worker).

Originally extracted from ``services/workers/tasks.py`` as part of the
structural decomposition of that module. The extraction was a behavior-preserving
move (references to ``tasks``-module globals like ``SessionLocal``, ``logger``,
and monkeypatched helpers are resolved through the ``tasks`` module at call time
so test patches like ``patch("tasks.SessionLocal")`` still apply).

NOTE: the multi-run finalization in ``generate_llm_responses_impl`` is NO LONGER
a byte-identical move — its status derivation was rewritten from the old
incrementing-counter scheme to a derived ``COUNT(DISTINCT run_index)`` cascade
(user-terminal → completion → first-failure latch), with a guarded start-of-trial
status set, an epoch-aware dispatch, and gated completion side effects. That block
is the most intricate concurrency logic here and should be reviewed as new code,
not as an extraction.

The public, decorated Celery task wrappers (with their original names, task
names, and decorator args) remain in ``tasks.py`` and delegate here.
"""

import re

import tasks
from typing import Any, Dict


def _check_custom_model_access(db, user_id: str, model) -> bool:
    """Worker-side re-check that the invoking user can still use a custom
    (BYOM) model. Enqueue-time already 403s new runs; this catches
    mid-run revocation (share removed / model privatized) — remaining
    task cells fail cleanly instead of running against a model the user
    no longer has access to."""
    if model.is_public:
        return True
    if model.created_by and str(model.created_by) == str(user_id):
        return True

    from models import ModelOrganization, OrganizationMembership, User

    user = db.query(User).filter(User.id == user_id).first()
    if user and getattr(user, "is_superadmin", False):
        return True

    model_org_ids = {
        row[0]
        for row in db.query(ModelOrganization.organization_id)
        .filter(ModelOrganization.model_id == model.id)
        .all()
    }
    if not model_org_ids:
        return False
    memberships = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active.is_(True),
        )
        .all()
    )
    return any(m.organization_id in model_org_ids for m in memberships)

def generate_response_impl(
    generation_id: str,
    project_id: str,
    task_id: str,
    model_id: str,
    structure_key: str = None,
    force_rerun: bool = False,
    organization_id: str = None,
    run_index: int = 0,
) -> Dict[str, Any]:
    """
    Generate response for a specific task-model combination.
    Bridge task for the new generation pipeline that matches the API call signature.

    Args:
        generation_id: Unique identifier for this generation run
        project_id: ID of the project
        task_id: ID of the specific task
        model_id: ID of the model to use for generation
        structure_key: Optional prompt structure key (Issue #762)
        force_rerun: If True, regenerate even if response already exists
        organization_id: Optional org context for API key resolution (Issue #1180)
        run_index: Zero-indexed trial number within the parent ResponseGeneration's
            fan-out (migration 041). One Celery task per run_index; the parent
            ResponseGeneration aggregates progress via runs_completed/runs_failed.

    Returns:
        Dictionary with generation results
    """
    structure_info = f" with structure '{structure_key}'" if structure_key else ""
    tasks.logger.info(
        f"🎯 Starting generation for task {task_id} with model {model_id}{structure_info} (run {run_index})"
    )

    try:
        # Import modules
        from datetime import datetime

        from models import ResponseGeneration as DBResponseGeneration

        # Import Task from project_models to avoid table conflict
        from project_models import Task

        # Check database availability
        if not tasks.HAS_DATABASE:
            raise Exception("Database not available - check database connection")

        # Create database session
        db = tasks.SessionLocal()

        try:
            # Get the generation record
            generation = (
                db.query(DBResponseGeneration)
                .filter(DBResponseGeneration.id == generation_id)
                .first()
            )

            if not generation:
                raise Exception(f"Generation {generation_id} not found")

            # Guard against duplicate execution (e.g., Celery message
            # redelivery) AND honor a stop/supersede/pause: ``stopped`` (stop),
            # ``cancelled`` (supersede), and ``paused`` (pause) are all terminal
            # for THIS dispatch, so a queued trial self-aborts here even if the
            # in-memory Celery revoke was lost (worker recycle / pod restart).
            # This makes the DB status the reliable backstop that stops
            # API-budget burn. (Resume flips status back to "running" before it
            # re-dispatches, so a resumed run is NOT skipped here.)
            if generation.status in ("completed", "cancelled", "stopped", "paused"):
                tasks.logger.info(
                    f"⏭️ Skipping generation {generation_id} - already {generation.status}"
                )
                return {
                    "status": generation.status,
                    "generation_id": generation_id,
                    "model_id": model_id,
                    "message": f"Generation already {generation.status}, skipping duplicate execution",
                }

            # Note: status="running" is set by generate_llm_responses (line 575)
            # which is also callable as a standalone Celery task

            # Get the task
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise Exception(f"Task {task_id} not found")

            # Get the project
            from project_models import Project

            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise Exception(f"Project {project_id} not found")

            # Build config_data for generate_llm_responses
            # Note: prompts and parameters are resolved from project.generation_config
            # and generation_structure inside generate_llm_responses, not from config_data
            config_data = {
                "project_id": project_id,
                "force_rerun": force_rerun,
            }

            # Get user ID from generation record
            user_id = generation.created_by

            # Call generate_llm_responses directly (not via Celery)
            # It uses its own DB session and commits all changes (status,
            # error_message, prompt_used, parameters) to the generation record.
            result = tasks.generate_llm_responses(
                generation_id, config_data, model_id, user_id, structure_key, organization_id,
                run_index=run_index,
            )

            # Refresh to pick up all changes committed by generate_llm_responses
            # (which uses a separate DB session)
            db.refresh(generation)

            tasks.logger.info(
                f"✅ Completed generation for task {task_id} with status: {generation.status}"
            )
            return result

        finally:
            db.close()

    except Exception as e:
        tasks.logger.error(f"❌ Error in generate_response: {str(e)}")

        # Try to update generation status. For multi-run we also bump the
        # runs_failed counter (migration 041) so the parent's aggregate matches
        # reality even when the trial died before generate_llm_responses ran.
        try:
            from sqlalchemy import text as _sql_text

            db = tasks.SessionLocal()
            db.execute(
                _sql_text(
                    "UPDATE response_generations SET runs_failed = runs_failed + 1 "
                    "WHERE id = :gid"
                ),
                {"gid": generation_id},
            )
            generation = (
                db.query(DBResponseGeneration)
                .filter(DBResponseGeneration.id == generation_id)
                .first()
            )
            # Don't relabel a terminal stop/supersede/pause as "failed" — if the
            # trial errored because it was SIGTERM'd by one of those, leave the
            # user-facing status intact.
            if generation and generation.status not in (
                "completed", "cancelled", "stopped", "paused"
            ):
                generation.status = "failed"
                generation.error_message = str(e)
                generation.completed_at = datetime.now()
                db.commit()
            db.close()
        except Exception as db_error:
            tasks.logger.error(f"❌ Failed to update generation status: {str(db_error)}")

        return {
            "status": "error",
            "message": f"Generation failed: {str(e)}",
            "generation_id": generation_id,
        }


def generate_llm_responses_impl(
    generation_id: str,
    config_data: dict,
    model_id: str,
    user_id: str,
    structure_key: str = None,
    organization_id: str = None,
    run_index: int = 0,
) -> Dict[str, Any]:
    """
    Generate LLM responses asynchronously using Celery

    Args:
        generation_id: Unique identifier for this generation run
        config_data: Task evaluation configuration data
        model_id: ID of the model to use for generation
        user_id: ID of the user who initiated the generation (for API key lookup)
        structure_key: Key for prompt structure in generation_config.prompt_structures (Issue #762)
        organization_id: Optional org context for API key resolution (Issue #1180)
        run_index: Multi-run trial index (migration 041). Stamped on the
            child Generation row; the parent ResponseGeneration aggregates
            via runs_completed/runs_failed counters bumped at the end of
            this function.

    Returns:
        Dictionary with generation results
    """
    tasks.logger.info(f"🚀 Starting real LLM generation for model {model_id}, generation {generation_id}")

    try:
        # Import additional modules needed for generation
        import asyncio
        import json
        import uuid
        from datetime import datetime

        # Check if database is available
        if not tasks.HAS_DATABASE:
            raise Exception("Database not available - check database connection")

        # Create database session
        db = tasks.SessionLocal()

        try:
            # Get generation record
            generation = (
                db.query(tasks.DBResponseGeneration)
                .filter(tasks.DBResponseGeneration.id == generation_id)
                .first()
            )
            if not generation:
                raise Exception(f"Generation record {generation_id} not found")

            # Skip if the generation was already stopped (stop), cancelled (a new
            # "all" mode run superseded it), or paused before we start — the DB
            # status is the backstop when the in-memory Celery revoke was lost
            # (worker recycle / pod restart). Resume flips status back to
            # "running" before re-dispatching, so a resumed run is not skipped.
            if generation.status in ("cancelled", "stopped", "paused"):
                tasks.logger.info(
                    f"⏭️ Skipping {generation.status} generation {generation_id}"
                )
                return {
                    "status": "skipped",
                    "generation_id": generation_id,
                    "model_id": model_id,
                    "message": f"Generation was {generation.status} before processing",
                }

            # Store structure_key if provided (Issue #762)
            if structure_key:
                generation.structure_key = structure_key
                tasks.logger.info(f"🔑 Using prompt structure: {structure_key}")

            # Mark in-progress — but DON'T clobber a terminal status a sibling
            # trial already set. In a multi-run fan-out a trial can START after a
            # sibling already finalized "failed" (first-failure latch) or
            # "completed"; blindly resetting to "running" here would un-latch it
            # before this trial's own finalizer runs, stranding the parent in
            # "running" forever (a failed trial's run_index never gets a child, so
            # COUNT can't reach runs_requested). Only a pending/running parent
            # advances. resume/retry reset the parent to "running" up front, so a
            # deliberate re-run still proceeds. (cancelled/stopped/paused already
            # returned above.)
            if generation.status in ("pending", "running"):
                generation.status = "running"
                generation.started_at = datetime.now()
                db.commit()

            tasks.logger.info(f"🤖 Starting real LLM generation for model {model_id}")

            # Get project details first
            from project_models import Project

            project_id = config_data.get(
                "project_id", config_data.get("task_id")
            )  # Support both keys for compatibility
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise Exception(f"Project {project_id} not found")

            # Issue #762: Fetch prompt structure from generation_config if structure_key provided
            generation_structure = None
            if structure_key and project.generation_config:
                prompt_structures = project.generation_config.get("prompt_structures", [])
                # Handle both list format (new) and dict format (legacy)
                if isinstance(prompt_structures, list):
                    # List format: find structure by key or numeric index
                    # First try to find by key
                    for ps in prompt_structures:
                        if ps.get("key") == structure_key:
                            generation_structure = ps.get("structure", ps)
                            tasks.logger.info(
                                f"✅ Loaded prompt structure '{structure_key}' from generation_config (list format)"
                            )
                            break
                    # If not found by key, try numeric index
                    if not generation_structure:
                        try:
                            idx = int(structure_key)
                            if 0 <= idx < len(prompt_structures):
                                ps = prompt_structures[idx]
                                generation_structure = ps.get("structure", ps)
                                tasks.logger.info(
                                    f"✅ Loaded prompt structure at index {idx} from generation_config (list format)"
                                )
                        except (ValueError, TypeError):
                            pass
                    if not generation_structure:
                        available_keys = [
                            ps.get("key", str(i)) for i, ps in enumerate(prompt_structures)
                        ]
                        raise Exception(
                            f"Prompt structure '{structure_key}' not found in project generation_config. "
                            f"Available structures: {available_keys}"
                        )
                elif isinstance(prompt_structures, dict):
                    # Legacy dict format
                    if structure_key in prompt_structures:
                        generation_structure = prompt_structures[structure_key]
                        tasks.logger.info(
                            f"✅ Loaded prompt structure '{structure_key}' from generation_config (dict format)"
                        )
                    else:
                        raise Exception(
                            f"Prompt structure '{structure_key}' not found in project generation_config. "
                            f"Available structures: {list(prompt_structures.keys())}"
                        )

            # Default prompts (overridden by generation_structure if configured)
            # Note: DefaultConfigService removed in Issue #759, using hardcoded defaults
            system_prompt = "Sie sind ein erfahrener Jurist mit Expertise im deutschen Zivilrecht und Arbeitsrecht. Analysieren Sie rechtliche Sachverhalte präzise und fundiert."
            instruction_prompt_text = "Beantworten Sie die Frage mit 'Ja' oder 'Nein' und geben Sie anschließend eine ausführliche rechtliche Begründung. Format: Antwort: <Ja/Nein> Begründung: <ausführliche Begründung>"

            # Create instruction_prompts list for iteration (single default prompt)
            instruction_prompts = [
                {
                    "id": "default_instruction",
                    "prompt_text": instruction_prompt_text,
                    "prompt_name": "Default Legal Analysis",
                }
            ]

            # Get task data directly from database
            # Issue #762: Use the specific task_id from generation record, not all project tasks
            try:
                from project_models import Task as ProjectTask

                # Query only the specific task for this generation
                task_id = generation.task_id
                task = (
                    db.query(ProjectTask)
                    .filter(ProjectTask.id == task_id, ProjectTask.project_id == project_id)
                    .first()
                )

                if not task:
                    raise Exception(f"Task {task_id} not found in project {project_id}")

                # Convert to dictionary format expected by generation code
                tasks_data = [
                    {
                        "id": task.id,
                        "project_id": task.project_id,
                        "data": task.data,  # JSONB field containing task data
                        "meta": task.meta,
                        "created_at": task.created_at.isoformat() if task.created_at else None,
                    }
                ]

            except Exception as e:
                tasks.logger.error(f"Error loading task data from database: {e}")
                raise Exception(f"Failed to load task data from database: {str(e)}")

            if not tasks_data:
                raise Exception("No task data found in native annotation system")

            # Get model info
            model = db.query(tasks.DBLLMModel).filter(tasks.DBLLMModel.id == model_id).first()
            if not model:
                raise Exception(f"Model {model_id} not found")

            # BYOM: re-check access + liveness for custom models (mid-run
            # revocation guard — see _check_custom_model_access).
            if not getattr(model, "is_official", True):
                if not model.is_active:
                    raise Exception(
                        f"Model access revoked: custom model '{model.name}' has been deleted"
                    )
                if not _check_custom_model_access(db, user_id, model):
                    raise Exception(
                        f"Model access revoked: you no longer have access to custom model '{model.name}'"
                    )

            # Check if AI services are available
            if not tasks.HAS_AI_SERVICES:
                raise Exception("AI services not available - check service imports")

            # Initialize user-aware AI service. BYOM-aware: official rows
            # resolve by provider + user/org key, custom rows by the model
            # row + the invoking user's per-model credential.
            try:
                ai_service = tasks.user_aware_ai_service.get_ai_service_for_model_row(
                    db, user_id, model, organization_id=organization_id
                )
                # Read the actual resolution route off the service so the log
                # reflects which key path the resolver took, not just whether
                # an org_id was passed (issue #82).
                route = (
                    getattr(ai_service, "_key_resolution_route", "user_key")
                    if ai_service
                    else "unresolved"
                )
                tasks.logger.info(
                    f"Using API key via {route} "
                    f"(org_context={organization_id}, user={user_id}) for {model.provider}"
                )
            except Exception as e:
                error_msg = str(e)
                if (
                    "no API key configured" in error_msg.lower()
                    or "api key not found" in error_msg.lower()
                ):
                    tasks.logger.error(f"❌ User {user_id} has no API key configured for {model.provider}")
                    raise Exception(
                        f"API key required: User must configure {model.provider} API key in profile settings to use this model"
                    )
                else:
                    tasks.logger.error(
                        f"❌ Failed to get user-aware AI service for user {user_id}, provider {model.provider}: {e}"
                    )
                    # Security fix: No fallback to global API keys - user must configure their own keys
                    raise Exception(
                        f"API key error: Unable to initialize {model.provider} service for user {user_id}. "
                        f"Please check your API key configuration in profile settings. Error: {error_msg}"
                    )

            if ai_service is None:
                if not getattr(model, "is_official", True):
                    # Custom model: the missing piece is a per-model
                    # credential, not a provider key ("API key required"
                    # prefix keeps the error classifier matching).
                    raise Exception(
                        f"API key required: no credential stored for custom model "
                        f"'{model.name}'. Add your key for this model under "
                        f"Settings → My models before generating."
                    )
                key_context = "organization settings" if organization_id else "profile settings"
                raise Exception(
                    f"No {model.provider} API key configured. Please add your API key in {key_context} to use this model."
                )

            if not ai_service.is_available():
                raise Exception(
                    f"AI service for {model.provider} is not available - check API key configuration"
                )

            # Use model.id for API calls - it contains the actual API identifier
            # model.id = API model name (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            # model.name = display name (e.g., "GPT-4o", "Claude 3.5 Sonnet")
            # BYOM exception: a custom row's PK is a generated "custom-<uuid>"
            # that means nothing to the remote server — endpoint_model_name
            # carries the real API model string.
            if not getattr(model, "is_official", True) and model.endpoint_model_name:
                api_model_name = model.endpoint_model_name
            else:
                api_model_name = model.id

            responses_generated = 0
            total_expected = len(tasks_data) * len(instruction_prompts)

            tasks.logger.info(
                f"🎯 Expected to generate: {total_expected} responses ({len(tasks_data)} tasks × {len(instruction_prompts)} prompts)"
            )

            # Rate limiting configuration (Issue #482)
            import time

            # Rate limits per provider (requests per minute)
            RATE_LIMITS = {
                "OpenAI": 60,  # 60 requests per minute for GPT models
                "Anthropic": 50,  # 50 requests per minute for Claude
                "Google": 60,  # 60 requests per minute for Gemini
                "DeepInfra": 100,  # Higher limit for open models
                "Meta": 100,  # Same as DeepInfra
                "Grok": 60,  # xAI
                "Mistral": 60,  # Mistral AI
                "Cohere": 100,  # Cohere - higher limit
                "Custom": 60,  # BYOM endpoints - conservative default
            }

            # Get rate limit for this provider
            provider_rate_limit = RATE_LIMITS.get(model.provider, 60)

            # Calculate minimum delay between requests (in seconds)
            min_delay = 60.0 / provider_rate_limit

            # Allow configuration override from config_data
            if "rate_limit_delay" in config_data:
                min_delay = config_data["rate_limit_delay"]

            tasks.logger.info(
                f"⏱️ Rate limiting: {provider_rate_limit} req/min, {min_delay:.2f}s delay between requests"
            )

            last_request_time = 0

            # Capture prompt templates for provenance
            # Use the generation_structure (what the user configures) as source of truth
            if generation_structure:
                # Extract template string from structure fields
                # Fields can be either a dict with "template" key or a plain string
                sys_field = generation_structure.get("system_prompt")
                instr_field = generation_structure.get("instruction_prompt")
                _captured_prompt_templates = {
                    "system_prompt": sys_field.get("template", system_prompt) if isinstance(sys_field, dict) else (sys_field or system_prompt),
                    "instruction_prompt": instr_field.get("template", instruction_prompt_text) if isinstance(instr_field, dict) else (instr_field or instruction_prompt_text),
                }
            else:
                _captured_prompt_templates = {
                    "system_prompt": system_prompt,
                    "instruction_prompt": instruction_prompt_text,
                }
            _captured_prompt_json = json.dumps(
                _captured_prompt_templates, ensure_ascii=False, sort_keys=True
            )
            _captured_parameters = None
            _last_error = None
            from sqlalchemy import text as _sql_text

            # Cooperative cancel (issue #198): set when the parent status flips
            # to a terminal stop/supersede/pause WHILE an LLM call is in flight.
            # When set we skip persisting the in-flight response, bail the loop,
            # and skip the trial counter-bump (the trial was cancelled, not
            # completed or failed). Complements the up-front skip + the Celery
            # revoke + the post-loop status guard.
            _aborted = False
            # Set when this run_index's child already exists (a surviving prior
            # trial wrote it in the race window after revoke). The trial is a
            # no-op, NOT a failure — skip the counter bump so the parent isn't
            # falsely flipped to "failed" and runs_failed isn't over-counted.
            _duplicate_skip = False
            from sqlalchemy.exc import IntegrityError as _IntegrityError

            # Generate responses for each task and prompt combination.
            for task_data in tasks_data:
                task_content = task_data.get("data", {})

                for instruction_prompt in instruction_prompts:
                    try:
                        # Handle both database objects and dict objects
                        if hasattr(instruction_prompt, "id"):
                            # Database object
                            prompt_id = instruction_prompt.id
                            prompt_text = instruction_prompt.prompt_text
                            prompt_name = instruction_prompt.prompt_name
                        else:
                            # Dict object (fallback)
                            prompt_id = instruction_prompt["id"]
                            prompt_text = instruction_prompt["prompt_text"]
                            prompt_name = instruction_prompt["prompt_name"]

                        # Check if response already exists (unless force_rerun is True)
                        force_rerun = config_data.get("force_rerun", False)

                        if not force_rerun:
                            # Check for existing completed response with prompt provenance
                            # Single query: join to get both response and stored prompt
                            existing = (
                                db.query(
                                    tasks.DBLLMResponse.id,
                                    tasks.DBResponseGeneration.prompt_used,
                                )
                                .join(
                                    tasks.DBResponseGeneration,
                                    tasks.DBLLMResponse.generation_id == tasks.DBResponseGeneration.id,
                                )
                                .filter(
                                    tasks.DBLLMResponse.task_id == task_data["id"],
                                    tasks.DBLLMResponse.model_id == model_id,
                                    tasks.DBResponseGeneration.structure_key == structure_key,
                                    # run_index-aware: a multi-run gen has one
                                    # completed child PER run_index. Without this
                                    # a missing-mode trial N>0 would skip on
                                    # run_index 0's row (so a runs_requested=N
                                    # missing-mode trigger generated only 1
                                    # trial). It also dedups a surviving prior
                                    # trial before re-dispatch (resume/retry).
                                    tasks.DBLLMResponse.run_index == run_index,
                                    tasks.DBLLMResponse.status == "completed",
                                )
                                .order_by(tasks.DBLLMResponse.created_at.desc())
                                .first()
                            )

                            if existing:
                                _, stored_prompt = existing
                                if stored_prompt is None or stored_prompt == _captured_prompt_json:
                                    tasks.logger.info(
                                        f"⏭️ Skipping existing response for task {task_data['id']}, "
                                        f"prompt {'unchanged' if stored_prompt else 'legacy'}"
                                    )
                                    continue
                                else:
                                    tasks.logger.info(
                                        f"🔄 Prompt changed for task {task_data['id']}, regenerating"
                                    )
                        else:
                            tasks.logger.info(
                                f"🔄 Force regenerating response for task {task_data['id']}, prompt {prompt_id}"
                            )

                        # Prepare the prompt - use safe field interpolation if enabled (Issue #507)
                        user_prompt = prompt_text

                        # Use safe generation structure parsing if available (Issue #507, #519, #762)
                        if tasks.HAS_GENERATION_PARSER and generation_structure:
                            tasks.logger.info(
                                f"🔒 Using generation structure '{structure_key}' for task {task_data['id']}"
                            )
                            try:
                                parser = tasks.GenerationStructureParser()
                                # Process the generation structure to filter task data
                                # V2 returns (prompts_dict, filtered_data)
                                prompts, filtered_data = parser.process_generation_structure(
                                    task_data=task_content,
                                    generation_structure=generation_structure,
                                    fallback_instruction=prompt_text,
                                )

                                # Use generated prompts if available
                                if 'system_prompt' in prompts:
                                    system_prompt = prompts['system_prompt']
                                    tasks.logger.info(
                                        f"✅ Using structured system prompt for task {task_data['id']}"
                                    )

                                if 'instruction_prompt' in prompts:
                                    user_prompt = prompts['instruction_prompt']
                                    tasks.logger.info(
                                        f"✅ Applied generation structure '{structure_key}' for task {task_data['id']}"
                                    )
                                else:
                                    # Fallback to original prompt if no instruction generated
                                    user_prompt = prompt_text
                                    tasks.logger.info(
                                        f"⚠️ No instruction prompt generated, using fallback for task {task_data['id']}"
                                    )

                            except Exception as e:
                                tasks.logger.error(
                                    f"Error applying generation structure '{structure_key}': {e}"
                                )
                                # Fall back to original behavior on error
                                for key, value in task_content.items():
                                    placeholder = f"{{{key}}}"
                                    if placeholder in user_prompt:
                                        user_prompt = user_prompt.replace(placeholder, str(value))
                        else:
                            # Original behavior - simple interpolation
                            for key, value in task_content.items():
                                placeholder = f"{{{key}}}"
                                if placeholder in user_prompt:
                                    user_prompt = user_prompt.replace(placeholder, str(value))

                        tasks.logger.info(
                            f"🎯 Generating response for task {task_data['id']}, model {model_id}, prompt {prompt_id}"
                        )

                        # Extract generation config for this model from PROJECT (not config_data)
                        # project.generation_config.selected_configuration.model_configs
                        project_gen_config = project.generation_config or {}
                        selected_config_for_model = project_gen_config.get(
                            "selected_configuration", {}
                        )
                        model_config = selected_config_for_model.get("model_configs", {}).get(
                            model_id, {}
                        )

                        # Tiered parameter resolution via the shared
                        # `_resolve_param` helper (see top of this file).
                        # Returns (value, source_tag, recommended_at_trigger)
                        # per key so the provenance snapshot below can record
                        # what the recommended value was at trigger time even
                        # when a user override won — making "user deviated
                        # from provider's recommendation" auditable post-hoc.
                        project_params = selected_config_for_model.get("parameters", {})

                        # Per-model overrides may live either flat on
                        # model_config or nested under model_config.generation_config
                        # (legacy shape kept for backward-compat). Flatten so
                        # the resolver only has to look one place.
                        per_model_flat: Dict[str, Any] = {}
                        if model_config:
                            for _k in ("temperature", "max_tokens", "seed", "top_p"):
                                if _k in model_config:
                                    per_model_flat[_k] = model_config[_k]
                                elif (
                                    isinstance(model_config.get("generation_config"), dict)
                                    and _k in model_config["generation_config"]
                                ):
                                    per_model_flat[_k] = model_config["generation_config"][_k]

                        prompt_meta_dict = (
                            instruction_prompt.prompt_metadata
                            if (
                                hasattr(instruction_prompt, "prompt_metadata")
                                and instruction_prompt.prompt_metadata
                            )
                            else None
                        )

                        model_recommended = (
                            getattr(model, "recommended_parameters", None) or None
                        )

                        _provenance: Dict[str, Dict[str, Any]] = {}

                        def _resolve(key: str) -> Any:
                            value, source, rec_at_trigger = tasks._resolve_param(
                                key=key,
                                mode="generation",
                                model_recommended=model_recommended,
                                project_cfg=project_params,
                                per_model_cfg=per_model_flat,
                                prompt_meta=prompt_meta_dict,
                            )
                            _provenance[key] = {
                                "value": value,
                                "source": source,
                                "recommended_at_trigger": rec_at_trigger,
                            }
                            return value

                        temperature = _resolve("temperature")
                        max_tokens = _resolve("max_tokens")
                        seed = _resolve("seed")
                        if _provenance["temperature"]["source"] != "system":
                            tasks.logger.info(
                                f"🌡️ temperature={temperature} from "
                                f"{_provenance['temperature']['source']} "
                                f"(recommended at trigger: {_provenance['temperature']['recommended_at_trigger']})"
                            )

                        # Multi-run variance: when this is one of N>1 trials
                        # (run_index > 0 or runs_requested > 1), perturb the seed
                        # by run_index. Without this, OpenAI's seed parameter
                        # makes every trial deterministic-identical even at
                        # temperature=1.0 — defeating the purpose of variance
                        # studies. Run 0 keeps the user's chosen seed for
                        # reproducibility; runs 1..N-1 get seed+run_index.
                        # If the user explicitly wants identical seeds across
                        # runs (a sanity check), they can pin seed via
                        # generation_config and set runs_per_task = 1.
                        try:
                            _rr = int(getattr(generation, "runs_requested", 1) or 1)
                        except (TypeError, ValueError):
                            _rr = 1
                        if _rr > 1 and run_index > 0:
                            _seed_pre = seed
                            seed = (seed or 0) + run_index
                            tasks.logger.info(
                                f"🎲 Multi-run trial {run_index}/{_rr}: "
                                f"seed perturbed to {seed} for variance"
                            )
                            # Record the actual seed sent to the API in
                            # provenance, plus the pre-perturbation value
                            # so an analyst can see the variance offset.
                            if "seed" in _provenance:
                                _provenance["seed"]["value"] = seed
                                _provenance["seed"]["multi_run_offset"] = run_index
                                _provenance["seed"]["pre_perturbation"] = _seed_pre

                        # Extract reasoning/thinking config from model_config.
                        # Phase 6.6: also forward `seed` here so all four
                        # ai_service.generate{,_structured}() call sites
                        # below receive it via **reasoning_kwargs without
                        # needing per-site changes.
                        reasoning_kwargs = {"seed": seed}
                        if model_config:
                            # OpenAI o-series: reasoning_effort
                            if "reasoning_effort" in model_config:
                                reasoning_kwargs["reasoning_effort"] = model_config[
                                    "reasoning_effort"
                                ]
                            # Anthropic/Qwen: thinking_budget
                            if "thinking_budget" in model_config:
                                reasoning_kwargs["thinking_budget"] = model_config[
                                    "thinking_budget"
                                ]
                            # Mistral: prompt_mode
                            if "prompt_mode" in model_config:
                                reasoning_kwargs["prompt_mode"] = model_config["prompt_mode"]
                            # Cohere: thinking_token_budget
                            if "thinking_token_budget" in model_config:
                                reasoning_kwargs["thinking_token_budget"] = model_config[
                                    "thinking_token_budget"
                                ]

                        # Apply model-specific parameter constraints (final
                        # guardrail after the precedence chain). Clamping
                        # also patches `_provenance.temperature.value` so
                        # the snapshot reflects what was actually sent to
                        # the LLM, not the user's pre-clamp choice — but
                        # `source` and `recommended_at_trigger` are kept
                        # so analysts can still see "user tried X, model
                        # forced Y".
                        # parameter_constraints is owner-supplied JSON for
                        # custom (BYOM) models, only shape-checked as a dict at
                        # the API. Guard every nested access so a malformed
                        # value ({"temperature": "high"}, a non-numeric min,
                        # ...) can't raise here and fail every generation cell.
                        constraints = getattr(model, 'parameter_constraints', None)
                        if isinstance(constraints, dict):
                            temp_config = constraints.get('temperature')
                            if not isinstance(temp_config, dict):
                                temp_config = {}

                            required_temp = temp_config.get('required_value')
                            min_temp = temp_config.get('min')
                            max_temp = temp_config.get('max')
                            _numeric = (int, float)

                            # Fixed temperature (e.g., GPT-5 series, o-series)
                            if not temp_config.get('supported', True):
                                if isinstance(required_temp, _numeric):
                                    if temperature != required_temp:
                                        tasks.logger.info(
                                            f"🔒 Overriding temperature to {required_temp} for {api_model_name} (model requirement)"
                                        )
                                        _provenance["temperature"]["clamped_from"] = temperature
                                    temperature = required_temp
                                    _provenance["temperature"]["value"] = temperature
                            else:
                                # Clamp to allowed min/max range
                                if isinstance(min_temp, _numeric) and temperature < min_temp:
                                    tasks.logger.info(
                                        f"⚠️ Clamping temperature from {temperature} to min {min_temp} for {api_model_name}. "
                                        f"Reason: {temp_config.get('reason', 'Model constraint')}"
                                    )
                                    _provenance["temperature"]["clamped_from"] = temperature
                                    temperature = min_temp
                                    _provenance["temperature"]["value"] = temperature
                                if isinstance(max_temp, _numeric) and temperature > max_temp:
                                    tasks.logger.info(
                                        f"⚠️ Clamping temperature from {temperature} to max {max_temp} for {api_model_name}. "
                                        f"Reason: {temp_config.get('reason', 'Model constraint')}"
                                    )
                                    _provenance["temperature"]["clamped_from"] = temperature
                                    temperature = max_temp
                                    _provenance["temperature"]["value"] = temperature

                            # Authoritative max_tokens clamp — mirrors the
                            # temperature clamp above. The owner-declared
                            # parameter_constraints.max_tokens.max is the REAL
                            # ceiling, enforced HERE regardless of how the
                            # request/persisted config was built or whether the
                            # value arrived as a float. The API-side pre-check
                            # is only an early 400; this is the boundary.
                            mt_config = constraints.get('max_tokens')
                            if not isinstance(mt_config, dict):
                                mt_config = {}
                            declared_max_mt = mt_config.get('max')
                            if (
                                isinstance(declared_max_mt, _numeric)
                                and not isinstance(declared_max_mt, bool)
                                and isinstance(max_tokens, _numeric)
                                and not isinstance(max_tokens, bool)
                                and max_tokens > declared_max_mt
                            ):
                                tasks.logger.info(
                                    f"⚠️ Clamping max_tokens from {max_tokens} to model max "
                                    f"{declared_max_mt} for {api_model_name}."
                                )
                                _provenance["max_tokens"]["clamped_from"] = max_tokens
                                max_tokens = int(declared_max_mt)
                                _provenance["max_tokens"]["value"] = max_tokens

                        # max_tokens must be an int for the provider APIs; a
                        # per-model config override can arrive as a JSON float.
                        if isinstance(max_tokens, float):
                            max_tokens = int(max_tokens)

                        tasks.logger.info(
                            f"🌡️ Final temperature: {temperature}, max_tokens: {max_tokens} for model {model_id}"
                        )

                        # Capture resolved parameters for provenance.
                        # `_param_provenance` records (value, source,
                        # recommended_at_trigger) per key so analysts can
                        # group runs by which tier won (system / recommended
                        # / user_*) and detect deviation from provider
                        # recommendations even after the YAML changes.
                        if _captured_parameters is None:
                            _captured_parameters = {
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                **reasoning_kwargs,
                                "_param_provenance": _provenance,
                            }

                        # Apply rate limiting (Issue #482)
                        current_time = time.time()
                        time_since_last = current_time - last_request_time

                        if time_since_last < min_delay:
                            sleep_time = min_delay - time_since_last
                            tasks.logger.info(f"⏳ Rate limiting: sleeping for {sleep_time:.2f}s")
                            time.sleep(sleep_time)

                        # Update last request time after the delay
                        last_request_time = time.time()

                        # Generate JSON schema from label_config for structured output
                        json_schema = None
                        use_structured_output = False
                        if project.label_config:
                            try:
                                from ai_services import generate_json_schema_from_label_config

                                json_schema = generate_json_schema_from_label_config(
                                    project.label_config
                                )
                                if json_schema.get("properties"):
                                    use_structured_output = True
                                    tasks.logger.info(
                                        f"📋 Generated JSON schema for structured output: {list(json_schema['properties'].keys())}"
                                    )
                            except Exception as schema_error:
                                tasks.logger.warning(f"⚠️ Could not generate JSON schema: {schema_error}")

                        # Extract field names from label_config and append output schema to prompt
                        # This ensures LLM produces fields matching annotation field names
                        if project.label_config:
                            output_fields = tasks.extract_label_config_fields(project.label_config)
                            if output_fields:
                                output_schema = {
                                    field: "<your response>" for field in output_fields
                                }
                                schema_instruction = (
                                    "\n\n---\n"
                                    "IMPORTANT: Respond ONLY with valid JSON using these exact field names:\n"
                                    f"```json\n{json.dumps(output_schema, indent=2)}\n```"
                                )
                                user_prompt = user_prompt + schema_instruction
                                tasks.logger.info(
                                    f"📋 Appended output schema instruction with fields: {output_fields}"
                                )

                        # Generate response using appropriate AI service
                        if use_structured_output and hasattr(ai_service, 'generate_structured'):
                            # Use structured output for guaranteed JSON responses
                            tasks.logger.info(
                                f"🔧 Using structured output generation for {model.provider}"
                            )

                            # Use user_prompt directly - it already contains interpolated fields from prompt structure
                            # DO NOT append task_content here as it contains sensitive fields (binary_solution, reasoning)
                            final_prompt = user_prompt

                            # Check if service has async or sync generate_structured
                            if asyncio.iscoroutinefunction(ai_service.generate_structured):

                                async def generate_structured_response():
                                    return await ai_service.generate_structured(
                                        prompt=final_prompt,
                                        system_prompt=system_prompt,
                                        json_schema=json_schema,
                                        model_name=api_model_name,
                                        temperature=temperature,
                                        max_tokens=max_tokens,
                                        **reasoning_kwargs,
                                    )

                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    response_data = loop.run_until_complete(
                                        generate_structured_response()
                                    )
                                finally:
                                    loop.close()
                            else:
                                # Sync version
                                response_data = ai_service.generate_structured(
                                    prompt=final_prompt,
                                    system_prompt=system_prompt,
                                    json_schema=json_schema,
                                    model_name=api_model_name,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                    **reasoning_kwargs,
                                )
                        else:
                            # Standard text generation (no structured output)
                            tasks.logger.info(f"🔧 Using standard generate for {model.provider}")

                            if asyncio.iscoroutinefunction(ai_service.generate):

                                async def generate_response():
                                    return await ai_service.generate(
                                        prompt=user_prompt,
                                        system_prompt=system_prompt,
                                        model_name=api_model_name,
                                        temperature=temperature,
                                        max_tokens=max_tokens,
                                        **reasoning_kwargs,
                                    )

                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    response_data = loop.run_until_complete(
                                        generate_response()
                                    )
                                finally:
                                    loop.close()
                            else:
                                response_data = ai_service.generate(
                                    prompt=user_prompt,
                                    system_prompt=system_prompt,
                                    model_name=api_model_name,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                    **reasoning_kwargs,
                                )

                        # Extract response content and metadata
                        tasks.logger.info(f"🔍 Raw response_data keys: {list(response_data.keys())}")
                        tasks.logger.info(f"🔍 Raw response_data: {response_data}")

                        # Check if AI service reported an error (e.g., 503, rate limit, safety block)
                        if not response_data.get("success", True):
                            raw_error = response_data.get("error", "Unknown AI service error")
                            # Try to extract the human-readable message from API error JSON
                            match = re.search(r"'message':\s*'([^']+)'", str(raw_error))
                            error_msg = match.group(1) if match else str(raw_error)
                            raise Exception(error_msg)

                        if "response_text" in response_data:
                            response_text = response_data["response_text"]
                            usage_stats = {
                                "prompt_tokens": response_data.get("prompt_tokens", 0),
                                "completion_tokens": response_data.get("completion_tokens", 0),
                                "total_tokens": response_data.get("total_tokens", 0),
                                "cost_usd": response_data.get("cost_usd", 0.0),
                            }
                            metadata = {
                                "prompt_id": prompt_id,
                                "prompt_name": prompt_name,
                                "temperature": response_data.get("temperature", 0.0),
                                "provider": response_data.get("provider", model.provider),
                                "system_prompt": system_prompt,
                                "instruction_prompt": user_prompt,
                                # Phase 6.1+6.2+6.5: merge AI-service-side audit
                                # trail (requested/actual temperature, retry
                                # history, provider route, billed user/org)
                                # so it lands on Generation rows alongside
                                # the worker-side metadata. The service-side
                                # dict can't override worker-set keys above.
                                **{
                                    k: v
                                    for k, v in (response_data.get("metadata") or {}).items()
                                    if k not in {
                                        "prompt_id", "prompt_name",
                                        "system_prompt", "instruction_prompt",
                                    }
                                },
                                # Issue #82: stamp the key-resolution audit
                                # fields directly off the service so every
                                # provider (not just openai) lands them.
                                "key_resolution_route": getattr(ai_service, "_key_resolution_route", None),
                                "provider_name": getattr(ai_service, "_provider_name", None),
                                "invocation_user_id": getattr(ai_service, "_invocation_user_id", None),
                                "invocation_organization_id": getattr(ai_service, "_invocation_organization_id", None),
                            }
                            tasks.logger.info(
                                f"✅ Using response_text format, content length: {len(response_text)}"
                            )
                        elif "content" in response_data:
                            # OpenAI format
                            response_text = response_data["content"]
                            usage_stats = response_data.get("usage", {})
                            metadata = {
                                "prompt_id": prompt_id,
                                "prompt_name": prompt_name,
                                "temperature": response_data.get("temperature", 0.0),
                                "provider": model.provider,
                                "system_prompt": system_prompt,
                                "instruction_prompt": user_prompt,
                                # Same merge as above (Phase 6 audit trail).
                                **{
                                    k: v
                                    for k, v in (response_data.get("metadata") or {}).items()
                                    if k not in {
                                        "prompt_id", "prompt_name",
                                        "system_prompt", "instruction_prompt",
                                    }
                                },
                                # Issue #82: same key-resolution audit fields.
                                "key_resolution_route": getattr(ai_service, "_key_resolution_route", None),
                                "provider_name": getattr(ai_service, "_provider_name", None),
                                "invocation_user_id": getattr(ai_service, "_invocation_user_id", None),
                                "invocation_organization_id": getattr(ai_service, "_invocation_organization_id", None),
                            }
                            tasks.logger.info(
                                f"✅ Using content format, content length: {len(response_text)}"
                            )
                        else:
                            tasks.logger.error(
                                f"❌ Unexpected response format - available keys: {list(response_data.keys())}"
                            )
                            raise Exception(f"Unexpected response format: {response_data}")

                        # Reject empty responses from any provider
                        if not response_text or not response_text.strip():
                            raise Exception(
                                f"AI service returned empty response for {model_id}"
                            )

                        tasks.logger.info(
                            f"📝 Final response_text length: {len(response_text)}"
                        )
                        tasks.logger.info(
                            f"📝 Response preview: {response_text[:100] if response_text else 'EMPTY'}"
                        )
                        tasks.logger.info(f"📊 Usage stats: {usage_stats}")

                        # Parse LLM response to structured format
                        parse_result = None
                        parsed_annotation = None
                        parse_status = "pending"
                        parse_error = None
                        parse_metadata = {}
                        final_status = "completed"

                        # Check existing parse attempts for retry limiting
                        existing_attempts = (
                            db.query(tasks.DBLLMResponse)
                            .filter(
                                tasks.DBLLMResponse.task_id == task_data["id"],
                                tasks.DBLLMResponse.model_id == model_id,
                            )
                            .count()
                        )

                        MAX_PARSE_RETRIES = 3

                        # Attempt parsing if we have label_config (structured output responses are JSON)
                        # generation_structure is optional - ResponseParser can auto-derive schema from label_config
                        if project.label_config:
                            try:
                                tasks.logger.info(f"🔍 Parsing LLM response for task {task_data['id']}")
                                # Use empty dict if no generation_structure (parser auto-derives from label_config)
                                parser = tasks.ResponseParser(
                                    generation_structure=generation_structure or {},
                                    label_config=project.label_config,
                                )
                                # Pass source text for span position calculation (Issue #964)
                                source_text = task_content.get("text") if task_content else None
                                parse_result = parser.parse(response_text, source_text=source_text)

                                parse_status = parse_result.status
                                parse_error = parse_result.error
                                parsed_annotation = parse_result.parsed_annotation

                                tasks.logger.info(f"📋 Parse status: {parse_status}")
                                if parse_status == "success":
                                    tasks.logger.info(
                                        f"✅ Successfully parsed response with {len(parsed_annotation)} fields"
                                    )
                                else:
                                    tasks.logger.warning(f"⚠️ Parse failed: {parse_error}")

                            except Exception as e:
                                tasks.logger.error(f"❌ Error during parsing: {str(e)}")
                                parse_status = "failed"
                                parse_error = f"Parser exception: {str(e)}"
                        else:
                            tasks.logger.info(
                                "ℹ️ Skipping parsing - no label_config configured for project"
                            )

                        # Determine final status based on parse result and retry count
                        if parse_status != "success" and existing_attempts >= MAX_PARSE_RETRIES:
                            final_status = "parse_failed_max_retries"
                            tasks.logger.warning(
                                f"🚫 Max parse retries ({MAX_PARSE_RETRIES}) reached for task {task_data['id']}"
                            )
                        elif parse_status != "success":
                            final_status = "parse_failed"
                            tasks.logger.info(
                                f"🔄 Parse failed, will retry (attempt {existing_attempts + 1}/{MAX_PARSE_RETRIES})"
                            )
                        else:
                            final_status = "completed"

                        # Build parse metadata
                        parse_metadata = {
                            "retry_count": existing_attempts + 1,
                            "last_attempt": datetime.now().isoformat(),
                            "max_retries_reached": existing_attempts >= MAX_PARSE_RETRIES,
                        }

                        # Save response to database
                        case_data_with_id = {
                            "text": str(task_content),
                            "task_item_id": task_data[
                                "id"
                            ],  # Native annotation system task item ID
                            "original_task_data": task_data,
                        }

                        # Phase 6.6: pull the academic-rigor fields out of
                        # the merged metadata dict + usage stats so the
                        # discrete columns (migration 040) and the JSON
                        # blob stay in sync. None defaults are fine for
                        # any provider that doesn't surface a given field.
                        llm_response = tasks.DBLLMResponse(
                            id=str(uuid.uuid4()),
                            generation_id=generation_id,
                            task_id=task_data["id"],  # Use actual task ID, not project ID
                            model_id=model_id,
                            # prompt_id removed - prompts table dropped in issue #759
                            case_data=json.dumps(case_data_with_id),
                            response_content=response_text,
                            usage_stats=usage_stats,
                            response_metadata=json.dumps(metadata),
                            # Migration 041: trial index within parent fan-out
                            run_index=run_index,
                            # Phase 6.6 columns.
                            seed=metadata.get("seed"),
                            finish_reason=metadata.get("finish_reason"),
                            truncated=bool(metadata.get("truncated", False)),
                            refusal=bool(metadata.get("refusal", False)),
                            error_type=metadata.get("error_type"),
                            latency_ms=metadata.get("response_time_ms"),
                            input_tokens=usage_stats.get("prompt_tokens") if isinstance(usage_stats, dict) else None,
                            output_tokens=usage_stats.get("completion_tokens") if isinstance(usage_stats, dict) else None,
                            # Parse results
                            parsed_annotation=parsed_annotation,
                            parse_status=parse_status,
                            parse_error=parse_error,
                            parse_metadata=parse_metadata,
                            # Label config versioning
                            label_config_version=project.label_config_version,
                            label_config_snapshot=project.label_config,
                            status=final_status,
                            created_at=datetime.now(),
                        )

                        # Cooperative cancel (issue #198): the parent status may
                        # have flipped to a terminal stop/supersede/pause WHILE
                        # the (slow) LLM call was in flight. Re-read it with a raw
                        # scalar — this does NOT touch the ORM query path the unit
                        # mocks drive — and skip PERSISTING the response. We can't
                        # un-spend the call, but we don't write it and we stop.
                        # Default to proceeding if the check itself errors (don't
                        # lose already-finished work).
                        try:
                            _live_status = db.execute(
                                _sql_text(
                                    "SELECT status FROM response_generations "
                                    "WHERE id = :id"
                                ),
                                {"id": generation_id},
                            ).scalar()
                        except Exception:
                            _live_status = None
                        if _live_status in ("cancelled", "stopped", "paused"):
                            tasks.logger.info(
                                f"⏹️ Generation {generation_id} {_live_status} during "
                                "the LLM call; discarding the in-flight response"
                            )
                            _aborted = True
                            break

                        db.add(llm_response)

                        # NOTE: do NOT write generation.responses_generated here.
                        # It is accumulated ONCE post-loop (`(existing or 0) +
                        # responses_generated`). Writing the absolute per-trial
                        # count here too both double-counted (the post-loop add
                        # lands on top of this committed value after db.refresh)
                        # and clobbered sibling trials' accumulated count in a
                        # multi-run fan-out. total_expected is 1 per trial (one
                        # task × one prompt), so there is no mid-trial progress to
                        # surface anyway; the WS ping uses the local counter.

                        # Commit after each response to avoid losing work. A
                        # uq(generation_id, run_index) collision means a surviving
                        # prior trial already wrote this run_index (race after a
                        # best-effort revoke) — treat as an idempotent no-op, NOT
                        # a failure (the parent counter was already bumped by that
                        # trial).
                        try:
                            db.commit()
                        except _IntegrityError:
                            db.rollback()
                            _duplicate_skip = True
                            tasks.logger.info(
                                f"⏭️ run_index {run_index} of {generation_id} already "
                                "written by a concurrent trial; skipping duplicate"
                            )
                            continue

                        responses_generated += 1
                        tasks.logger.info(
                            f"✅ Generated response {responses_generated}/{total_expected} for task {task_data['id']}"
                        )

                        # Progress ping on the same throttle as the counter update
                        # (every 10 rows or at end). PROGRESS only — always
                        # "running". The authoritative terminal signal
                        # ("completed"/"failed"/…) is broadcast once post-commit
                        # from the DERIVED parent status below, so a multi-run
                        # gen's socket never closes early off a stale in-memory
                        # runs_completed estimate (the prior `(runs_completed+1) >=
                        # runs_requested` heuristic read a per-trial-stale count).
                        if (
                            responses_generated % 10 == 0
                            or responses_generated == total_expected
                        ):
                            tasks._publish_progress(
                                f"generation:progress:{project_id}",
                                {
                                    "type": "progress",
                                    "generation_id": generation.id,
                                    "model_id": model_id,
                                    "responses_generated": responses_generated,
                                    "total_expected": total_expected,
                                    "status": "running",
                                },
                            )

                    except Exception as e:
                        _last_error = str(e)
                        tasks.logger.error(
                            f"❌ Failed to generate response for task {task_data['id']}, prompt {prompt_id}: {_last_error}"
                        )
                        continue

                if _aborted:
                    break

            # Multi-run aggregation — DERIVE the parent state from the child
            # rows instead of incrementing a counter. ``runs_completed`` is an
            # idempotent ``COUNT(DISTINCT run_index)`` of trials that PRODUCED a
            # response (every child row is one — a pure LLM failure writes no
            # child; a parse failure still generated a response and counts, as
            # the legacy ``responses_generated += 1`` did). So the fan-out can't
            # double-count, a post-revoke duplicate is harmless, and resume/retry
            # need no counter reconciliation. For single-run this is identical to
            # the legacy behaviour; for N>1 the parent reaches "completed" only
            # when every trial produced a response, and "failed" on the first
            # trial that errored without one. User-terminal statuses
            # (cancelled/stopped/paused — incl. the #198 mid-call abort) win.
            trial_failed = responses_generated == 0 and total_expected > 0

            db.refresh(generation)

            # Bare Mocks (unit tests) / legacy rows may not coerce cleanly.
            def _as_int(v: Any, default: int) -> int:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    return default

            _runs_requested = _as_int(getattr(generation, "runs_requested", 1), 1)
            try:
                _completed = int(
                    db.execute(
                        _sql_text(
                            "SELECT COUNT(DISTINCT run_index) FROM generations "
                            "WHERE generation_id = :gid"
                        ),
                        {"gid": generation_id},
                    ).scalar()
                    or 0
                )
            except (TypeError, ValueError):
                # Bare-Mock db (unit tests): ``db.execute(...).scalar()`` returns a
                # Mock and ``int(Mock or 0)`` raises TypeError — fall back to this
                # trial's own signal. A REAL transient DB error is a SQLAlchemyError
                # (not TypeError/ValueError) and propagates to the outer handler,
                # which marks the trial failed and lets Celery retry — far better
                # than silently mis-deriving the parent off one trial's count.
                _completed = 0 if (_aborted or trial_failed) else responses_generated

            if generation.status in ("cancelled", "stopped", "paused"):
                # User-terminal (incl. the #198 mid-call abort) — the user asked
                # to stop; this wins over EVERYTHING, even a derived "completed"
                # (a stopped gen that happens to have all children stays stopped).
                # Just sync the derived completed count.
                generation.runs_completed = min(_completed, _runs_requested)
            elif _completed >= _runs_requested:
                # Completion wins over a stale "failed" latch. If every run_index
                # produced a child — e.g. a retry re-filled the missing one, or a
                # prior-epoch survivor landed AFTER the parent latched "failed" —
                # the gen IS complete. Checking this BEFORE the failed-latch below
                # self-heals that survivor race (otherwise "failed" would stick
                # despite all children existing, an inconsistent terminal state).
                generation.runs_completed = _runs_requested
                generation.runs_failed = 0
                generation.status = "completed"
                generation.completed_at = datetime.now()
            elif generation.status == "failed":
                # FIRST-FAILURE latch — only while still INCOMPLETE. A failed
                # trial writes no child, so COUNT can't reach runs_requested; a
                # later-finishing sibling success must NOT un-fail the parent (it
                # would otherwise be stuck "running" with no retry/resume path).
                # Retry resets the status to "running" before re-dispatch, so this
                # latch never blocks a deliberate retry. Keep runs_failed
                # consistent as siblings land (the still-missing run_indices) so
                # completed+failed can't exceed runs_requested in the UI.
                generation.runs_completed = min(_completed, _runs_requested)
                generation.runs_failed = _runs_requested - generation.runs_completed
            elif _duplicate_skip:
                # A duplicate of an already-written run_index (post-revoke race),
                # and the parent isn't complete yet — NOT a failure.
                generation.runs_completed = min(_completed, _runs_requested)
                generation.status = "running"
            elif trial_failed:
                # First-failure semantics for multi-run.
                generation.runs_completed = min(_completed, _runs_requested)
                generation.runs_failed = max(_runs_requested - _completed, 1)
                generation.status = "failed"
                generation.error_message = _last_error or generation.error_message or "Trial failed"
                generation.completed_at = datetime.now()
            else:
                # This trial succeeded; more trials still pending.
                generation.runs_completed = min(_completed, _runs_requested)
                generation.runs_failed = 0
                generation.status = "running"

            generation.responses_generated = (generation.responses_generated or 0) + responses_generated
            metadata = {
                "total_expected": total_expected,
                "successful": responses_generated,
                "failed": total_expected - responses_generated,
                "model_provider": model.provider,
                "api_model_name": api_model_name,
            }
            # Add structure_key to metadata if provided (Issue #762)
            if structure_key:
                metadata["structure_key"] = structure_key
            generation.generation_metadata = json.dumps(metadata)

            # Store prompt provenance and parameters
            if _captured_prompt_templates:
                generation.prompt_used = json.dumps(
                    _captured_prompt_templates,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            if _captured_parameters:
                generation.parameters = _captured_parameters

            # Capture the derived status BEFORE commit (the worker session is
            # expire_on_commit=True, so reading generation.status after commit
            # would re-query).
            _final_status = generation.status

            db.commit()

            # Authoritative terminal WS signal: fires exactly once, from whichever
            # trial drove the parent to a terminal status — unlike the in-loop
            # pings, which are progress-only. Uses the committed derived status, so
            # a multi-run gen broadcasts "completed"/"failed" only when it really
            # is, never off a single trial's per-trial estimate. "paused" is
            # included so a pause-while-in-flight emits a state frame instead of
            # leaving the client stuck on the last "running" ping.
            if _final_status in (
                "completed",
                "failed",
                "cancelled",
                "stopped",
                "paused",
            ):
                try:
                    tasks._publish_progress(
                        f"generation:progress:{project_id}",
                        {
                            "type": "progress",
                            "generation_id": generation_id,
                            "model_id": model_id,
                            "responses_generated": responses_generated,
                            "total_expected": total_expected,
                            "status": _final_status,
                        },
                    )
                except Exception as ws_error:
                    tasks.logger.warning(
                        f"⚠️ Failed to broadcast terminal status: {ws_error}"
                    )

            if _aborted:
                # Cancelled mid-call (issue #198): the terminal status is already
                # committed above. Skip the report "generation completed" update,
                # the completion notification, and the failed/success return —
                # this trial was cancelled, not finished.
                tasks.logger.info(
                    f"⏹️ Generation {generation_id} cancelled mid-run; no response "
                    "persisted, skipping completion report/notification"
                )
                return {
                    "status": "cancelled",
                    "generation_id": generation_id,
                    "model_id": model_id,
                    "message": "Generation cancelled before the response was persisted",
                    "responses_generated": 0,
                    "total_expected": total_expected,
                }

            # Update report generation section after generation completion (Issue
            # #770) — ONLY when the parent actually reached terminal "completed".
            # In a multi-run fan-out each trial runs this function, so without the
            # _final_status gate a still-"running" trial (N-1 of N) would mark the
            # report section "completed" prematurely, and a failed trial
            # (responses_generated==0) would mark it "completed" despite producing
            # nothing. Gated like the WS terminal signal above.
            try:
                report = (
                    db.query(tasks.DBProjectReport)
                    .filter(tasks.DBProjectReport.project_id == project_id)
                    .first()
                )
                if report and _final_status == "completed":
                    # Get unique models from generations for this project
                    models = (
                        db.query(tasks.DBLLMResponse.model_id)
                        .join(
                            tasks.DBResponseGeneration,
                            tasks.DBLLMResponse.generation_id == tasks.DBResponseGeneration.id,
                        )
                        .filter(tasks.DBResponseGeneration.project_id == project_id)
                        .distinct()
                        .all()
                    )
                    model_ids = [m[0] for m in models]

                    # Preserve custom text if it exists
                    existing_generation = report.content.get("sections", {}).get("generation", {})
                    custom_text = existing_generation.get("custom_text")
                    show_config = existing_generation.get("show_config", False)

                    # Update report content
                    if "sections" not in report.content:
                        report.content["sections"] = {}
                    report.content["sections"]["generation"] = {
                        "models": model_ids,
                        "custom_text": custom_text,
                        "show_models": True,
                        "show_config": show_config,
                        "status": "completed",
                        "editable": True,
                        "visible": True,
                    }

                    # Update metadata
                    if "metadata" not in report.content:
                        report.content["metadata"] = {}
                    report.content["metadata"]["last_auto_update"] = datetime.now().isoformat()
                    if "sections_completed" not in report.content["metadata"]:
                        report.content["metadata"]["sections_completed"] = []
                    if "generation" not in report.content["metadata"]["sections_completed"]:
                        report.content["metadata"]["sections_completed"].append("generation")

                    # Mark content as modified for SQLAlchemy to detect the change
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(report, "content")
                    db.commit()
                    tasks.logger.info(f"✅ Updated report generation section for project {project_id}")
                else:
                    tasks.logger.debug(
                        f"No report found for project {project_id} - skipping report update"
                    )
            except Exception as e:
                tasks.logger.error(f"Failed to update report generation section: {e}")
                # Don't fail the generation operation

            tasks.logger.info(
                f"🎉 Generation completed: {responses_generated}/{total_expected} successful"
            )

            # Trigger notification for completion. Writes a real DB
            # notification (via NotificationService) carrying generation_id
            # so the frontend NotificationDropdown can route the click to
            # /generations/{id}. The legacy notify_task_completed log stub
            # was previously called here too as belt-and-suspenders; removed
            # because emitting two side effects per event was just noise
            # (the stub doesn't write to the DB, only logs).
            #
            # Gated on _final_status == "completed" so the "Generation Complete"
            # notification fires EXACTLY ONCE — from the trial that drives the
            # parent terminal — not N times for an N-run fan-out (N-1 premature),
            # and never on a failed trial (which would send a false "0/N
            # responses" success). Same gate as the report update + WS signal.
            try:
                if (
                    project
                    and tasks.HAS_DATABASE
                    and user_id
                    and _final_status == "completed"
                ):
                    tasks.NotificationService.create_notification(
                        db=db,
                        user_ids=[user_id],
                        notification_type=tasks.NotificationType.LLM_GENERATION_COMPLETED,
                        title="Generation Complete",
                        message=(
                            f"Generation completed for {project.title}: "
                            f"{responses_generated}/{total_expected} responses"
                        ),
                        data={
                            "project_id": project_id,
                            "generation_id": generation_id,
                            "model_id": model_id,
                            "responses_generated": responses_generated,
                            "total_expected": total_expected,
                        },
                    )
                    tasks.logger.info(
                        f"✅ Notification sent for generation {generation_id} (project {project_id})"
                    )
            except Exception as notification_error:
                tasks.logger.warning(f"⚠️ Failed to send notification: {notification_error}")

            # Note: Bidirectional sync will be handled by the periodic sync task every 10 minutes

            # Return status reflecting actual outcome
            if responses_generated == 0 and total_expected > 0:
                if _duplicate_skip:
                    # This run_index was already generated by another (surviving)
                    # trial — a no-op redelivery, not a failure.
                    return {
                        "status": "skipped",
                        "generation_id": generation_id,
                        "model_id": model_id,
                        "message": "run_index already generated by another trial",
                        "responses_generated": 0,
                        "total_expected": total_expected,
                    }
                return {
                    "status": "failed",
                    "generation_id": generation_id,
                    "model_id": model_id,
                    "message": f"Generation failed: 0/{total_expected} responses - all attempts failed",
                    "responses_generated": 0,
                    "total_expected": total_expected,
                }

            return {
                "status": "success",
                "generation_id": generation_id,
                "model_id": model_id,
                "message": f"Generation completed successfully: {responses_generated}/{total_expected} responses",
                "responses_generated": responses_generated,
                "total_expected": total_expected,
            }

        except Exception as e:
            # Mark this trial's generation failed — BUT don't clobber a terminal
            # status another path already set. This handler fires for ANY
            # exception outside the per-prompt try, including a SIGTERM that
            # surfaces in the post-loop recompute region (stop/pause revoke) or a
            # transient DB error AFTER all children already landed. Re-read the
            # row and skip the "failed" write (and the runs_failed bump) when it's
            # user-terminal (cancelled/stopped/paused — the user asked to stop) or
            # already "completed" (every child present — a transient recompute
            # error must not flip a real success to failed). Mirrors the outer
            # generate_response_impl guard.
            try:
                from sqlalchemy import text as _sql_text

                # Discard any uncommitted in-memory state from the failed attempt
                # FIRST. Two reasons: (1) if the triggering error was a DB failure
                # (e.g. the recompute commit), the session is in a failed
                # transaction and every subsequent statement would raise
                # PendingRollbackError until rolled back; (2) the recompute block
                # may have already dirtied generation.runs_failed in the ORM — a
                # later flush would re-write that stale value ON TOP of the raw
                # `runs_failed + 1` below. Rolling back gives a clean session so the
                # raw UPDATE + ORM status write are the only pending changes.
                db.rollback()

                # Read the LIVE committed status with a raw scalar — NOT
                # db.query, which returns this session's identity-mapped, stale
                # in-memory "running". A concurrent stop/pause/cancel committed by
                # the API (and the #198 cooperative-cancel path) only shows up via
                # a fresh read. Default to proceeding (mark failed) if the read
                # itself errors.
                try:
                    _live_status = db.execute(
                        _sql_text(
                            "SELECT status FROM response_generations WHERE id = :gid"
                        ),
                        {"gid": generation_id},
                    ).scalar()
                except Exception:
                    _live_status = None
                if _live_status not in (
                    "completed",
                    "cancelled",
                    "stopped",
                    "paused",
                ):
                    db.execute(
                        _sql_text(
                            "UPDATE response_generations SET runs_failed = runs_failed + 1 "
                            "WHERE id = :gid"
                        ),
                        {"gid": generation_id},
                    )
                    generation = (
                        db.query(tasks.DBResponseGeneration)
                        .filter(tasks.DBResponseGeneration.id == generation_id)
                        .first()
                    )
                    if generation:
                        generation.status = "failed"
                        generation.error_message = str(e)
                        generation.completed_at = datetime.now()
                        db.commit()
            except Exception as db_error:
                tasks.logger.error(f"❌ Failed to update generation status: {str(db_error)}")

            tasks.logger.error(f"❌ Generation failed for {generation_id}: {str(e)}")
            raise

        finally:
            db.close()

    except Exception as e:
        tasks.logger.error(f"❌ Async generation failed for {generation_id}: {str(e)}")
        return {
            "status": "error",
            "generation_id": generation_id,
            "model_id": model_id,
            "message": str(e),
        }
