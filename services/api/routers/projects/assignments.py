"""Task assignment endpoints for projects."""

import random
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from auth_module import require_user
from auth_module.models import User as AuthUser
from database import get_db
from models import NotificationType, OrganizationMembership, User
from notification_service import NotificationService
from project_models import Annotation, FeedbackComment, Project, ProjectMember, ProjectOrganization, Task, TaskAssignment
from routers.projects.helpers import check_project_accessible, get_org_context_from_request, get_user_with_memberships

router = APIRouter()


@router.post("/{project_id}/tasks/assign")
async def assign_tasks(
    project_id: str,
    data: dict,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Assign tasks to users

    Request body:
    {
        "task_ids": [1, 2, 3],
        "user_ids": ["user1", "user2"],
        "distribution": "manual" | "round_robin" | "random" | "load_balanced",
        "priority": 0,
        "due_date": "2024-12-31T23:59:59Z",
        "notes": "Optional notes"
    }
    """
    # Verify project exists and user has permission
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permission - only superadmin, org admin, or contributor can assign
    user_with_memberships = get_user_with_memberships(db, current_user.id)
    user_role = None

    if current_user.is_superadmin:
        user_role = "superadmin"
    elif user_with_memberships and user_with_memberships.organization_memberships:
        # Get project organizations
        project_orgs = (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        )
        project_org_ids = [org[0] for org in project_orgs]

        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    if user_role not in ["superadmin", "ORG_ADMIN", "CONTRIBUTOR"]:
        raise HTTPException(status_code=403, detail="Only admins and contributors can assign tasks")

    task_ids = data.get("task_ids", [])
    user_ids = data.get("user_ids", [])
    distribution = data.get("distribution", "manual")
    priority = data.get("priority", 0)
    due_date = data.get("due_date")
    notes = data.get("notes")

    # Debug logging
    print(f"[ASSIGN DEBUG] Received task_ids: {task_ids}")
    print(f"[ASSIGN DEBUG] Received user_ids: {user_ids}")
    print(f"[ASSIGN DEBUG] Project ID: {project_id}")

    if not task_ids or not user_ids:
        raise HTTPException(status_code=400, detail="task_ids and user_ids are required")

    # Verify tasks exist
    tasks = db.query(Task).filter(Task.id.in_(task_ids), Task.project_id == project_id).all()

    # Debug logging
    print(f"[ASSIGN DEBUG] Found {len(tasks)} tasks in database")
    print(f"[ASSIGN DEBUG] Task IDs in DB: {[t.id for t in tasks]}")

    # Check all tasks in this project to see what IDs exist
    all_project_tasks = db.query(Task).filter(Task.project_id == project_id).all()
    print(f"[ASSIGN DEBUG] All task IDs in project: {[t.id for t in all_project_tasks]}")

    if len(tasks) != len(task_ids):
        raise HTTPException(
            status_code=400,
            detail=f"Some tasks not found in project. Requested: {task_ids}, Found: {[t.id for t in tasks]}",
        )

    # Verify users exist and are project members (direct or through organization)
    # Get direct project members
    direct_members = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id.in_(user_ids),
            ProjectMember.is_active == True,
        )
        .all()
    )

    direct_member_ids = {m.user_id for m in direct_members}

    # Get members through organizations (for users not already direct members)
    remaining_user_ids = [uid for uid in user_ids if uid not in direct_member_ids]

    if remaining_user_ids:
        project_orgs = (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .subquery()
        )

        org_members = (
            db.query(OrganizationMembership)
            .filter(
                OrganizationMembership.organization_id.in_(project_orgs),
                OrganizationMembership.user_id.in_(remaining_user_ids),
                OrganizationMembership.is_active == True,
            )
            .all()
        )
    else:
        org_members = []

    org_member_ids = {m.user_id for m in org_members}

    # Check if all users are either direct or organization members
    all_valid_member_ids = direct_member_ids | org_member_ids
    invalid_user_ids = [uid for uid in user_ids if uid not in all_valid_member_ids]

    if invalid_user_ids:
        raise HTTPException(
            status_code=400, detail=f"Users {invalid_user_ids} are not project members"
        )

    assignments_created = []
    assignments_skipped = []
    assignments_updated = []

    # Distribute tasks based on method
    if distribution == "manual":
        # Assign all tasks to all users
        for task_id in task_ids:
            for user_id in user_ids:
                # Check if assignment already exists
                existing = (
                    db.query(TaskAssignment)
                    .filter(
                        TaskAssignment.task_id == task_id,
                        TaskAssignment.user_id == user_id,
                    )
                    .first()
                )

                if not existing:
                    assignment = TaskAssignment(
                        id=str(uuid.uuid4()),
                        task_id=task_id,
                        user_id=user_id,
                        assigned_by=current_user.id,
                        priority=priority,
                        due_date=due_date,
                        notes=notes,
                        status="assigned",
                    )
                    db.add(assignment)
                    assignments_created.append(assignment)
                    print(f"[ASSIGN DEBUG] Created assignment for task {task_id} to user {user_id}")
                else:
                    # Update existing assignment if needed
                    updated = False
                    if priority and existing.priority != priority:
                        existing.priority = priority
                        updated = True
                    if due_date and existing.due_date != due_date:
                        existing.due_date = due_date
                        updated = True
                    if notes and existing.notes != notes:
                        existing.notes = notes
                        updated = True

                    if updated:
                        assignments_updated.append(existing)
                        print(
                            f"[ASSIGN DEBUG] Updated existing assignment for task {task_id} to user {user_id}"
                        )
                    else:
                        assignments_skipped.append(existing)
                        print(
                            f"[ASSIGN DEBUG] Assignment already exists for task {task_id} to user {user_id} - skipping"
                        )

    elif distribution == "round_robin":
        # Distribute tasks evenly in round-robin fashion
        user_index = 0
        for task_id in task_ids:
            user_id = user_ids[user_index % len(user_ids)]

            existing = (
                db.query(TaskAssignment)
                .filter(TaskAssignment.task_id == task_id, TaskAssignment.user_id == user_id)
                .first()
            )

            if not existing:
                assignment = TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    user_id=user_id,
                    assigned_by=current_user.id,
                    priority=priority,
                    due_date=due_date,
                    notes=notes,
                    status="assigned",
                )
                db.add(assignment)
                assignments_created.append(assignment)

            user_index += 1

    elif distribution == "random":
        # Randomly assign tasks to users
        for task_id in task_ids:
            user_id = random.choice(user_ids)

            existing = (
                db.query(TaskAssignment)
                .filter(TaskAssignment.task_id == task_id, TaskAssignment.user_id == user_id)
                .first()
            )

            if not existing:
                assignment = TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    user_id=user_id,
                    assigned_by=current_user.id,
                    priority=priority,
                    due_date=due_date,
                    notes=notes,
                    status="assigned",
                )
                db.add(assignment)
                assignments_created.append(assignment)

    elif distribution == "load_balanced":
        # Assign based on current workload (least tasks assigned)
        # Count current assignments for each user
        workload = {}
        for user_id in user_ids:
            count = (
                db.query(TaskAssignment)
                .filter(
                    TaskAssignment.user_id == user_id,
                    TaskAssignment.status.in_(["assigned", "in_progress"]),
                )
                .count()
            )
            workload[user_id] = count

        for task_id in task_ids:
            # Assign to user with least workload
            user_id = min(workload, key=workload.get)

            existing = (
                db.query(TaskAssignment)
                .filter(TaskAssignment.task_id == task_id, TaskAssignment.user_id == user_id)
                .first()
            )

            if not existing:
                assignment = TaskAssignment(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    user_id=user_id,
                    assigned_by=current_user.id,
                    priority=priority,
                    due_date=due_date,
                    notes=notes,
                    status="assigned",
                )
                db.add(assignment)
                assignments_created.append(assignment)
                workload[user_id] += 1

    db.commit()

    # Debug logging
    print(f"[ASSIGN DEBUG] Total assignments created: {len(assignments_created)}")

    # Send notifications to assigned users
    if assignments_created:
        # Group assignments by user
        user_assignments = {}
        for assignment in assignments_created:
            if assignment.user_id not in user_assignments:
                user_assignments[assignment.user_id] = []
            user_assignments[assignment.user_id].append(assignment)

        # Send notification to each user
        for user_id, user_tasks in user_assignments.items():
            task_count = len(user_tasks)
            user = db.query(User).filter(User.id == user_id).first()

            title = f"New Task Assignment"
            if task_count == 1:
                message = f"You have been assigned 1 new task in {project.title}"
            else:
                message = f"You have been assigned {task_count} new tasks in {project.title}"

            # Add priority and due date info if set
            if priority > 0:
                message += f" (Priority: {priority})"
            if due_date:
                message += f" - Due: {due_date.strftime('%Y-%m-%d')}"
            if notes:
                message += f"\nNotes: {notes}"

            NotificationService.create_notification(
                db=db,
                user_ids=[user_id],
                notification_type=NotificationType.TASK_ASSIGNED,
                title=title,
                message=message,
                data={
                    "project_id": project_id,
                    "project_title": project.title,
                    "task_ids": [a.task_id for a in user_tasks],
                    "assigned_by": current_user.name or current_user.email,
                    "priority": priority,
                    "due_date": due_date.isoformat() if due_date else None,
                },
                # Get first organization for backward compatibility
                organization_id=(
                    db.query(ProjectOrganization.organization_id)
                    .filter(ProjectOrganization.project_id == project_id)
                    .first()[0]
                    if db.query(ProjectOrganization)
                    .filter(ProjectOrganization.project_id == project_id)
                    .first()
                    else None
                ),
            )

    return {
        "assignments_created": len(assignments_created),
        "assignments_updated": len(assignments_updated) if 'assignments_updated' in locals() else 0,
        "assignments_skipped": len(assignments_skipped) if 'assignments_skipped' in locals() else 0,
        "distribution": distribution,
        "task_ids": task_ids,
        "user_ids": user_ids,
        "message": f"Created {len(assignments_created)} new assignments"
        + (
            f", updated {len(assignments_updated)} existing"
            if 'assignments_updated' in locals() and assignments_updated
            else ""
        )
        + (
            f", skipped {len(assignments_skipped)} duplicates"
            if 'assignments_skipped' in locals() and assignments_skipped
            else ""
        ),
    }


@router.get("/{project_id}/tasks/{task_id}/assignments")
async def list_task_assignments(
    project_id: str,
    task_id: str,
    request: Request,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List all assignments for a specific task"""

    # Verify task exists in project
    task = db.query(Task).filter(Task.id == task_id, Task.project_id == project_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found in project")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    assignments = db.query(TaskAssignment).filter(TaskAssignment.task_id == task_id).all()

    # Enrich with user info
    result = []
    for assignment in assignments:
        user = db.query(User).filter(User.id == assignment.user_id).first()
        result.append(
            {
                "id": assignment.id,
                "user_id": assignment.user_id,
                "user_name": user.name if user else None,
                "user_email": user.email if user else None,
                "status": assignment.status,
                "priority": assignment.priority,
                "due_date": assignment.due_date,
                "assigned_at": assignment.assigned_at,
                "started_at": assignment.started_at,
                "completed_at": assignment.completed_at,
                "notes": assignment.notes,
            }
        )

    return result


@router.delete("/{project_id}/tasks/{task_id}/assignments/{assignment_id}")
async def remove_task_assignment(
    project_id: str,
    task_id: str,  # Changed from int to str to match UUID task IDs
    assignment_id: str,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Remove a task assignment"""

    # Verify assignment exists
    assignment = (
        db.query(TaskAssignment)
        .filter(TaskAssignment.id == assignment_id, TaskAssignment.task_id == task_id)
        .first()
    )

    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Check permission
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user_with_memberships = get_user_with_memberships(db, current_user.id)
    user_role = None

    if current_user.is_superadmin:
        user_role = "superadmin"
    elif user_with_memberships and user_with_memberships.organization_memberships:
        # Get project organizations
        project_orgs = (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        )
        project_org_ids = [org[0] for org in project_orgs]

        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    if user_role not in ["superadmin", "ORG_ADMIN", "CONTRIBUTOR"]:
        raise HTTPException(
            status_code=403,
            detail="Only admins and contributors can remove assignments",
        )

    # Store info for notification before deletion
    assigned_user_id = assignment.user_id
    task = db.query(Task).filter(Task.id == task_id).first()

    db.delete(assignment)
    db.commit()

    # Send notification to the user whose assignment was removed
    NotificationService.create_notification(
        db=db,
        user_ids=[assigned_user_id],
        notification_type=NotificationType.TASK_ASSIGNMENT_REMOVED,
        title="Task Assignment Removed",
        message=f"Your assignment to a task in {project.title} has been removed",
        data={
            "project_id": project_id,
            "project_title": project.title,
            "task_id": task_id,
            "removed_by": current_user.name or current_user.email,
        },
        organization_id=(
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project.id)
            .first()[0]
            if db.query(ProjectOrganization)
            .filter(ProjectOrganization.project_id == project.id)
            .first()
            else None
        ),
    )

    return {"status": "success", "message": "Assignment removed"}


@router.get("/{project_id}/workload")
async def get_project_workload(
    project_id: str,
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get workload statistics for all annotators in a project
    Only accessible by managers and admins
    """

    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permission - only superadmin, org admin, or contributor can view workload
    user_with_memberships = get_user_with_memberships(db, current_user.id)
    user_role = None

    if current_user.is_superadmin:
        user_role = "superadmin"
    elif user_with_memberships and user_with_memberships.organization_memberships:
        # Get project organizations
        project_orgs = (
            db.query(ProjectOrganization.organization_id)
            .filter(ProjectOrganization.project_id == project_id)
            .all()
        )
        project_org_ids = [org[0] for org in project_orgs]

        for membership in user_with_memberships.organization_memberships:
            if membership.organization_id in project_org_ids and membership.is_active:
                user_role = membership.role
                break

    if user_role not in ["superadmin", "ORG_ADMIN", "CONTRIBUTOR"]:
        raise HTTPException(status_code=403, detail="Only managers can view workload dashboard")

    # Get all project members
    members = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.is_active == True)
        .all()
    )

    annotators = []
    total_assigned = 0
    total_completed = 0
    total_in_progress = 0

    for member in members:
        # Get user details
        user = db.query(User).filter(User.id == member.user_id).first()
        if not user:
            continue

        # Get assignment statistics for this user
        assignments = (
            db.query(TaskAssignment)
            .filter(TaskAssignment.user_id == member.user_id)
            .join(Task)
            .filter(Task.project_id == project_id)
            .all()
        )

        assigned_count = len(assignments)
        completed_count = sum(1 for a in assignments if a.status == "completed")
        in_progress_count = sum(1 for a in assignments if a.status == "in_progress")
        skipped_count = sum(1 for a in assignments if a.status == "skipped")

        # Check for overdue tasks
        overdue_count = sum(
            1
            for a in assignments
            if a.due_date and a.due_date < datetime.now() and a.status != "completed"
        )

        annotators.append(
            {
                "user_id": user.id,
                "user_name": user.name or user.email,
                "user_email": user.email,
                "assigned_tasks": assigned_count,
                "completed_tasks": completed_count,
                "in_progress_tasks": in_progress_count,
                "skipped_tasks": skipped_count,
                "overdue_tasks": overdue_count,
            }
        )

        total_assigned += assigned_count
        total_completed += completed_count
        total_in_progress += in_progress_count

    # Get total task count
    total_tasks = db.query(Task).filter(Task.project_id == project_id).count()

    # Calculate unassigned tasks (tasks without any assignments)
    assigned_task_ids = (
        db.query(TaskAssignment.task_id)
        .join(Task)
        .filter(Task.project_id == project_id)
        .distinct()
        .count()
    )

    total_unassigned = total_tasks - assigned_task_ids

    return {
        "annotators": annotators,
        "stats": {
            "total_tasks": total_tasks,
            "total_assigned": total_assigned,
            "total_completed": total_completed,
            "total_in_progress": total_in_progress,
            "total_unassigned": total_unassigned,
        },
    }


@router.get("/{project_id}/my-tasks")
async def get_my_tasks(
    project_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(assigned|in_progress|completed|skipped)$"),
    current_user: AuthUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get tasks assigned to current user"""

    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    org_context = get_org_context_from_request(request)
    if not check_project_accessible(db, current_user, project_id, org_context):
        raise HTTPException(status_code=403, detail="Access denied")

    query = (
        db.query(Task)
        .join(TaskAssignment)
        .filter(Task.project_id == project_id, TaskAssignment.user_id == current_user.id)
    )

    if status:
        query = query.filter(TaskAssignment.status == status)

    # Order by priority and due date
    query = query.order_by(
        TaskAssignment.priority.desc(), TaskAssignment.due_date.asc().nullsfirst()
    )

    # Pagination
    total = query.count()
    tasks = query.offset((page - 1) * page_size).limit(page_size).all()

    # Batch compute which tasks have feedback on the current user's annotations
    task_ids = [t.id for t in tasks]
    tasks_with_feedback = set()
    if task_ids and project.feedback_enabled:
        feedback_task_ids = (
            db.query(FeedbackComment.task_id)
            .join(
                Annotation,
                (FeedbackComment.target_type == "annotation")
                & (FeedbackComment.target_id == Annotation.id),
            )
            .filter(
                FeedbackComment.task_id.in_(task_ids),
                Annotation.completed_by == current_user.id,
            )
            .distinct()
            .all()
        )
        tasks_with_feedback = {tid for (tid,) in feedback_task_ids}

    # Enrich with assignment info
    result = []
    for task in tasks:
        assignment = (
            db.query(TaskAssignment)
            .filter(
                TaskAssignment.task_id == task.id,
                TaskAssignment.user_id == current_user.id,
            )
            .first()
        )

        task_data = {
            "id": task.id,
            "inner_id": task.inner_id,
            "is_labeled": task.is_labeled,
            "has_feedback": task.id in tasks_with_feedback,
            "assignment": (
                {
                    "id": assignment.id,
                    "status": assignment.status,
                    "priority": assignment.priority,
                    "due_date": assignment.due_date,
                    "assigned_at": assignment.assigned_at,
                    "notes": assignment.notes,
                }
                if assignment
                else None
            ),
        }
        result.append(task_data)

    return {
        "tasks": result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }
