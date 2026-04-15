# Managing Multiple Projects - User Guide

This guide will help you efficiently manage multiple projects at once using BenGER's bulk operations feature.

## Getting Started

### Accessing the Projects Page

1. Log in to BenGER
2. Click on **"Projects"** in the main navigation menu
3. You'll see a table listing all your accessible projects

### Understanding the Projects Table

The projects table displays:
- **Checkbox** - For selecting projects
- **Title** - Project name (clickable to view details)
- **Description** - Brief project description
- **Tasks** - Number of tasks in the project
- **Annotations** - Number of completed annotations
- **Created** - Creation date
- **Status** - Active or Archived

## Selecting Projects

### Individual Selection
- Click the checkbox next to any project to select it
- Click again to deselect

### Select All
- Click the checkbox in the table header to select all visible projects
- This only selects projects on the current page

### Selection Indicator
- When projects are selected, you'll see a count above the table (e.g., "3 selected")
- The "Bulk Actions" button becomes enabled

## Performing Bulk Operations

### Step-by-Step Guide

#### 1. Deleting Multiple Projects

**⚠️ Warning**: This action is permanent and cannot be undone.

1. Select the projects you want to delete
2. Click **"Bulk Actions"** → **"Delete"**
3. Review the confirmation dialog showing:
   - Number of projects to be deleted
   - Warning about permanent deletion
4. Click **"Delete Projects"** to confirm

**What happens**:
- Selected projects are permanently removed
- All associated tasks and annotations are also deleted
- You'll see a success message confirming the deletion

#### 2. Exporting Multiple Projects

1. Select the projects you want to export
2. Click **"Bulk Actions"** → **"Export"**
3. The export will download automatically as a JSON file

**Export includes**:
- Project metadata (title, description, settings)
- Task data
- Configuration details
- Creation and modification timestamps

**Tips**:
- Use exports for backups before major changes
- Export data can be imported into other BenGER instances
- JSON format is human-readable and can be processed programmatically

#### 3. Archiving Projects

1. Select active projects you want to archive
2. Click **"Bulk Actions"** → **"Archive"**
3. Projects are immediately archived

**Benefits of archiving**:
- Removes clutter from your active projects list
- Preserves all project data
- Projects can be unarchived later
- Archived projects don't count against active project limits

#### 4. Unarchiving Projects

1. Use the filter to show archived projects
2. Select the archived projects to restore
3. Click **"Bulk Actions"** → **"Unarchive"**
4. Projects return to active status

## Practical Examples

### Example 1: Cleaning Up Completed Projects

**Scenario**: You've finished evaluating several LLM models and want to archive the completed projects.

1. Sort projects by completion date
2. Select all completed evaluation projects
3. Bulk archive them to keep your workspace organized

### Example 2: Creating Project Templates

**Scenario**: You want to create multiple similar projects for different legal domains.

1. Create and configure one project perfectly
2. Select it and use bulk duplicate
3. Rename the copies for different domains
4. Modify specific settings as needed

### Example 3: Monthly Backup

**Scenario**: Company policy requires monthly backups of all active projects.

1. Select all projects using the header checkbox
2. Bulk export to create a comprehensive backup
3. Store the JSON file in your backup system
4. Document the backup date and file location

## Tips and Best Practices

### Organization Tips

1. **Regular Cleanup**
   - Archive completed projects monthly
   - Delete test or duplicate projects promptly

2. **Naming Conventions**
   - Use consistent naming for easy sorting
   - Include dates or version numbers
   - Add prefixes for different project types

3. **Project Grouping**
   - Create projects for related tasks together
   - Archive or delete groups as a unit

### Performance Tips

1. **Batch Operations**
   - Select all related projects at once
   - Perform operations in batches of 10-20 for best performance

2. **Filtering First**
   - Use search and filters to find projects
   - Then use "Select All" for targeted operations

### Safety Tips

1. **Before Deleting**
   - Always export projects before deletion
   - Double-check your selection
   - Consider archiving instead of deleting

2. **Regular Exports**
   - Export important projects regularly
   - Keep exports organized by date
   - Test restore procedures periodically

## Troubleshooting

### Can't select projects?
- Ensure you're clicking the checkbox, not the project name
- Check if you have permission to manage the projects
- Refresh the page if checkboxes aren't responding

### Bulk Actions button disabled?
- Make sure at least one project is selected
- Verify you have the required permissions
- Check your organization role

### Export not downloading?
- Check browser download settings
- Disable popup blockers temporarily
- Try a different browser
- Check available disk space

### Operations failing?
- Verify your permissions for all selected projects
- Check internet connection
- Try smaller batches
- Contact support if errors persist

## Keyboard Shortcuts

- **Space** - Toggle selection of focused project
- **Ctrl/Cmd + A** - Select all visible projects
- **Escape** - Clear all selections

## FAQs

**Q: How many projects can I select at once?**
A: You can select all projects on the current page (up to 50). For larger operations, process in batches.

**Q: Can I recover deleted projects?**
A: No, deletion is permanent. Always export important projects before deleting.

**Q: Do archived projects count against my project limit?**
A: No, only active projects count against limits.

**Q: Can I bulk edit project settings?**
A: Currently, bulk operations don't include editing. Edit projects individually.

**Q: Who can perform bulk operations?**
A: Users need appropriate permissions (admin or project owner) for each selected project.

## Need Help?

If you encounter issues or have questions:

1. Check the [troubleshooting section](#troubleshooting) above
2. Review the [technical documentation](/docs/features/bulk-operations.md)
3. Contact your organization administrator
4. Submit a support ticket with:
   - Description of the issue
   - Screenshots if applicable
   - Steps to reproduce the problem