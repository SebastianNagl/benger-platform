# Task Assignment and Role-Based Access Control

## Overview

BenGER now supports task-level assignment with role-based access control (RBAC), following Label Studio Enterprise's model. This enables fine-grained control over who can see and annotate specific tasks, improving workload distribution and data security.

## Role Hierarchy

### Organization Roles

#### 1. **Superadmin** (Organization Owner)
- Full access to everything across all organizations
- Can see all projects and tasks
- Can create/edit/delete any project
- Can manage all users and assignments
- Can access organization settings and billing

#### 2. **Org Admin** (Administrator)
- Full access to all projects in their organization
- Can see all projects and tasks in their org
- Can create/edit/delete projects
- Can manage annotators and assignments
- Cannot access billing/organization settings

#### 3. **Contributor** (Manager)
- Can see all projects in their organization
- Can create new projects
- Can manage annotators on their own projects
- Can assign tasks to annotators
- Can view all tasks in projects they manage
- Cannot delete projects they didn't create

#### 4. **Annotator**
- Can only see projects they are members of
- Can only see tasks assigned to them (when assignment_mode is 'manual' or 'auto')
- Cannot create or manage projects
- Cannot assign tasks to others
- Read-only access to project settings

## Task Assignment Features

### Assignment Modes

Projects can operate in three assignment modes:

1. **Open Mode** (`assignment_mode: 'open'`)
   - Default mode
   - All project members can see all tasks
   - No assignment required
   - Good for small teams or open collaboration

2. **Manual Mode** (`assignment_mode: 'manual'`)
   - Tasks must be explicitly assigned to users
   - Annotators only see tasks assigned to them
   - Managers control exactly who works on what
   - Best for sensitive data or controlled workflows

3. **Auto Mode** (`assignment_mode: 'auto'`)
   - Tasks are automatically distributed to annotators
   - New annotators get tasks assigned when added to project
   - Maintains even workload distribution
   - Good for large-scale annotation projects

### Assignment Distribution Methods

When assigning tasks, managers can choose from four distribution methods:

1. **Manual Assignment**
   - Assigns all selected tasks to all selected users
   - Creates overlap for consensus/quality control
   - Each user gets every selected task

2. **Round Robin**
   - Distributes tasks evenly in rotation
   - User 1 gets task 1, User 2 gets task 2, etc.
   - Ensures equal distribution

3. **Random Distribution**
   - Randomly assigns each task to one user
   - Good for avoiding bias
   - May result in uneven distribution

4. **Load Balanced**
   - Assigns based on current workload
   - Users with fewer tasks get priority
   - Maintains balanced workload across team

## Database Schema

### TaskAssignment Table
```sql
CREATE TABLE task_assignments (
    id VARCHAR PRIMARY KEY,
    task_id INTEGER REFERENCES ls_tasks(id),
    user_id VARCHAR REFERENCES users(id),
    assigned_by VARCHAR REFERENCES users(id),
    status VARCHAR DEFAULT 'assigned', -- assigned, in_progress, completed, skipped
    priority INTEGER DEFAULT 0,
    due_date TIMESTAMP,
    notes TEXT,
    assigned_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(task_id, user_id)
);
```

### Project Configuration
Projects have an `assignment_mode` field that controls task visibility:
```sql
ALTER TABLE projects ADD COLUMN assignment_mode VARCHAR(50) DEFAULT 'open';
```

## API Endpoints

### Task Assignment

#### Assign Tasks
```http
POST /api/projects/{project_id}/tasks/assign
{
  "task_ids": [1, 2, 3],
  "user_ids": ["user1", "user2"],
  "distribution": "round_robin",
  "priority": 2,
  "due_date": "2024-12-31T23:59:59Z",
  "notes": "Please complete by end of month"
}
```

#### List Task Assignments
```http
GET /api/projects/{project_id}/tasks/{task_id}/assignments
```

