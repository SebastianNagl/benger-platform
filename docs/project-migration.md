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
- ✅ Pseudonymous user placeholders

### Intelligent Import System
The import system provides:
- 🔄 Automatic ID regeneration to avoid conflicts
- 📝 Project renaming on title conflicts
- 👤 Pseudonymous authors: an export names no email, username or name, so on another instance every author becomes a placeholder account
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
For exporting complete projects with all associated data (for large projects
and for moving a benchmark project between instances, prefer the NDJSON
export below):

1. Navigate to the Projects page
2. Select one or more projects using the checkboxes
3. Click the **Actions** dropdown button  
4. Select **Export Full Projects (Complete)**
5. A ZIP file will be downloaded containing:
   - One JSON file per project
   - Each file contains complete project data
   - Files are named: `[ProjectTitle]_[ProjectID].json`

The same **Actions** menu offers **Export as NDJSON (gzip)** and **Export as
JSON (one file per project)**. They run as background jobs (one per project):
the worker writes the export to object storage and the browser downloads it
from there, so the size of a project does not matter.

### Importing Projects

1. Navigate to the Projects page
2. Click the **Import Project** button (cloud upload icon)
3. Select a project export (`.json`, `.ndjson`, `.gz` or the `.zip` of the
   full export)
4. The system will:
   - Validate the file format
   - Check for conflicts
   - Import the project with new IDs, keeping the order of the task numbers
   - Keep the authors of an export from this same instance; on another
     instance every author becomes a placeholder account
     (`imported_<id>@imported.invalid`, no password), because exports are
     pseudonymous
   - Show import statistics (tasks, annotations, generations, evaluation
     runs and evaluated rows)

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

### Export Endpoints

The export to use for a full project is the background job, which writes the
file to object storage:

```http
POST /api/projects/{project_id}/exports?format=ndjson_gz
GET  /api/projects/{project_id}/exports/{job_id}
GET  /api/projects/{project_id}/exports/{job_id}/download
```

`format` is a query parameter: `ndjson_gz` (recommended), `ndjson` or
`comprehensive` for a full project export. The `POST` answers `202` with
`{job_id, status}`. Polling the job returns `job_id`, `project_id`, `format`,
`status` (`pending`, `running`, `completed`, `failed`), `progress`,
`byte_size`, `error_message`, `created_at`, `updated_at` and `expires_at`
(when the stored file is deleted). There is no `completed_at`: once `status`
is `completed`, `updated_at` is the time the job finished. The download route
answers with a `302` to a presigned URL; with `?json=1` it returns
`{"url": ..., "expires_in": 300}` instead, a URL valid for five minutes. It
answers `404` until the job is completed and `410` once the file has expired.

