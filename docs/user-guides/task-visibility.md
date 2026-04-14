# Task Visibility System API Documentation

The BenGER platform implements a comprehensive task visibility system to control access to tasks based on organization membership and visibility settings.

## Overview

The visibility system provides two levels of access control:
- **Public Tasks**: Accessible to all authenticated users
- **Private Tasks**: Only accessible to users who belong to organizations assigned to the task

## API Endpoints

### Task Creation

**POST** `/tasks`

Creates a new task with visibility settings and organization assignment.

```json
{
  "name": "Legal Document Classification",
  "description": "Classify legal documents by type",
  "task_type": "classification",
  "visibility": "private",  // "public" or "private" (default: "private")
  "template": "<View>...</View>"
}
```

**Default Behavior:**
- `visibility`: Defaults to `"private"`
- **Organization Assignment**: Automatically assigns creator's organizations + TUM
- **Access Control**: Private tasks are only visible to assigned organization members

### Task Listing

**GET** `/tasks`

Returns tasks filtered based on user's organization membership and visibility settings.

**Filtering Logic:**
- **Superadmin**: Can see all tasks regardless of visibility or organization
- **Regular Users**: 
  - Can see all public tasks
  - Can see private tasks only from their organizations
- **No Organization Membership**: Can only see public tasks

**Query Parameters:**
- `sort_by`: Sorting field (default: "created_at")
- `sort_order`: "asc" or "desc" (default: "desc")
- `task_type`: Filter by task type
- `created_by`: Filter by creator
- `search`: Search in name and description

### Individual Task Access

**GET** `/tasks/{task_id}`

Retrieves a specific task with visibility-based access control.

**Access Rules:**
- **Public Tasks**: Accessible to all authenticated users
- **Private Tasks**: Only accessible to users in assigned organizations
- **Superadmin**: Access to all tasks

**Response:** Returns 403 Forbidden if user doesn't have access.

### Task Updates

**PUT** `/tasks/{task_id}`

Updates task properties including visibility and organization assignment.

```json
{
  "name": "Updated Task Name",
  "description": "Updated description", 
  "visibility": "public",  // Change visibility
  "organization_ids": ["org1", "org2"]  // Update organization assignment
}
```

**Permission Requirements:**
- Task creator can update their own tasks
- Superadmins can update any task
- TUM users can update any task

## Database Schema

### Task Model

```python
class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    visibility = Column(Enum(TaskVisibility), default=TaskVisibility.PRIVATE)
    created_by = Column(String, ForeignKey("users.id"))
    
    # Many-to-many relationship with organizations
    organizations = relationship("Organization", secondary=task_organizations_table)
```

### TaskVisibility Enum

```python
class TaskVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
```

## Implementation Details

### Database Filtering

The system implements efficient database-level filtering to ensure performance:

```python
# For users with organization membership
query = query.filter(
    (Task.visibility == TaskVisibility.PUBLIC) |
    (Task.id.in_(private_tasks_in_user_orgs_subquery))
)

# For users without organization membership
query = query.filter(Task.visibility == TaskVisibility.PUBLIC)
```

### Access Control Function

```python
def _user_has_task_access(current_user: User, task, db: Session) -> bool:
    # Superadmin has access to all tasks
    if current_user.is_superadmin:
        return True
    
    # Public tasks are accessible to all users
    if task.visibility == TaskVisibility.PUBLIC:
        return True
    
    # Private tasks require organization membership
    user_org_ids = get_user_organization_ids(current_user, db)
    task_org_ids = [org.id for org in task.organizations]
    
    return bool(set(user_org_ids) & set(task_org_ids))
```

## Default Settings

### New Task Creation
- **Visibility**: `private` (recommended for data privacy)
- **Organization Assignment**: Creator's organizations + TUM (for oversight)
- **Access**: Limited to assigned organization members

### Enterprise Sync
- **Visibility**: `private` (secure by default)
- **Organization Assignment**: TUM organization (for institutional oversight)
- **Access**: Limited to TUM organization members initially

## Best Practices

### For Developers

1. **Always check access**: Use `_user_has_task_access()` before returning task data
2. **Database filtering**: Use optimized queries that filter at database level
3. **Default private**: New tasks should default to private for security
4. **Organization assignment**: Ensure TUM is always assigned for oversight

### For API Consumers

1. **Handle 403 errors**: Gracefully handle access denied responses
2. **Check visibility**: Be aware that task lists may be filtered based on user permissions
3. **Public vs Private**: Use public tasks for open collaboration, private for sensitive data
4. **Organization membership**: Ensure users are in appropriate organizations for task access

## Security Considerations

1. **Data Isolation**: Private tasks are completely hidden from unauthorized users
2. **Database Security**: Filtering happens at the database level, not application level
3. **Access Logging**: All task access attempts should be logged for security auditing
4. **Organization Validation**: Always validate organization membership before granting access

## Performance Optimizations

1. **Database Indexes**: Visibility and organization columns are indexed for fast filtering
2. **Efficient Queries**: Subqueries used to minimize data transfer
3. **Eager Loading**: Organization relationships are loaded efficiently
4. **Caching**: Consider caching organization memberships for frequent access checks