#### Remove Assignment
```http
DELETE /api/projects/{project_id}/tasks/{task_id}/assignments/{assignment_id}
```

#### Get My Tasks
```http
GET /api/projects/{project_id}/my-tasks?status=assigned&page=1
```

### Role-Based Task Filtering

The `/api/projects/{project_id}/tasks` endpoint now respects user roles:

- **Superadmin/Admin/Contributor**: See all tasks
- **Annotator** (in manual/auto mode): Only see assigned tasks
- **Annotator** (in open mode): See all tasks

## Frontend Features

### My Tasks View
Located at `/projects/{id}/my-tasks`, this view shows:
- Tasks assigned to the current user
- Priority indicators
- Due dates
- Assignment status (assigned, in_progress, completed)
- Quick access to start annotating

### Task Assignment Modal
Managers can assign tasks through:
- Select tasks in the task list
- Click "Assign Tasks" button
- Choose annotators and distribution method
- Set priority and due date
- Add notes for annotators

### Project Settings
In project settings, managers can:
- Set `assignment_mode` (open/manual/auto)
- Configure `min_annotations_per_task`
- View assignment statistics

## Usage Examples

### Example 1: Quality Control with Double Annotation
1. Set `assignment_mode` to `manual`
2. Set `min_annotations_per_task` to `2`
3. Select all tasks
4. Assign to 2 annotators using `manual` distribution
5. Each annotator independently labels all tasks
6. System tracks when tasks reach consensus

### Example 2: Large-Scale Annotation Project
1. Set `assignment_mode` to `auto`
2. Add 10 annotators to project
3. Import 1000 tasks
4. System automatically distributes 100 tasks per annotator
5. New tasks are auto-assigned as they're added

### Example 3: Sensitive Data with Restricted Access
1. Set `assignment_mode` to `manual`
2. Assign specific sensitive tasks to trusted annotators only
3. Other team members cannot see unassigned tasks
4. Full audit trail of who accessed what

## Benefits

1. **Better Workload Management**
   - Even distribution of tasks
   - Clear visibility of assignments
   - Priority-based workflow

2. **Enhanced Security**
   - Annotators only see their assigned tasks
   - Sensitive data stays controlled
   - Full audit trail

3. **Improved Quality Control**
   - Assign same task to multiple annotators
   - Track inter-annotator agreement
   - Identify and resolve conflicts

4. **Increased Productivity**
   - Annotators focus on their queue
   - No confusion about what to work on
   - Clear priorities and deadlines

## Migration Notes

### For Existing Projects
- All existing projects default to `assignment_mode: 'open'`
- No change in behavior unless explicitly configured
- Can gradually adopt assignment features

### Database Migration
Run the migration to add task assignment support:
```bash
alembic upgrade head
```

This creates the `task_assignments` table and adds `assignment_mode` to projects.

## Best Practices

1. **Start with Open Mode**
   - Test the waters with your team
   - Move to manual/auto as needed

2. **Use Load Balancing for Large Teams**
   - Prevents annotator burnout
   - Maintains steady progress

3. **Set Realistic Due Dates**
   - Consider task complexity
   - Account for review time

4. **Provide Clear Instructions**
   - Use the notes field for guidance
   - Link to annotation guidelines

5. **Monitor Progress**
   - Check assignment completion rates
   - Reassign if needed
   - Recognize top performers

## Troubleshooting

### Annotators Can't See Tasks
- Check project `assignment_mode`
- Verify tasks are assigned to them
- Confirm they're project members

### Tasks Not Auto-Distributing
- Ensure `assignment_mode` is set to `auto`
- Check annotators are project members
- Verify annotator role is correct

### Assignment Conflicts
- Use unique constraint to prevent duplicates
- Check task isn't already assigned
- Review distribution method settings

## Future Enhancements

Planned improvements include:
- Skill-based assignment (match tasks to annotator expertise)
- Assignment templates for recurring patterns
- Bulk reassignment tools
- Assignment analytics dashboard
- Integration with notification system