The synchronous projects-list export is still there for a few
small projects (`<token>` here and below is an access key, `bgr_...`, or the
`access_token` from `POST /api/auth/token`, see
[API and script authentication](setup/authentication.md#api-and-script-authentication)):

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

The upload-url response is
`{upload_url, method, file_key, fields, expires_at}`. `filename` is a query
parameter that sets the content type the upload policy pins, so pass the real
name (`?filename=<name>.ndjson.gz` for a gzip export). Upload with a multipart
`POST` to `upload_url`: send every entry of `fields` unchanged, then the file
last as the form field `file`. The upload goes straight to object storage, so
send no `Authorization` header there and never the BenGER key. The
`file_key` then goes into the job body as `object_key`.

The job body of `POST /api/projects/project-imports` (create a new project):

```json
{
  "object_key": "<file_key from the upload-url response>",
  "organization_id": "optional: the organization that owns the new project",
  "organization_group_id": "optional: a group of that organization",
  "model_id_map": {"custom-<id in the export>": "custom-<id on this instance>"},
  "source_manifest": {"optional": "where the file came from, see below"},
  "reimport": false
}
```

`model_id_map` is optional. Custom models get a new id on every instance, so
results generated with a custom model on one instance only show up under the
same model on another when the map translates the id. It applies to the model
of every generation job, generation, evaluation run and judge run and to the
project's model selection (`llm_model_ids`, `generation_config`). The target
model must already be registered on the importing instance (and be public if it
should appear on the leaderboard); an import never creates models. A map
whose target does not exist is refused with 400 (`unknown_model_id_map_target`,
listing the ids).

A malformed body (missing `object_key`, a map that is not an object of
strings, an unknown `mode`) is answered with 400, like every refused option;
the request and response bodies are typed in the OpenAPI schema. The job a
client polls carries `status` (`pending`, `running`, `completed`, `failed`),
the created or targeted `project_id`, the importer's `result` with its
statistics, and for a refused import `error_message` plus `error_status` (the
HTTP-style status, e.g. 409) and `error_code`, a stable token such as
`merge_task_mismatch`, `merge_unknown_models`, `task_export_not_project` or
`import_too_large`. The job also carries `format`, `progress`, `byte_size`,
`created_at`, `updated_at` and `expires_at`. There is no `completed_at`: once
`status` is `completed` or `failed`, `updated_at` is the time the job finished.

### Import provenance and re-import

Every import job records what it imported. Once the worker has downloaded
the file, the job carries `payload_sha256`, the SHA-256 of the file's bytes,
and `source_manifest`:

```json
{
  "version": 1,
  "payload": {"sha256": "<hex>", "byte_size": 1234},
  "source": {"kind": "upload", "object_key": "imports/...", "filename": "..."},
  "target": {"kind": "project", "project_id": "<id>"},
  "import": {"mode": "nested", "model_id_map": {}, "reimport": false},
  "declared": {"...": "what the caller sent as source_manifest"}
}
```

`source.kind` is `storage_connection` (with `connection_id`) for a cloud
import. `target` is `{"kind": "project", "project_id"}` for the imports into
an existing project and `{"kind": "new_project", "requested_by",
"organization_id", "organization_group_id"}` for a create-new import.
`import.mode` is `nested`, `merge`, `merge_preview`, `comprehensive` or the
tabular format (`csv`, `tsv`, `txt`). `declared` is there only when the job
request carried `source_manifest`, an optional JSON object of at most
64 KiB that describes where the file came from (for example the source
files a converter built it from, with their hashes); a larger or non-object
value is refused with 400 `invalid_source_manifest`.

Importing the same file into the same target again is a no-op. Same file
means the same bytes, whatever the file is called; same target means the
same project for the imports into an existing project, or the same
requester, organization and group for a create-new import whose project
still exists and is not deleted; the mode and, for merge and create-new
imports, `model_id_map` must match too. Such a job completes without
writing anything: `duplicate_of_job_id` names the import it repeated, and
`result` is `{"project_id", "project_title", "project_url", "no_op": true,
"duplicate_of": {"job_id", "completed_at", "payload_sha256"}}` with the
earlier import's project. A changed file has another hash and is imported
as usual. A merge preview (`dry_run`) is never a no-op and never makes a
later import one. Two identical imports started at the same time run one
after the other, so the second one becomes the no-op; when the first one
takes longer than the worker's lock timeout (30 seconds), the second fails
with 409 `import_conflict`, and starting it again after the first finished
is the no-op. A failed import records its hash and manifest too and blocks
nothing.

An import records which tasks it wrote: the tasks it created and, for a
merge, the existing tasks it added results to. A repeat is a no-op only
while every one of those tasks still exists. Once any of them was deleted,
all or only some, the same file imports again as a new import: a new job
with the same `payload_sha256`, no `duplicate_of_job_id` and the usual
result. This holds for the imports into an existing project (nested,
tabular, merge) and for create-new imports.

To import the same file again on purpose in any case, send
`"reimport": true` in the job body (on
`POST /api/projects/project-imports`, `POST /api/projects/{id}/imports` and
`POST /api/projects/{id}/cloud-imports`); the web interface does not send
it. Jobs from before this feature
carry no hash, so the first import of a file after the upgrade always runs.

`error_message` is always a short reason meant for the person who started
the job, never the exception the worker hit: a database error would carry
the whole SQL statement, storage and broker errors carry hosts and paths.
The full error stays in the server log, and a message such as "The import
failed because of an internal error. The server log has the details under
job <job_id>." names the job to look it up by. Two failures carry a code a
client can act on: 409 `import_conflict` (or `export_conflict`) when the job
collided with another one writing the same rows at the same time, and 503
`queue_unavailable` when the job could not be queued; start the job again in
both cases.

Imports may run at the same time, also when their exports share authors.
The placeholder account an import creates for an author this deployment
does not know (see above) is written and committed in a short transaction
of its own before the import goes on, so a second import of an export by the
same author finds it instead of waiting for the first import to finish. A
placeholder therefore stays when its import fails later; it cannot log in,
belongs to no organization and is reused by the next import of the same
export.

An upload may be at most 5 GiB, the largest object S3 takes in one upload;
the presigned policy refuses a larger file. The cap is
`IMPORT_UPLOAD_MAX_BYTES` (bytes, Helm value `minio.importUploadMaxBytes`),
set on the API and the workers alike, because the same number bounds a cloud
import in the worker. A value above 5 GiB is lowered to 5 GiB. Object storage needs at least that much free space, or
MinIO refuses every import upload with 507; `/health` reports
`low_free_space` below it. A file of several GB takes minutes to upload, so
the proxy in front of the storage host must allow long requests (see
`infra/k3s/traefik-config.yaml`).

A compressed upload (gzip or zip) may inflate to at most 40 GiB on the
worker's temp disk; past that the job fails with 413 `import_too_large`. The
limit is `IMPORT_MAX_DECOMPRESSED_BYTES` (bytes, Helm value
`minio.importMaxDecompressedBytes`) and does not change with the upload cap,
so raising the upload cap does not raise the temp disk an import may use.

Task assignments travel with their target: a row that assigns the whole task
and the rows Korrektur creates for single items of it (an annotation or a
generation, `target_type` and `target_id`) are all exported and imported, the
item rows pointing at the imported copy of their item. Exports written before
these fields existed carry the item rows without their target, so importing
one keeps only one assignment per task and user; export again to keep them all.

Imported generation jobs are attributed to the organization that owns the
project they land in (the organization the import names, or the merge target's
organization), and to no organization for a private project. The organization
an export names for a job is informational and never used.

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

Before merging, the same uploaded file can be checked without writing
anything: create the job with `"dry_run": true` as well. The worker runs the
merge and rolls it back, and the job completes with `format`
`merge_preview` and the preview in `result.statistics`: the matched tasks, the
rows the merge would add and skip, and every model id the file's results name
(`models`: the id in the file, the id it lands under here, whether that model
exists here, its name and its row counts), with `unknown_models` naming the ids
that still need a mapping and `available_models` the models you may map to.
Poll it like any import job. The merge dialog builds its model map from it.

The file is a full project export (comprehensive JSON, NDJSON, `.gz` or the
single-project `.zip`) of this project or of a copy of it. Each exported task is
matched to one of the project's tasks by its recorded origin, else by identical
task data. The merge then adds only the generation jobs, generations,
evaluation runs, metrics, judge runs and evaluated rows the project does not
hold yet, and adds the models of newly merged generations to the project's
model selection so the generation grid shows them (a project without a saved
selection first gets the models it already has generations for). Results
already present are skipped, so running the same merge twice changes nothing.
If any exported task matches no task of the project (or more than one), the job
fails with `merge_task_mismatch` and nothing is imported. If rows would land
under a model id that does not exist on this instance, the job fails with
`merge_unknown_models`, listing the ids, and nothing is imported: map them and
merge again. Exported Bewertungsbogen (task rubrics) are mapped onto the
matching task's identical sheet, and a sheet the task lacks is added (as a
candidate when the task already has an active one), so merged gradings stay
joinable to their sheet. Annotations, comments and human-evaluation data are
not merged. In the UI the merge is the "Merge results" button on the project's
data page: choose the file, check it, choose the model here for every id the
file names that this instance does not know, and merge. The id of a custom
model is shown, with a copy button, in its expanded row on the models page.

## Data Format

### Export Format Structure

The comprehensive JSON export (`format=comprehensive`) has these top-level
keys; the NDJSON export carries the same data as one record per line.

```json
{
  "format_version": "1.0.0",
  "exported_at": "2025-01-01T12:00:00",
  "exported_by": "user-id",
  "project": {
    "id": "project-id",
    "title": "Project Title",
    "description": "Project description",
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
  "task_rubrics": [...],
  "task_rubric_review_events": [...],
  "annotations": [...],
  "predictions": [],
  "generations": [...],
  "response_generations": [...],
  "task_assignments": [...],
  "evaluations": [...],
  "evaluation_metrics": [...],
  "evaluation_judge_runs": [...],
  "task_evaluations": [...],
  "human_evaluation_configs": [...],
  "human_evaluation_sessions": [...],
  "human_evaluation_results": [...],
  "preference_rankings": [...],
  "likert_scale_evaluations": [...],
  "korrektur_comments": [...],
  "grading_feedback": [...],
  "post_annotation_responses": [...],
  "users": [...],
  "statistics": {
    "total_tasks": 100,
    "total_annotations": 50
  }
}
```

`evaluations` holds the project's evaluation runs, `task_assignments` the task
assignments (see above), and `users` the pseudonymous user placeholders.

`task_rubrics` holds the grading sheets (Bewertungsbogen) with their check
(`review_state`, `reviewed_at`, `reviewed_by`), and `task_rubric_review_events`
their edit and check log; that key only appears when the project has a log,
and the project's `rubric_review_required` switch travels in `project`. The
import points every log entry at the imported task and sheet. The person who
checked a sheet or wrote a log entry is kept when the import resolves them
(the same account, the same person by email, or their placeholder) and left
empty otherwise; it is never replaced by the person running the import. The
per-task data export carries the same log under `rubric_review_events` next to
each task's `rubrics`. A merge import leaves the log out. An import into an
existing project that requires the check (nested or merge) brings an exported
active sheet that is not confirmed in as a candidate.

## Security Considerations

### Permissions
- **Export**: needs the effective role ORG_ADMIN or CONTRIBUTOR on the
  project, the roles that see unblinded task data (annotators cannot export).
  A project with a timed access window cannot be exported by non-editors
  before the window opens.
- **Import into an existing project** (nested or merge import): needs edit
  rights on the project: its creator, a superadmin, or a CONTRIBUTOR or
  ORG_ADMIN of an organisation it is attached to. Visitors of a public project
  with `public_role=CONTRIBUTOR` may read and export it but not import into it.
- **Import as a new project**: open to every signed-in user. Naming an
  `organization_id` additionally needs a CONTRIBUTOR or ORG_ADMIN membership
  there.
- **Superadmin**: can export and import any project.

### Data Privacy
- User passwords are NEVER exported
- API keys are NEVER exported
- Exports are pseudonymous: no email, username or name of any user is exported
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

**Problem**: Imported annotations show placeholder authors
- **Cause**: Exports are pseudonymous, so on another instance an author cannot
  be matched to an account, even one with the same email
- **Solution**: None needed for the data; on the same instance the original
  authors are kept

**Problem**: Import creates duplicate projects
- **Solution**: System auto-renames duplicates
- **Solution**: Check and merge if needed

**Problem**: Large file upload is cut off
- **Cause**: an upload that breaks off after about 60 seconds points to the
  proxy in front of object storage, not to the file size. Its timeout is set
  in `infra/k3s/traefik-config.yaml` (3600 seconds), so a file of several GB
  has time to arrive.
- **Solution**: check that proxy timeout on the deployment; splitting the
  file is not needed below the 5 GiB cap.

## Performance Guidelines

### Recommended Limits
- **Single Export**: Up to 100 projects
- **Single Import**: up to 5 GiB per file (`IMPORT_UPLOAD_MAX_BYTES`)
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
   - Import each export file (authors become placeholder accounts, see above)
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

Map every custom model back, not only the new one: a custom model of the
production project that was mapped to a local id on the way into the copy
comes back under that local id, and without its mapping the merge would add
its results a second time. The merge refuses such a file
(`merge_unknown_models`) and the preview lists every id that needs a mapping.

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

`token` is an access key (`bgr_...`) or the `access_token` from
`POST /api/auth/token`.

### Python Example
```python
import os
import time

import requests

API = "https://benger.example.com/api/projects"


# Export one project (background job: start, poll, download)
def export_project(project_id, token, path="export.ndjson.gz"):
    headers = {"Authorization": f"Bearer {token}"}
    job = requests.post(
        f"{API}/{project_id}/exports",
        params={"format": "ndjson_gz"},
        headers=headers,
    ).json()
    while True:
        status = requests.get(
            f"{API}/{project_id}/exports/{job['job_id']}", headers=headers
        ).json()
        if status["status"] == "completed":
            break
        if status["status"] == "failed":
            raise RuntimeError(status["error_message"])
        time.sleep(2)
    url = requests.get(
        f"{API}/{project_id}/exports/{job['job_id']}/download",
        params={"json": 1},
        headers=headers,
    ).json()["url"]
    # The presigned URL goes to object storage: no BenGER key there.
    with requests.get(url, stream=True) as r, open(path, "wb") as f:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    return path

# Import project (background job: presign, upload, enqueue, poll)
def import_project(file_path, token, model_id_map=None):
    base = f"{API}/project-imports"
    headers = {"Authorization": f"Bearer {token}"}
    upload = requests.post(
        f"{base}/upload-url",
        params={"filename": os.path.basename(file_path)},
        headers=headers,
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
- Pseudonymous user export (no email, username or name; authors become placeholder accounts on another instance)
- Progress indicators and statistics