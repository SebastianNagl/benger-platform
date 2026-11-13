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
- ✅ Task assignments (project membership comes from organizations and is not exported)
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

### Import Endpoints

Imports run as background jobs. The client first asks for a presigned upload
URL, uploads the file straight to object storage, then creates the job and
polls it:

```http
POST /api/projects/project-imports/upload-url?filename=project.ndjson.gz
POST /api/projects/project-imports
GET  /api/projects/project-imports/{job_id}
```

The job body of `POST /api/projects/project-imports` (create a new project):

```json
{
  "object_key": "<file_key from the upload-url response>",
  "organization_id": "optional: the organization that owns the new project",
  "organization_group_id": "optional: a group of that organization",
  "model_id_map": {"custom-<id in the export>": "custom-<id on this instance>"}
}
```

`model_id_map` is optional. Custom models get a new id on every instance, so
results generated with a custom model on one instance only show up under the
same model on another when the map translates the id. It applies to the model
of every generation job, generation, evaluation run and judge run and to the
project's model selection (`llm_model_ids`, `generation_config`). The target
model must already be registered on the importing instance (and be public if it
should appear on the leaderboard); an import never creates models.

Every imported task records the id of the task it was copied from
(`source_task_id`, kept across repeated imports), which is what a merge import
matches on.

### Merge Import (results back into an existing project)

```http
POST /api/projects/{project_id}/imports/upload-url?filename=copy.ndjson.gz
POST /api/projects/{project_id}/imports
GET  /api/projects/{project_id}/imports/{job_id}
```

with the job body

```json
{
  "object_key": "<file_key from the upload-url response>",
  "mode": "merge",
  "model_id_map": {"custom-<id in the export>": "custom-<id on this instance>"}
}
```

The file is a full project export (comprehensive JSON, NDJSON, `.gz` or the
single-project `.zip`) of this project or of a copy of it. Each exported task is
matched to one of the project's tasks by its recorded origin, else by identical
task data. The merge then adds only the generation jobs, generations,
evaluation runs, metrics, judge runs and evaluated rows the project does not
hold yet, and adds newly merged models to the project's model selection so the
generation grid shows them. Results already present are skipped, so running the
same merge twice changes nothing. If any exported task matches no task of the
project (or more than one), the job fails with `merge_task_mismatch` and nothing
is imported. Annotations, rubrics, comments and human-evaluation data are not
merged. In the UI the merge is the "Merge results" button on the project's data
page.

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

### Benchmarking a Model on Another Instance

To benchmark a model on a local instance and show its results next to the
other models of a production project:

1. Production: export the project as NDJSON (gzipped) or comprehensive JSON.
2. Local: import it as a new project. Register the model, generate and
   evaluate on the copy.
3. Local: export the copy.
4. Production: register the same model (public, if it should appear on the
   leaderboard), then merge the export into the original project, mapping the
   local model id to the production one (`model_id_map`).

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
import time

import requests

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

# Import project (background job: presign, upload, enqueue, poll)
def import_project(file_path, token, model_id_map=None):
    base = "https://benger.example.com/api/projects/project-imports"
    headers = {"Authorization": f"Bearer {token}"}
    upload = requests.post(
        f"{base}/upload-url", params={"filename": file_path}, headers=headers
    ).json()
    with open(file_path, "rb") as f:
        requests.post(upload["upload_url"], data=upload["fields"], files={"file": f})
    body = {"object_key": upload["file_key"]}
    if model_id_map:
        body["model_id_map"] = model_id_map
    job = requests.post(base, json=body, headers=headers).json()
    while True:
        status = requests.get(f"{base}/{job['job_id']}", headers=headers).json()
        if status["status"] in ("completed", "failed"):
            return status
        time.sleep(2)
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

// Import project: see the Python example for the presign, upload, enqueue
// and poll steps; the web client does the same in projectsAPI.runProjectImportJob.
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