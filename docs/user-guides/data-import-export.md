# Data Import and Export Guide

This guide covers the data import and export functionality in BenGER, including the new standardized BenGER JSON format with full round-trip compatibility.

## Round-Trip Compatibility

BenGER now provides **full round-trip compatibility** between export and import operations:

✅ **Export** → **Import** → **Export** produces identical data  
✅ All task metadata, annotations, predictions, and prompts are preserved  
✅ Same BenGER format used for both export and import  
✅ Enables seamless data migration between instances  

This means you can:
- Export a task from one BenGER instance
- Import it into another instance  
- Re-export it and get the same data structure
- Trust that no data is lost in the process

## Data Export

### Downloading Task Data

You can export complete task data including annotations, predictions, and metadata from any task:

1. Navigate to a task detail page
2. In the "Quick Actions" sidebar, click the **Download** button (located above the delete button)
3. The system will download a JSON file with the naming pattern: `yyyymmdd_benger_taskname.json`

#### Export Format

The exported JSON file contains:
- **task_info**: Complete task metadata from BenGER database
- **annotation_project**: Full annotation project configuration
- **tasks_data**: All task data including annotations and predictions
- **evaluation_prompts**: All evaluation prompts associated with the task
- **export_timestamp**: When the export was created
- **exported_by**: User ID who created the export

#### Filename Convention

Downloads follow the pattern: `yyyymmdd_benger_taskname.json`

Examples:
- `20241210_benger_sentiment_analysis.json`
- `20241210_benger_qa_evaluation_task.json`

Special characters in task names are automatically replaced with underscores for filesystem compatibility.

#### Example Export Structure

```json
{
  "task_info": {
    "id": "task123",
    "name": "Legal Document Classification",
    "description": "Classify legal documents by type",
    "task_type_id": "classification",
    "template": "<View>...</View>",
    "visibility": "private",
    "created_by": "user456",
    "created_at": "2024-12-10T10:00:00Z",
    "updated_at": null
  },
  "annotation_project": {
    "id": 123,
    "title": "Legal Document Classification",
    "annotation_config": "<View>...</View>",
    // ... other annotation configuration
  },
  "tasks_data": [
    {
      "id": 1,
      "data": {"text": "Sample legal document..."},
      "annotations": [...],
      "predictions": [...]
    }
    // ... more tasks
  ],
  "evaluation_prompts": [
    {
      "id": "prompt789",
      "task_id": "task123",
      "prompt_name": "Classification Evaluation",
      "prompt_text": "Evaluate the classification accuracy...",
      "prompt_type": "evaluation",
      "evaluation_type_ids": ["accuracy", "f1"],
      "language": "de",
      "is_default": true,
      "is_active": true,
      "created_by": "user456",
      "created_at": "2024-12-10T10:00:00Z",
      "updated_at": null
    }
    // ... more prompts
  ],
  "export_timestamp": "2024-12-10T10:30:00Z",
  "exported_by": "user456"
}
```

## Data Import

### Supported Formats

BenGER supports importing data in multiple formats:

1. **Standard formats**: CSV, JSON, TSV, TXT files (processed by native annotation system)
2. **BenGER JSON exports**: Previously exported BenGER data

### Importing BenGER JSON Exports

When you upload a BenGER JSON export file, the system automatically:

1. **Detects** the file as a BenGER export (by filename pattern or content structure)
2. **Extracts** task data in the correct format for the annotation system
3. **Imports** all annotations and predictions to preserve work progress
4. **Imports** evaluation prompts and associates them with the target task
5. **Provides** detailed feedback about what was imported

#### Import Process

- **Task Data**: All task entries with their annotations and predictions are imported
- **Evaluation Prompts**: All evaluation prompts are recreated for the target task
  - Prompt IDs are regenerated to avoid conflicts
  - Default prompt settings are preserved
  - Current user becomes the creator of imported prompts
- **Metadata**: Original export information is preserved for reference

#### Import Results

After importing a BenGER export, you'll receive a summary including:
- Number of task items imported
- Number of evaluation prompts imported
- Original export timestamp and task name
- Import type confirmation

### Regular File Import

Standard data files (CSV, JSON, TXT, etc.) are processed normally:
- Direct upload to annotation system
- Automatic format detection
- Standard import validation

## Use Cases

### Data Migration
- Export tasks from one BenGER instance
- Import into another instance
- Preserve all annotations and metadata

### Backup and Restore
- Create periodic backups of important tasks
- Restore data after system changes
- Archive completed projects

### Data Sharing
- Share annotated datasets between teams
- Maintain annotation provenance
- Collaborative annotation workflows

### Cross-Project Analysis
- Export multiple tasks for analysis
- Combine datasets from different projects
- Research and evaluation workflows

## Best Practices

1. **Regular Exports**: Create periodic backups of important tasks
2. **Descriptive Names**: Use clear task names for better organization
3. **Version Control**: Track exports with timestamps for data lineage
4. **Access Control**: Only authorized users can export sensitive data
5. **Storage**: Store exports securely with appropriate access controls

## Troubleshooting

### Import Issues

**Problem**: BenGER export not detected
- **Solution**: Verify filename follows `yyyymmdd_benger_*.json` pattern or contains required structure

**Problem**: Import fails with format error
- **Solution**: Check that the JSON file is valid and contains complete BenGER export structure

**Problem**: Missing annotations after import
- **Solution**: Verify that the export contains the `tasks_data` section with annotations

### Export Issues

**Problem**: Download fails
- **Solution**: Check user permissions and task access rights

**Problem**: Large exports timeout
- **Solution**: Contact administrator for tasks with extensive data

## API Integration

### Programmatic Export
```bash
curl -X GET "https://your-instance/api/tasks/{task_id}/download" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o export.json
```

### Programmatic Import
```bash
curl -X POST "https://your-instance/api/data/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@your_export.json" \
  -F "task_id=target_task_id"
```

## Security Considerations

- Exports contain complete task data including sensitive annotations
- Access is controlled by user permissions (require_annotator level for exports)
- Exports include audit trail with user ID and timestamp
- Store exported files securely according to your data governance policies 