#!/usr/bin/env python3
"""
Setup test project with radio button and text input annotations
Demonstrates Label Studio-style configuration with Choices and TextArea components
"""

import os
import sys
import uuid
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import relationships properly
import models  # This ensures all model relationships are loaded
from database import SessionLocal
from models import Organization, User
from project_models import Project, Task


def setup_test_annotation_project():
    """Create a test project with radio button and text area annotations"""
    db = SessionLocal()

    try:
        # Check environment
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment == "production":
            print("🔒 Production environment detected - skipping test setup")
            return

        print("📝 Setting up test annotation project...")

        # Get admin user and organization
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            print("❌ Admin user not found. Please run setup_demo_users.py first")
            return

        test_org = db.query(Organization).filter(Organization.name == "Test Organization").first()
        if not test_org:
            print("❌ Test Organization not found. Please run setup_demo_org.py first")
            return

        # Define label configuration with radio button (Yes/No) and text area
        label_config = """<View>
  <Text name="document" value="$document_text" showLabel="true"/>
  
  <View style="margin-top: 24px; padding: 16px; background-color: #f7f7f7; border-radius: 8px">
    <Header value="Legal Analysis" level="3"/>
    
    <Choices 
      name="is_relevant" 
      toName="document"
      label="Is this document legally relevant?"
      choice="single"
      required="true"
      layout="horizontal"
    >
      <Choice value="Yes" selected="false"/>
      <Choice value="No" selected="false"/>
    </Choices>
    
    <TextArea 
      name="legal_justification" 
      toName="document"
      label="Legal Justification"
      placeholder="Please explain your decision with reference to applicable legal principles..."
      rows="4"
      required="true"
      hint="Provide specific legal reasoning for your assessment"
    />
    
    <Choices 
      name="confidence_level" 
      toName="document"
      label="How confident are you in this assessment?"
      choice="single"
      required="false"
      layout="vertical"
    >
      <Choice value="Very Confident"/>
      <Choice value="Somewhat Confident"/>
      <Choice value="Not Confident"/>
    </Choices>
    
    <TextArea 
      name="additional_notes" 
      toName="document"
      label="Additional Notes (Optional)"
      placeholder="Any other observations or considerations..."
      rows="3"
      required="false"
    />
  </View>
</View>"""

        # Create project
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            title="Radio Button & Text Input Test",
            description="Test project demonstrating radio button (Yes/No) and text input annotations",
            created_by=admin_user.id,
            organization_id=test_org.id,
            label_config=label_config,
            expert_instruction="""Please review each document and determine:
1. Whether the document is legally relevant (Yes/No)
2. Provide a clear justification for your decision
3. Optionally indicate your confidence level
4. Add any additional notes if necessary

Focus on accuracy and provide concise but thorough legal reasoning.""",
            show_instruction=True,
            show_skip_button=True,
            enable_empty_annotation=False,
            # Note: Several columns removed in migrations 411540fa6c40 and 95726e4be27e
            # show_annotation_history=True,  # Removed
            # show_ground_truth_first=False,  # Removed
            # show_overlap_first=False,  # Removed
            # overlap_cohort_percentage=0,  # Removed
            maximum_annotations=3,
            min_annotations_per_task=1,
            assignment_mode="open",
            show_submit_button=True,
            require_comment_on_skip=False,
            # sampling="SEQUENTIAL",  # Removed
            is_published=True,
            created_at=datetime.utcnow(),
        )

        db.add(project)
        db.commit()
        print(f"✅ Created project: {project.title}")

        # Create sample tasks with legal documents
        sample_tasks = [
            {
                "document_text": """Contract Clause 5.2: The parties agree that any disputes arising from this agreement 
shall be resolved through binding arbitration in accordance with the rules of the American Arbitration Association. 
The arbitration shall take place in New York, NY, and the arbitrator's decision shall be final and binding upon both parties."""
            },
            {
                "document_text": """Email from John Smith to Jane Doe (March 15, 2024):
"Hey Jane, just wanted to remind you about the team lunch tomorrow at 12:30pm. We're going to the Italian place 
downtown. Let me know if you can make it!" """
            },
            {
                "document_text": """Section 12 of the Employment Agreement: The Employee acknowledges that during the term 
of employment and for a period of two (2) years thereafter, the Employee shall not directly or indirectly engage in 
any business that competes with the Company within a 50-mile radius of any Company location."""
            },
            {
                "document_text": """Court Opinion Excerpt: "The defendant's motion to dismiss is hereby DENIED. 
The plaintiff has sufficiently alleged facts that, if proven true, would establish a breach of fiduciary duty. 
The case shall proceed to discovery." - Judge Patricia Williams, District Court"""
            },
            {
                "document_text": """Product Review from customer: "This coffee maker works great! Makes coffee quickly 
and keeps it hot for hours. The timer function is very convenient. Would definitely recommend to others." - 5 stars"""
            },
        ]

        # Create tasks
        for idx, task_data in enumerate(sample_tasks, 1):
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project_id,
                data=task_data,
                meta={
                    "source": "test_data",
                    "created_for": "annotation_testing",
                    "task_number": idx,
                },
                created_by=admin_user.id,
                is_labeled=False,
                total_annotations=0,
                cancelled_annotations=0,
                inner_id=idx,
                created_at=datetime.utcnow(),
            )
            db.add(task)

        db.commit()
        print(f"✅ Created {len(sample_tasks)} sample tasks")

        print("\n🎉 Test annotation project setup complete!")
        print(f"\nProject Details:")
        print(f"  - Title: {project.title}")
        print(f"  - ID: {project_id}")
        print(f"  - Tasks: {len(sample_tasks)}")
        print(f"  - Organization: {test_org.name}")
        print(f"\nLabel Configuration Features:")
        print("  - Radio Button (Yes/No) for relevance assessment")
        print("  - Required text area for legal justification")
        print("  - Optional confidence level selection")
        print("  - Optional additional notes field")
        print(f"\n📌 Access the project at: http://benger.localhost/projects/{project_id}")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    setup_test_annotation_project()
