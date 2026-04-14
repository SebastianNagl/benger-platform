#!/usr/bin/env python3
"""
Complete initialization script for BenGER development environment.
Run this to set up the entire database with all required data.

Usage: docker-compose exec api python init_complete.py
"""

import os
import sys
import uuid

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from datetime import datetime, timezone
from decimal import Decimal

from database import SessionLocal
from scripts.setup_demo_org import setup_demo_organization
from user_service import init_demo_users


def complete_mandatory_profiles(db):
    """Fill in mandatory profile fields for all demo users so E2E tests aren't
    redirected to the profile page after login.

    Checks actual field completeness via get_mandatory_profile_fields() rather
    than trusting the mandatory_profile_completed boolean flag.
    """
    from models import User
    from auth_module.user_service import _complete_demo_user_profile

    users = db.query(User).all()
    completed_count = 0

    for user in users:
        if _complete_demo_user_profile(db, user):
            completed_count += 1

    db.commit()
    print(f"✅ Mandatory profile fields set for {completed_count}/{len(users)} demo users")


def setup_e2e_test_data(db):
    """Create test data required for E2E tests"""
    from models import Organization, User
    from project_models import Project, ProjectOrganization, Task

    # Get admin user and TUM organization
    admin = db.query(User).filter(User.email == "admin@example.com").first()
    tum_org = db.query(Organization).filter(Organization.name == "TUM").first()

    if not admin or not tum_org:
        print("⚠️  Admin user or TUM organization not found, skipping E2E test data")
        return

    # Check if Test AGG project already exists
    existing = db.query(Project).filter(Project.title == "Test AGG").first()
    if existing:
        print("✅ Test AGG project already exists")
        return

    # Create Test AGG project
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        title="Test AGG",
        description="Test project for E2E automated testing",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/><Choices name="sentiment" toName="text"><Choice value="positive"/><Choice value="negative"/><Choice value="neutral"/></Choices></View>',
    )
    db.add(project)

    # Link project to TUM organization
    project_org = ProjectOrganization(
        id=str(uuid.uuid4()),
        project_id=project_id,
        organization_id=tum_org.id,
        assigned_by=admin.id,
    )
    db.add(project_org)

    # Add sample tasks
    sample_data = [
        {"text": "This is a great product! I love it.", "expected": "positive"},
        {"text": "Terrible service, very disappointed.", "expected": "negative"},
        {"text": "The weather is cloudy today.", "expected": "neutral"},
        {"text": "Amazing experience, highly recommend!", "expected": "positive"},
        {"text": "Not worth the money, waste of time.", "expected": "negative"},
    ]

    for i, data in enumerate(sample_data):
        task = Task(
            id=str(uuid.uuid4()),
            project_id=project_id,
            data=data,
            is_labeled=False,
            inner_id=i + 1,
        )
        db.add(task)

    db.commit()
    print(f"✅ Created Test AGG project with {len(sample_data)} sample tasks")


