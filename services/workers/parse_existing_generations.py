#!/usr/bin/env python3
"""
Parse existing LLM generations that were created before the parsing system.

This script:
1. Finds all generations with parse_status='pending'
2. Attempts to parse them using the ResponseParser
3. Updates the database with parse results
4. Reports parsing statistics
"""

import logging
from datetime import datetime

from response_parser import ResponseParser

from database import SessionLocal
from models import LLMResponse as DBLLMResponse
from models import ResponseGeneration as DBResponseGeneration
from project_models import Project

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_existing_generations(limit: int = None, dry_run: bool = False):
    """Parse existing generations with pending status.

    Args:
        limit: Maximum number of generations to process (None for all)
        dry_run: If True, don't commit changes to database
    """
    db = SessionLocal()

    try:
        # Find all pending generations
        query = db.query(DBLLMResponse).filter(DBLLMResponse.parse_status == "pending")

        if limit:
            query = query.limit(limit)

        pending_generations = query.all()

        logger.info(f"Found {len(pending_generations)} pending generations to parse")

        if len(pending_generations) == 0:
            logger.info("No pending generations found. Exiting.")
            return

        # Statistics
        stats = {
            "total": len(pending_generations),
            "success": 0,
            "failed": 0,
            "validation_error": 0,
            "skipped_no_config": 0,
        }

        errors = []

        for i, generation in enumerate(pending_generations, 1):
            logger.info(f"\n[{i}/{len(pending_generations)}] Processing generation {generation.id}")

            try:
                # Get the project to access generation_structure and label_config
                response_gen = (
                    db.query(DBResponseGeneration)
                    .filter(DBResponseGeneration.id == generation.generation_id)
                    .first()
                )

                if not response_gen:
                    logger.warning(
                        f"  ⚠️ No ResponseGeneration found for generation {generation.id}"
                    )
                    stats["skipped_no_config"] += 1
                    continue

                # Get the project via task (response_gen has task_id, not project_id in workers)
                from project_models import Task

                task = db.query(Task).filter(Task.id == response_gen.task_id).first()

                if not task:
                    logger.warning(f"  ⚠️ Task not found for generation {generation.id}")
                    stats["skipped_no_config"] += 1
                    continue

                project = db.query(Project).filter(Project.id == task.project_id).first()

                if not project:
                    logger.warning(f"  ⚠️ Project not found for generation {generation.id}")
                    stats["skipped_no_config"] += 1
                    continue

                # Get generation_structure (may be in generation_config.prompt_structures)
                generation_structure = None
                if response_gen.structure_key and project.generation_config:
                    prompt_structures = project.generation_config.get("prompt_structures", {})
                    generation_structure = prompt_structures.get(response_gen.structure_key)

                if not generation_structure or not project.label_config:
                    logger.info(f"  ℹ️ No generation_structure or label_config - skipping")
                    stats["skipped_no_config"] += 1
                    continue

                # Parse the response
                logger.info(f"  🔍 Parsing response ({len(generation.response_content)} chars)")
                parser = ResponseParser(
                    generation_structure=generation_structure,
                    label_config=project.label_config,
                )
                # Pass source text for span position calculation (Issue #964)
                task_data = task.data if task.data else {}
                source_text = task_data.get("text") if isinstance(task_data, dict) else None
                parse_result = parser.parse(generation.response_content, source_text=source_text)

                # Update generation with parse results
                generation.parse_status = parse_result.status
                generation.parse_error = parse_result.error
                generation.parsed_annotation = parse_result.parsed_annotation
                generation.parse_metadata = {
                    "retry_count": 1,
                    "last_attempt": datetime.now().isoformat(),
                    "parsed_by_script": True,
                    "max_retries_reached": False,
                }

                # Update status based on parse result
                if parse_result.status == "success":
                    generation.status = "completed"
                    stats["success"] += 1
                    logger.info(
                        f"  ✅ Parse successful - {len(parse_result.parsed_annotation)} fields"
                    )
                elif parse_result.status == "validation_error":
                    stats["validation_error"] += 1
                    logger.warning(f"  ⚠️ Validation error: {parse_result.error}")
                    errors.append(
                        {
                            "generation_id": generation.id,
                            "error_type": "validation_error",
                            "error": parse_result.error,
                        }
                    )
                else:
                    stats["failed"] += 1
                    logger.warning(f"  ❌ Parse failed: {parse_result.error}")
                    errors.append(
                        {
                            "generation_id": generation.id,
                            "error_type": "failed",
                            "error": parse_result.error,
                        }
                    )

            except Exception as e:
                logger.error(f"  ❌ Exception processing generation {generation.id}: {str(e)}")
                stats["failed"] += 1
                errors.append(
                    {
                        "generation_id": generation.id,
                        "error_type": "exception",
                        "error": str(e),
                    }
                )
                continue

        # Commit or rollback
        if dry_run:
            logger.info("\n🔄 DRY RUN - Rolling back changes")
            db.rollback()
        else:
            logger.info("\n💾 Committing changes to database")
            db.commit()

        # Print statistics
        logger.info("\n" + "=" * 60)
        logger.info("PARSING STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total processed:       {stats['total']}")
        logger.info(
            f"✅ Success:            {stats['success']} ({stats['success']/stats['total']*100:.1f}%)"
        )
        logger.info(
            f"❌ Failed:             {stats['failed']} ({stats['failed']/stats['total']*100:.1f}%)"
        )
        logger.info(
            f"⚠️  Validation errors: {stats['validation_error']} ({stats['validation_error']/stats['total']*100:.1f}%)"
        )
        logger.info(f"ℹ️  Skipped (no config): {stats['skipped_no_config']}")
        logger.info("=" * 60)

        # Print error summary
        if errors:
            logger.info(f"\n📋 ERROR SUMMARY ({len(errors)} errors):")
            error_counts = {}
            for error in errors:
                error_msg = error["error"][:100]  # First 100 chars
                error_counts[error_msg] = error_counts.get(error_msg, 0) + 1

            for error_msg, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[
                :5
            ]:
                logger.info(f"  • [{count}x] {error_msg}")

        return stats, errors

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse existing LLM generations")
    parser.add_argument("--limit", type=int, help="Limit number of generations to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't commit changes")

    args = parser.parse_args()

    logger.info("🚀 Starting parse of existing generations")
    parse_existing_generations(limit=args.limit, dry_run=args.dry_run)
    logger.info("\n✅ Done!")
