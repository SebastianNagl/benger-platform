# Project Migration: Export/Import System

## Overview

BenGER provides a comprehensive round-trip project export/import system that allows you to:
- Export complete projects with all associated data
- Migrate projects between BenGER instances
- Create backups of your projects
- Share projects with collaborators
- Archive projects for long-term storage

## Features

### Comprehensive Data Export
The export system captures ALL project data including:
- ✅ Project configuration and metadata
- ✅ All tasks with their data and metadata
- ✅ All annotations from all users
- ✅ ML model predictions
- ✅ LLM generations and responses
- ✅ Evaluation results
- ✅ Project members and assignments
- ✅ User references for mapping

### Intelligent Import System
The import system provides:
- 🔄 Automatic ID regeneration to avoid conflicts
- 📝 Project renaming on title conflicts
- 👤 User mapping by email address
- 🛡️ Data validation and integrity checks
- 📊 Import statistics and reporting

## Usage Guide

### Exporting Projects

#### Single Project Export (Data Only)
For exporting just the task data in Label Studio compatible format:

1. Navigate to the Projects page
2. Select one or more projects using the checkboxes
3. Click the **Actions** dropdown button
4. Select **Export Selected (Data Only)**
5. A JSON file will be downloaded containing the task data

#### Full Project Export (Complete)
For exporting complete projects with all associated data:

1. Navigate to the Projects page
2. Select one or more projects using the checkboxes
3. Click the **Actions** dropdown button  
4. Select **Export Full Projects (Complete)**
5. A ZIP file will be downloaded containing:
   - One JSON file per project
   - Each file contains complete project data
   - Files are named: `[ProjectTitle]_[ProjectID].json`

### Importing Projects

1. Navigate to the Projects page
2. Click the **Import Project** button (cloud upload icon)
3. Select a JSON file exported from BenGER
4. The system will:
   - Validate the file format
   - Check for conflicts
   - Import the project with new IDs
   - Map users by email when possible
   - Show import statistics

### Progress Indicators

The system provides real-time feedback:
- 📥 **Import Progress**: Shows file name and size during import
- 📤 **Export Progress**: Shows number of projects being exported
- ⏱️ **Timing Information**: Displays operation duration
- 📊 **Statistics**: Shows number of tasks, annotations imported/exported

### Error Handling

Common errors and their solutions:

| Error | Cause | Solution |
|-------|-------|----------|
| "Invalid JSON format" | Corrupted or malformed file | Ensure file is valid JSON |
| "Unsupported format version" | Old export format | Update source system or convert manually |
| "Missing required fields" | Incomplete export | Re-export from source with all data |
| "Project title already exists" | Name conflict | System auto-renames with timestamp |

## API Reference

### Export Endpoint

```http
POST /api/projects/bulk-export-full
Content-Type: application/json
Authorization: Bearer <token>

{
  "project_ids": ["project-1", "project-2"]
}
```

**Response**: ZIP file containing project JSON files

### Import Endpoint

```http
POST /api/projects/import-project
Content-Type: multipart/form-data
Authorization: Bearer <token>

file: <project.json>
```

**Response**:
```json
{
  "message": "Project imported successfully",
  "project_id": "new-project-id",
  "project_title": "Imported Project Title",
  "project_url": "/projects/new-project-id",
  "statistics": {
    "tasks_imported": 100,
    "annotations_imported": 50,
    "predictions_imported": 25,
    "generations_imported": 10
  }
}
```

## Data Format

### Export Format Structure

```json
{
  "format_version": "1.0.0",
  "exported_at": "2025-01-01T12:00:00Z",
  "exporter_version": "1.0.0",
  "project": {
    "id": "project-id",
    "title": "Project Title",
    "description": "Project description",
    "is_public": false,
    "is_archived": false,
    "created_at": "2025-01-01T10:00:00Z",
    "updated_at": "2025-01-01T11:00:00Z"
  },
  "tasks": [
    {
      "id": "task-id",
      "project_id": "project-id",
      "data": {},
      "meta": {},
      "is_labeled": true,
      "created_at": "2025-01-01T10:30:00Z"
    }
  ],
  "annotations": [...],
  "predictions": [...],
  "generations": [...],
  "evaluations": [...],
  "users": [...],
  "metadata": {
    "export_reason": "Migration",
    "included_data": ["tasks", "annotations", "predictions"]
  },
  "statistics": {
    "total_tasks": 100,
    "total_annotations": 50
  }
}
```