def setup_e2e_projects(db):
    """Create additional E2E test projects covering all annotation types"""
    from datetime import datetime

    from models import Organization, User
    from project_models import Annotation, Project, ProjectOrganization, Task

    admin = db.query(User).filter(User.email == "admin@example.com").first()
    contributor = db.query(User).filter(User.email == "contributor@example.com").first()
    annotator = db.query(User).filter(User.email == "annotator@example.com").first()
    annotator2 = db.query(User).filter(User.email == "annotator2@example.com").first()
    tum_org = db.query(Organization).filter(Organization.name == "TUM").first()

    if not all([admin, contributor, annotator, tum_org]):
        print("⚠️  Required users/org not found, skipping E2E projects")
        return

    # Label configs for different annotation types
    LABEL_CONFIGS = {
        "qa": """<View>
  <Header value="Question"/>
  <Text name="question" value="$question"/>
  <Header value="Your Answer"/>
  <TextArea name="answer" toName="question" rows="4"/>
</View>""",
        "ner": """<View>
  <Labels name="label" toName="text">
    <Label value="PERSON" background="#FF6B6B"/>
    <Label value="ORG" background="#4ECDC4"/>
    <Label value="LOC" background="#96CEB4"/>
    <Label value="DATE" background="#45B7D1"/>
  </Labels>
  <Text name="text" value="$text"/>
</View>""",
        "multichoice": """<View>
  <Text name="text" value="$text"/>
  <Choices name="categories" toName="text" choice="multiple">
    <Choice value="Legal"/>
    <Choice value="Technical"/>
    <Choice value="Administrative"/>
    <Choice value="Financial"/>
  </Choices>
</View>""",
        "rating": """<View>
  <Text name="text" value="$text"/>
  <Rating name="quality" toName="text" maxRating="5"/>
</View>""",
        "numeric": """<View>
  <Text name="text" value="$text"/>
  <Number name="confidence" toName="text" min="0" max="100"/>
</View>""",
    }

    # Project definitions
    projects_to_create = [
        {
            "title": "E2E QA Project",
            "description": "Question answering project for E2E testing",
            "label_config": LABEL_CONFIGS["qa"],
            "tasks": [
                {"question": "What are the legal requirements for forming a GmbH?"},
                {"question": "How does German contract law handle breach of contract?"},
                {"question": "What is the statute of limitations for tort claims?"},
                {"question": "What rights do employees have under German labor law?"},
                {"question": "How are intellectual property rights protected in Germany?"},
            ],
            "annotation_type": "textarea",
        },
        {
            "title": "E2E NER Project",
            "description": "Named entity recognition project for E2E testing",
            "label_config": LABEL_CONFIGS["ner"],
            "tasks": [
                {"text": "Dr. Hans Mueller works at BMW in Munich since January 2020."},
                {"text": "The contract between Siemens AG and Deutsche Bank was signed in Berlin."},
                {"text": "Maria Schmidt filed a lawsuit in Frankfurt on March 15, 2023."},
                {"text": "The merger of Daimler and Chrysler was announced in Stuttgart."},
                {"text": "Professor Weber from LMU Munich published the research in September."},
            ],
            "annotation_type": "labels",
        },
        {
            "title": "E2E Multi-Choice Project",
            "description": "Multi-label classification project for E2E testing",
            "label_config": LABEL_CONFIGS["multichoice"],
            "tasks": [
                {"text": "The new tax regulations affect corporate compliance and reporting."},
                {"text": "This software update requires IT approval and user training."},
                {"text": "The merger requires regulatory approval and shareholder consent."},
                {"text": "Budget allocation for the project needs finance and legal review."},
                {"text": "Employee benefits package requires HR and legal coordination."},
            ],
            "annotation_type": "choices",
        },
        {
            "title": "E2E Rating Project",
            "description": "Quality rating project for E2E testing",
            "label_config": LABEL_CONFIGS["rating"],
            "tasks": [
                {"text": "The legal analysis provided was comprehensive and well-researched."},
                {"text": "The response time for the query was acceptable but could improve."},
                {"text": "Documentation quality meets professional standards."},
                {"text": "The argument structure was clear and logical."},
                {"text": "Overall service delivery exceeded expectations."},
            ],
            "annotation_type": "rating",
        },
        {
            "title": "E2E Numeric Project",
            "description": "Confidence scoring project for E2E testing",
            "label_config": LABEL_CONFIGS["numeric"],
            "tasks": [
                {"text": "Based on precedent, the case has a strong chance of success."},
                {"text": "The risk assessment indicates moderate exposure."},
                {"text": "Compliance likelihood with new regulations is high."},
                {"text": "The contract terms are somewhat favorable to our client."},
                {"text": "Settlement probability in this dispute is uncertain."},
            ],
            "annotation_type": "number",
        },
    ]

    # Get all annotators for creating mock annotations
    annotators = [admin, contributor, annotator]
    if annotator2:
        annotators.append(annotator2)

    for proj_def in projects_to_create:
        # Check if project already exists
        existing = db.query(Project).filter(Project.title == proj_def["title"]).first()
        if existing:
            print(f"✅ {proj_def['title']} already exists")
            continue

        # Create project
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            title=proj_def["title"],
            description=proj_def["description"],
            created_by=admin.id,
            label_config=proj_def["label_config"],
        )
        db.add(project)

        # Link to TUM organization
        project_org = ProjectOrganization(
            id=str(uuid.uuid4()),
            project_id=project_id,
            organization_id=tum_org.id,
            assigned_by=admin.id,
        )
        db.add(project_org)

        # Create tasks
        task_ids = []
        for i, task_data in enumerate(proj_def["tasks"]):
            task_id = str(uuid.uuid4())
            task = Task(
                id=task_id,
                project_id=project_id,
                data=task_data,
                is_labeled=False,
                inner_id=i + 1,
            )
            db.add(task)
            task_ids.append(task_id)

        db.flush()  # Ensure tasks are created before annotations

        # Create overlapping annotations for IAA testing
        # Task 1: admin, contributor
        # Task 2: admin, contributor, annotator
        # Task 3: admin, contributor, annotator, annotator2
        # Task 4: contributor, annotator, annotator2
        # Task 5: annotator, annotator2
        annotation_matrix = [
            [admin, contributor],
            [admin, contributor, annotator],
            annotators,  # All annotators
            [contributor, annotator] + ([annotator2] if annotator2 else []),
            [annotator] + ([annotator2] if annotator2 else []),
        ]

        for task_idx, task_id in enumerate(task_ids):
            users_to_annotate = annotation_matrix[task_idx]
            for user in users_to_annotate:
                annotation_result = create_mock_annotation_result(
                    proj_def["annotation_type"], task_idx, user.username
                )
                annotation = Annotation(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    project_id=project_id,
                    completed_by=user.id,
                    result=annotation_result,
                    was_cancelled=False,
                    ground_truth=False,
                    created_at=datetime.utcnow(),
                )
                db.add(annotation)

        # Update task is_labeled status
        for task_id in task_ids:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.is_labeled = True

        db.commit()
        print(f"✅ Created {proj_def['title']} with {len(proj_def['tasks'])} tasks and annotations")


