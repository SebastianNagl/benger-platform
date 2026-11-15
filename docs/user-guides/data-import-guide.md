# Data Import Guide

## Overview
BenGER supports importing data to create tasks in your projects. This guide explains how to use the import functionality and the supported data formats.

## Accessing the Import Modal
1. Navigate to your project page
2. Click on "Project Data" in the Quick Actions section
3. Click the **Upload** icon (↑) in the toolbar
4. The Import Data modal will open

## Supported Formats

### JSON Format
JSON is the recommended format for importing data. Your data should be an array of objects.

**Example:**
```json
[
  {
    "id": 1,
    "text": "What is the principle of Treu und Glauben?",
    "category": "civil_law",
    "difficulty": "hard"
  },
  {
    "id": 2,
    "text": "Explain the German court system",
    "category": "procedure",
    "difficulty": "medium"
  }
]
```

**Label Studio Format:**
If your data is already in Label Studio format, it will be imported as-is:
```json
[
  {
    "data": {
      "text": "Legal question text"
    },
    "id": "task_1"
  }
]
```

### CSV Format
CSV files should include headers in the first row.

**Example:**
```csv
id,text,category,difficulty
1,"What is a GmbH?",corporate,easy
2,"Explain contract law",contract,medium
```

### TSV Format
Tab-separated values work similarly to CSV but use tabs as delimiters.

**Example:**
```tsv
id	text	category	difficulty
1	What is a GmbH?	corporate	easy
2	Explain contract law	contract	medium
```

### Plain Text Format
Each line becomes a separate task with the line content as the text field.

**Example:**
```
What is the principle of good faith in German law?
Explain the requirements for a valid contract
Describe the German court system hierarchy
```

## Import Methods

### Method 1: File Upload
1. Click "Upload Files" tab in the Import Data modal
2. Either drag and drop your file or click "Choose Files"
3. Select your data file (JSON, CSV, TSV, or TXT)
4. Click "Import Data"

### Method 2: Paste Data
1. Click "Paste Data" tab in the Import Data modal
2. Paste your data directly into the text area
3. The system will auto-detect the format
4. Click "Import Data"

### Method 3: Cloud Storage
*Coming soon - Cloud storage integration is under development*

## Field Mapping
If your data fields don't match the project template:
1. After pasting/uploading data, you may see a field mapping interface
2. Map your data fields to the required template fields
3. Click "Import" to proceed with the mapped data

## Data Validation
- The system validates data against your project's label configuration
- Missing required fields will trigger a validation warning
- You can choose to import anyway or use field mapping to correct issues

## Best Practices

### Data Preparation
1. **Consistent Format**: Ensure all records have the same structure
2. **Valid JSON**: Use a JSON validator for JSON data
3. **UTF-8 Encoding**: Save files with UTF-8 encoding to preserve special characters
4. **Headers**: Include headers in CSV/TSV files
5. **Unique IDs**: Provide unique IDs for each task when possible

### Large Datasets
- The system can handle datasets with 100+ items
- For very large datasets (1000+ items), consider splitting into batches
- Use JSON format for best performance with large datasets

### Field Requirements
Check your project's label configuration to understand required fields:
- Navigate to Project Settings > Labeling
- Note the field names marked with `$` (e.g., `$text`, `$question`)
- Ensure your import data includes these fields

## Troubleshooting

### Import Button Disabled
- Ensure you have either selected a file or pasted data
- Check that the data is not empty

### Validation Errors
- Review the error message to identify missing fields
- Use field mapping to match your data to template requirements
- Or modify your data to include required fields

### No Visual Feedback
- Check the task count after import to verify success
- Toast notifications should appear but may be delayed
- Refresh the page to see updated task count

### Format Detection Issues
- Explicitly specify format by using correct file extension
- For pasted data, ensure proper formatting:
  - JSON: Start with `[` or `{`
  - CSV: Include commas and headers
  - TSV: Use tab characters between fields

## Example Workflows

### Importing Legal Questions
1. Prepare your questions in JSON format
2. Include required fields: `text` or `question`
3. Add optional metadata: `category`, `difficulty`, `source`
4. Import via paste or file upload
5. Verify task count increased

### Batch Import from Spreadsheet
1. Export your spreadsheet as CSV
2. Ensure first row contains headers
3. Upload the CSV file
4. Map fields if necessary
5. Complete import

## API Import (Advanced)
Programmatic imports run as background jobs in three steps: ask for a
presigned upload URL, upload the file straight to object storage, then create
the import job and poll it. Put the tasks into a JSON file, for example
`tasks.json`:

```json
{
  "data": [
    {"text": "Task 1"},
    {"text": "Task 2"}
  ]
}
```

`$TOKEN` is an access key (`bgr_...`) or the `access_token` from
`POST /api/auth/token` (see
[API and script authentication](../setup/authentication.md#api-and-script-authentication)).

```bash
API=https://your-instance
H="Authorization: Bearer $TOKEN"

# 1. Ask for a presigned upload URL
curl -s -X POST -H "$H" \
  "$API/api/projects/$PROJECT_ID/imports/upload-url?filename=tasks.json" > upload.json

# 2. Upload the file straight to object storage: every entry of "fields"
#    unchanged, the file last as "file", and no BenGER token
args=()
while IFS= read -r field; do args+=(--form-string "$field"); done \
  < <(jq -r '.fields | to_entries[] | "\(.key)=\(.value)"' upload.json)
curl -s "${args[@]}" -F "file=@tasks.json" "$(jq -r .upload_url upload.json)"

# 3. Create the import job and poll it until status is completed or failed
JOB=$(curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  -d "{\"object_key\": \"$(jq -r .file_key upload.json)\"}" \
  "$API/api/projects/$PROJECT_ID/imports" | jq -r .job_id)
curl -s -H "$H" "$API/api/projects/$PROJECT_ID/imports/$JOB"
```

Importing needs edit rights on the project. The upload rules, the job fields
and the other import kinds are described in
[Project migration](../project-migration.md#import-endpoints).

## Support
If you encounter issues with data import:
1. Check this guide for format requirements
2. Verify your data in a JSON/CSV validator
3. Report persistent issues on GitHub