## Security Considerations

### Permissions
- **Export**: Users can export projects they have access to
- **Import**: Users need project creation permissions
- **Superadmin**: Can export/import any project

### Data Privacy
- User passwords are NEVER exported
- API keys are NEVER exported
- Personal data is mapped by email only
- Sensitive metadata can be excluded

### Best Practices
1. Always verify export files before sharing
2. Use secure channels for file transfer
3. Validate imports in staging environment first
4. Keep backups of original projects
5. Document the export reason in metadata

## Troubleshooting

### Export Issues

**Problem**: Export takes too long
- **Solution**: Export smaller batches of projects
- **Solution**: Check network connectivity
- **Solution**: Verify server resources

**Problem**: Export file is corrupted
- **Solution**: Re-export the projects
- **Solution**: Check disk space
- **Solution**: Verify browser compatibility

### Import Issues

**Problem**: Import fails with "User not found"
- **Solution**: Create users with matching emails first
- **Solution**: Import will use current user as fallback

**Problem**: Import creates duplicate projects
- **Solution**: System auto-renames duplicates
- **Solution**: Check and merge if needed

**Problem**: Large file import times out
- **Solution**: Split into smaller files
- **Solution**: Increase server timeout settings
- **Solution**: Use direct API instead of UI

## Performance Guidelines

### Recommended Limits
- **Single Export**: Up to 100 projects
- **Single Import**: Files up to 100MB
- **Tasks per Project**: Up to 10,000
- **Concurrent Operations**: 1 (UI enforced)

### Optimization Tips
1. Export during off-peak hours
2. Compress large exports externally
3. Import in batches for large datasets
4. Monitor server resources during operations

## Migration Workflows

### Instance Migration
Moving projects between BenGER instances:

1. **Source Instance**:
   - Select all projects to migrate
   - Export as full projects
   - Download ZIP file

2. **Target Instance**:
   - Ensure users exist (by email)
   - Import each JSON file
   - Verify data integrity
   - Update project settings as needed

### Backup Strategy
Regular backup workflow:

1. **Weekly**: Export active projects
2. **Monthly**: Export all projects
3. **Archive**: Store exports in secure location
4. **Test**: Periodically test restore process

### Collaboration Workflow
Sharing projects with external teams:

1. Export specific projects
2. Remove sensitive data if needed
3. Share via secure file transfer
4. Recipient imports to their instance
5. Projects maintain separate IDs

## Version Compatibility

| Export Version | Compatible Import Versions | Notes |
|---------------|---------------------------|-------|
| 1.0.0 | 1.0.0+ | Current format |
| Future versions | Will maintain backward compatibility | |

## API Client Examples

### Python Example
```python
import requests
import json

# Export projects
def export_projects(project_ids, token):
    response = requests.post(
        "https://benger.example.com/api/projects/bulk-export-full",
        json={"project_ids": project_ids},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    with open("export.zip", "wb") as f:
        f.write(response.content)
    
    return "export.zip"

# Import project
def import_project(file_path, token):
    with open(file_path, "rb") as f:
        response = requests.post(
            "https://benger.example.com/api/projects/import-project",
            files={"file": f},
            headers={"Authorization": f"Bearer {token}"}
        )
    
    return response.json()
```

### JavaScript Example
```javascript
// Export projects
async function exportProjects(projectIds) {
  const response = await fetch('/api/projects/bulk-export-full', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ project_ids: projectIds })
  });
  
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'projects-export.zip';
  a.click();
}

// Import project
async function importProject(file) {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await fetch('/api/projects/import-project', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  });
  
  return await response.json();
}
```

## Support

For issues or questions about project migration:
1. Check this documentation
2. Review error messages carefully
3. Check server logs for details
4. Contact support with:
   - Export/import files (if shareable)
   - Error messages
   - Server logs
   - Steps to reproduce

## Changelog

### Version 1.0.0 (2025-01-31)
- Initial release of comprehensive export/import system
- Support for all project data types
- Automatic conflict resolution
- User mapping by email
- Progress indicators and statistics