def create_mock_annotation_result(annotation_type, task_idx, username):
    """Create mock annotation results in Label Studio format"""
    if annotation_type == "textarea":
        answers = [
            "A GmbH requires minimum share capital of €25,000 and notarized articles.",
            "German contract law provides remedies including damages and rescission.",
            "Standard statute of limitations is 3 years under BGB § 195.",
            "Employees have rights to paid leave, notice periods, and works councils.",
            "IP is protected through patents, trademarks, and copyright under German law.",
        ]
        return [
            {
                "from_name": "answer",
                "to_name": "question",
                "type": "textarea",
                "value": {"text": [f"{answers[task_idx]} (Annotated by {username})"]},
            }
        ]
    elif annotation_type == "labels":
        # NER spans for each text
        spans = [
            [
                {"start": 4, "end": 15, "text": "Hans Mueller", "labels": ["PERSON"]},
                {"start": 26, "end": 29, "text": "BMW", "labels": ["ORG"]},
                {"start": 33, "end": 39, "text": "Munich", "labels": ["LOC"]},
                {"start": 46, "end": 58, "text": "January 2020", "labels": ["DATE"]},
            ],
            [
                {"start": 21, "end": 31, "text": "Siemens AG", "labels": ["ORG"]},
                {"start": 36, "end": 50, "text": "Deutsche Bank", "labels": ["ORG"]},
                {"start": 66, "end": 72, "text": "Berlin", "labels": ["LOC"]},
            ],
            [
                {"start": 0, "end": 13, "text": "Maria Schmidt", "labels": ["PERSON"]},
                {"start": 34, "end": 43, "text": "Frankfurt", "labels": ["LOC"]},
                {"start": 47, "end": 61, "text": "March 15, 2023", "labels": ["DATE"]},
            ],
            [
                {"start": 14, "end": 21, "text": "Daimler", "labels": ["ORG"]},
                {"start": 26, "end": 34, "text": "Chrysler", "labels": ["ORG"]},
                {"start": 52, "end": 61, "text": "Stuttgart", "labels": ["LOC"]},
            ],
            [
                {"start": 0, "end": 14, "text": "Professor Weber", "labels": ["PERSON"]},
                {"start": 20, "end": 30, "text": "LMU Munich", "labels": ["ORG"]},
                {"start": 62, "end": 71, "text": "September", "labels": ["DATE"]},
            ],
        ]
        return [
            {"from_name": "label", "to_name": "text", "type": "labels", "value": span}
            for span in spans[task_idx]
        ]
    elif annotation_type == "choices":
        choices_per_task = [
            ["Legal", "Administrative"],
            ["Technical", "Administrative"],
            ["Legal", "Financial"],
            ["Financial", "Administrative"],
            ["Legal", "Administrative"],
        ]
        return [
            {
                "from_name": "categories",
                "to_name": "text",
                "type": "choices",
                "value": {"choices": choices_per_task[task_idx]},
            }
        ]
    elif annotation_type == "rating":
        # Vary ratings slightly by user
        base_ratings = [5, 3, 4, 4, 5]
        rating = base_ratings[task_idx]
        # Add some variation based on username
        if "annotator" in username:
            rating = max(1, min(5, rating + (hash(username) % 3 - 1)))
        return [
            {
                "from_name": "quality",
                "to_name": "text",
                "type": "rating",
                "value": {"rating": rating},
            }
        ]
    elif annotation_type == "number":
        # Confidence scores with variation
        base_scores = [85, 60, 75, 65, 50]
        score = base_scores[task_idx]
        # Add variation based on username
        if "annotator" in username:
            score = max(0, min(100, score + (hash(username) % 21 - 10)))
        return [
            {
                "from_name": "confidence",
                "to_name": "text",
                "type": "number",
                "value": {"number": score},
            }
        ]
    return []


def setup_e2e_generations(db):
    """Create mock LLM generation data for evaluation testing

    Creates proper Generation records in the database with parsed annotations
    that can be used for evaluation.
    """
    from datetime import datetime

    from models import Generation, ResponseGeneration, User
    from project_models import Project, Task

    admin = db.query(User).filter(User.email == "admin@example.com").first()
    qa_project = db.query(Project).filter(Project.title == "E2E QA Project").first()

    if not admin or not qa_project:
        print("⚠️  Admin or QA project not found, skipping generation data")
        return

    tasks = db.query(Task).filter(Task.project_id == qa_project.id).order_by(Task.inner_id).all()
    if not tasks:
        print("⚠️  No tasks found in QA project, skipping generation data")
        return

    # Check if generations already exist
    existing_gen = db.query(Generation).filter(Generation.task_id == tasks[0].id).first()
    if existing_gen:
        print("✅ E2E generation data already exists")
        return

    # Mock LLM responses for each task
    mock_responses = {
        "gpt-4-turbo": [
            "To form a GmbH, you need minimum capital of €25,000, notarized articles of association, and registration in the commercial register.",
            "Under German contract law (BGB), breach of contract allows the aggrieved party to claim damages, demand performance, or rescind the contract.",
            "The general limitation period for tort claims in Germany is 3 years from knowledge of the claim (§195 BGB).",
            "German labor law provides employees with rights including paid annual leave (24+ days), notice periods, protection against unfair dismissal, and works council participation.",
            "IP rights in Germany are protected through the Patent Act, Trademark Act, Copyright Act, and EU regulations for designs.",
        ],
        "claude-3-sonnet": [
            "A GmbH formation requires: (1) €25,000 minimum capital, (2) notarized founding documents, (3) commercial register entry, and (4) business address in Germany.",
            "German contract law addresses breach through: specific performance claims, damage compensation under §§280ff BGB, and contract termination rights.",
            "Tort claims in Germany have a standard 3-year limitation starting from year-end when the claim arose and the claimant had knowledge.",
            "Key employee rights include: 4+ weeks paid leave, statutory notice periods, dismissal protection after 6 months, and collective bargaining participation.",
            "Germany protects IP via: patents (20 years), trademarks (renewable 10-year terms), copyright (author's life + 70 years), and utility models.",
        ],
        "gemini-pro": [
            "GmbH formation: Need €25k capital, notarized articles, commercial register entry. Managing director required.",
            "Contract breach in BGB: Claims for damages (§280), specific performance, or rescission (§323) available.",
            "Tort limitation: 3 years from end of year when claim arose and claimant knew (§195, §199 BGB).",
            "Employee rights: Min 20 days leave, notice periods (§622 BGB), dismissal protection (KSchG), works council rights.",
            "IP protection: PatG for patents, MarkenG for trademarks, UrhG for copyright, DesignG for designs.",
        ],
    }

    # Create ResponseGeneration (parent job) and Generation records for each model
    for model_id, responses in mock_responses.items():
        # Create parent ResponseGeneration job
        response_gen_id = str(uuid.uuid4())
        response_gen = ResponseGeneration(
            id=response_gen_id,
            project_id=qa_project.id,
            model_id=model_id,
            status="completed",
            responses_generated=len(responses),
            created_by=admin.id,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(response_gen)

        # Create individual Generation records
        for i, task in enumerate(tasks):
            if i >= len(responses):
                break

            generation_id = str(uuid.uuid4())
            generation = Generation(
                id=generation_id,
                generation_id=response_gen_id,
                task_id=task.id,
                model_id=model_id,
                case_data=str(task.data),
                response_content=responses[i],
                status="completed",
                parse_status="success",
                parsed_annotation=[
                    {
                        "from_name": "answer",
                        "to_name": "question",
                        "type": "textarea",
                        "value": {"text": [responses[i]]},
                    }
                ],
                usage_stats={"prompt_tokens": 50, "completion_tokens": len(responses[i].split())},
                created_at=datetime.utcnow(),
            )
            db.add(generation)

    db.commit()
    print(
        f"✅ Created mock generation data for E2E QA Project ({len(mock_responses)} models × {len(tasks)} tasks)"
    )


def _get_e2e_evaluation_config():
    """Return the evaluation config for E2E QA Project"""
    return {
        "selected_methods": {
            "answer": {
                "automated": ["llm_judge_custom"],
                "human": [],
                "field_mapping": {"prediction_field": "answer", "reference_field": "answer"},
            }
        },
        "evaluation_configs": [
            {
                "id": "e2e-llm-judge",
                "metric": "llm_judge_custom",
                "display_name": "LLM Judge Quality",
                "metric_parameters": {},
                "prediction_fields": ["answer"],
                "reference_fields": ["answer"],
                "enabled": True,
            }
        ],
    }


def setup_e2e_evaluations(db):
    """Create mock evaluation data with sample results for E2E testing

    Creates EvaluationRun and TaskEvaluation records that can be
    used to test the evaluation results display.
    """
    from datetime import datetime

    from models import EvaluationRun, TaskEvaluation, Generation, User
    from project_models import Project, Task

    admin = db.query(User).filter(User.email == "admin@example.com").first()
    qa_project = db.query(Project).filter(Project.title == "E2E QA Project").first()

    if not admin or not qa_project:
        print("⚠️  Admin or QA project not found, skipping evaluation data")
        return

    # Check if evaluations already exist
    existing_eval = db.query(EvaluationRun).filter(EvaluationRun.project_id == qa_project.id).first()
    if existing_eval:
        # Still ensure evaluation_config is set even if data exists
        if not qa_project.evaluation_config or not qa_project.evaluation_config.get(
            "evaluation_configs"
        ):
            qa_project.evaluation_config = _get_e2e_evaluation_config()
            db.commit()
            print("✅ E2E evaluation data already exists, updated config")
        else:
            print("✅ E2E evaluation data already exists")
        return

    tasks = db.query(Task).filter(Task.project_id == qa_project.id).order_by(Task.inner_id).all()
    if not tasks:
        print("⚠️  No tasks found in QA project, skipping evaluation data")
        return

    # Get all generations for this project
    task_ids = [t.id for t in tasks]
    generations = db.query(Generation).filter(Generation.task_id.in_(task_ids)).all()

    if not generations:
        print("⚠️  No generations found, skipping evaluation data")
        return

    # Group generations by model
    generations_by_model = {}
    for gen in generations:
        if gen.model_id not in generations_by_model:
            generations_by_model[gen.model_id] = {}
        generations_by_model[gen.model_id][gen.task_id] = gen

    # Predetermined scores for each model (for predictable testing)
    model_scores = {
        "gpt-4-turbo": [0.85, 0.90, 0.78, 0.88, 0.82],  # Mean: 0.846
        "claude-3-sonnet": [0.82, 0.88, 0.75, 0.85, 0.80],  # Mean: 0.82
        "gemini-pro": [0.70, 0.75, 0.65, 0.72, 0.68],  # Mean: 0.70
    }

    # Create evaluation for each model
    for model_id, scores in model_scores.items():
        if model_id not in generations_by_model:
            continue

        model_gens = generations_by_model[model_id]
        avg_score = sum(scores[: len(tasks)]) / len(tasks)

        # Create Evaluation record
        evaluation_id = str(uuid.uuid4())
        evaluation = EvaluationRun(
            id=evaluation_id,
            project_id=qa_project.id,
            model_id=model_id,
            evaluation_type_ids=["llm_judge_custom"],
            metrics={
                "llm_judge_custom": {
                    "mean": avg_score,
                    "std": 0.05,
                    "min": min(scores[: len(tasks)]),
                    "max": max(scores[: len(tasks)]),
                    "count": len(tasks),
                }
            },
            status="completed",
            samples_evaluated=len(tasks),
            has_sample_results=True,
            created_by=admin.id,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        db.add(evaluation)

        # Create TaskEvaluation for each task
        for i, task in enumerate(tasks):
            if i >= len(scores):
                break

            gen = model_gens.get(task.id)
            if not gen:
                continue

            score = scores[i]
            sample_result = TaskEvaluation(
                id=str(uuid.uuid4()),
                evaluation_id=evaluation_id,
                task_id=task.id,
                generation_id=gen.id,
                field_name="answer",
                answer_type="textarea",
                ground_truth={"text": "Reference answer"},
                prediction={"text": gen.response_content},
                metrics={
                    "llm_judge_custom": score,
                    "score": score,
                },
                passed=score >= 0.5,
                confidence_score=score,
                created_at=datetime.utcnow(),
            )
            db.add(sample_result)

    # Update project's evaluation_config so UI shows the results
    # This enables the evaluations dashboard to display results
    qa_project.evaluation_config = _get_e2e_evaluation_config()

    db.commit()
    print(f"✅ Created mock evaluation data for E2E QA Project ({len(model_scores)} models)")
    print(f"✅ Configured evaluation settings for E2E QA Project")


def setup_user_api_keys(db):
    """Setup user API keys from environment variables for E2E testing"""
    from models import User

    # Add shared services to path
    sys.path.append('/shared')
    from encryption_service import encryption_service
    from user_api_key_service import create_user_api_key_service

    user_api_key_service = create_user_api_key_service(encryption_service)

    # Get admin user
    admin = db.query(User).filter(User.email == "admin@example.com").first()
    if not admin:
        print("⚠️  Admin user not found, skipping API key setup")
        return

    # Map of environment variables to provider names
    api_key_mappings = {
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "GOOGLE_API_KEY": "google",
        "DEEPINFRA_API_KEY": "deepinfra",
    }

    keys_set = []
    for env_var, provider in api_key_mappings.items():
        api_key = os.environ.get(env_var)
        if api_key and api_key.strip():
            try:
                success = user_api_key_service.set_user_api_key(db, admin.id, provider, api_key)
                if success:
                    keys_set.append(provider)
                    print(f"✅ Set {provider} API key for admin user")
            except Exception as e:
                print(f"⚠️  Failed to set {provider} API key: {e}")

    if keys_set:
        print(f"✅ User API keys configured: {', '.join(keys_set)}")
    else:
        print("ℹ️  No API keys found in environment variables")


def main():
    """Initialize database with tables, demo users, organization, and feature flags"""
    print("🚀 BenGER Complete Database Initialization")
    print("=" * 50)

    try:
        # Create tables using Alembic
        print("\n📋 Step 1: Applying database migrations...")
        import subprocess

        result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"⚠️  Migrations may already be applied: {result.stderr}")
        else:
            print("✅ Database migrations applied successfully!")

        # Create demo users (admin, contributor, annotator, etc.)
        print("\n👥 Step 2: Creating demo users...")
        db = SessionLocal()
        try:
            init_demo_users(db)
            print("✅ Demo users created successfully!")
            print("   - admin/admin (Superadmin)")
            print("   - org_admin/admin (Organization Admin)")
            print("   - contributor/admin (Contributor)")
            print("   - annotator/admin (Annotator)")
            print("   - annotator2/admin (Annotator 2)")
            print("   - annotator3/admin (Annotator 3)")
            print("   - basicuser/admin (Basic User - no org role)")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("✅ Demo users already exist")
            else:
                raise e
        finally:
            db.close()

        # Complete mandatory profile fields for demo users
        print("\n📝 Step 2b: Setting mandatory profile fields for demo users...")
        db = SessionLocal()
        try:
            complete_mandatory_profiles(db)
        finally:
            db.close()

        # Setup organization and feature flags
        print("\n🏢 Step 3: Setting up TUM organization and feature flags...")
        setup_demo_organization()

        # E2E test data (Steps 4-7) only in test/e2e environments
        environment = os.getenv("ENVIRONMENT", "development").lower()
        is_test_env = environment in ("test", "e2e")

        if is_test_env:
            # Setup E2E test data (Test AGG project)
            print("\n🧪 Step 4: Setting up E2E test data...")
            db = SessionLocal()
            try:
                setup_e2e_test_data(db)
            finally:
                db.close()

            # Setup additional E2E projects with annotations
            print("\n📦 Step 5: Setting up E2E projects with mock annotations...")
            db = SessionLocal()
            try:
                setup_e2e_projects(db)
            finally:
                db.close()

            # Setup mock generation data
            print("\n🤖 Step 6: Setting up mock generation data...")
            db = SessionLocal()
            try:
                setup_e2e_generations(db)
            finally:
                db.close()

            # Setup mock evaluation data
            print("\n📊 Step 7: Setting up mock evaluation data...")
            db = SessionLocal()
            try:
                setup_e2e_evaluations(db)
            finally:
                db.close()
        else:
            print("\n--- Skipping E2E test data (not a test environment) ---")

        # Setup user API keys from environment variables
        print("\n🔑 Step 8: Setting up user API keys from environment...")
        db = SessionLocal()
        try:
            setup_user_api_keys(db)
        finally:
            db.close()

        # Summary
        print("\n" + "=" * 50)
        print("🎉 Complete initialization successful!")
        print("\n📊 Summary:")
        print("✅ Database tables created")
        print(
            "✅ Demo users created (admin, org_admin, contributor, annotator, annotator2, annotator3, basicuser)"
        )
        print("✅ Mandatory profile fields completed for all demo users")
        print("✅ TUM organization created with members (basicuser has no org role)")
        if is_test_env:
            print("✅ E2E test projects created:")
            print("   - Test AGG (Sentiment Classification)")
            print("   - E2E QA Project (TextArea)")
            print("   - E2E NER Project (Labels/Spans)")
            print("   - E2E Multi-Choice Project (Choices)")
            print("   - E2E Rating Project (Rating)")
            print("   - E2E Numeric Project (Number)")
            print("✅ Mock annotations created by multiple users")
            print("✅ Mock generation data created (3 models x 5 tasks)")
            print("✅ Mock evaluation data created with sample results")
        print("✅ Feature flags enabled:")
        print("   - reports")
        print("   - data")
        print("   - generations")
        print("   - evaluations")
        print("   - how-to")
        print("   - leaderboards")
        print("\n🚀 You can now access the application at:")
        print("   http://benger.localhost")
        print("   Login: admin/admin")

    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
