# Project Data Tabs Implementation

## Overview
The project data page has been reorganized with a three-tab interface to better separate different aspects of project data:
1. **Annotation Tab** - Contains the original annotation management functionality
2. **Generation Tab** - Displays LLM-generated responses and prompts
3. **Evaluation Tab** - Placeholder for future evaluation features

## Implementation Details

### File Structure
```
services/frontend/src/
├── app/projects/[id]/data/page.tsx         # Main page with tab navigation
└── components/projects/tabs/
    ├── AnnotationTab.tsx                   # Annotation data management
    ├── GenerationTab.tsx                   # LLM generations display
    └── EvaluationTab.tsx                   # Evaluation placeholder
```

### Features

#### Tab Navigation
- Three tabs are displayed: Annotation, Generation, and Evaluation
- Annotation tab is selected by default
- Tab state is synchronized with URL parameters for bookmarking
- URL format: `/projects/[id]/data?tab=annotation|generation|evaluation`

#### Annotation Tab
- Contains all original functionality from the project data page
- Table/grid view with filtering, sorting, and bulk operations
- Import/export capabilities
- Column management and customization
- Real-time task status updates

#### Generation Tab
- Displays tasks that have LLM responses
- Shows prompts sent to LLMs
- Displays responses from different models
- Expandable/collapsible task cards
- Model filtering capability
- Export functionality for prompts and responses

#### Evaluation Tab
- Currently shows a "Coming Soon" placeholder
- Will include evaluation metrics and analytics in future releases

### Technical Implementation

#### URL Synchronization
The tab state is synchronized with URL parameters to enable:
- Direct linking to specific tabs
- Browser back/forward navigation
- Bookmarking of specific views

```typescript
// Tab change handler
const handleTabChange = useCallback((tab: TabType) => {
  setActiveTab(tab)
  const newSearchParams = new URLSearchParams(searchParams.toString())
  newSearchParams.set('tab', tab)
  const newUrl = `${window.location.pathname}?${newSearchParams.toString()}`
  window.history.replaceState({}, '', newUrl)
}, [searchParams])
```

#### Component Architecture
The implementation follows a modular approach:
- Each tab is a separate component for maintainability
- Shared hooks and utilities are reused across tabs
- Project store provides centralized state management

### Usage

Navigate to any project's data page:
```
/projects/[project-id]/data
```

Switch between tabs by:
1. Clicking on the tab buttons
2. Using URL parameters: `?tab=generation`
3. Using keyboard navigation (Tab key + Enter/Space)

### Mobile Responsiveness
- Tab labels are abbreviated on mobile devices
- All functionality remains accessible on smaller screens
- Touch-friendly interaction areas

### Accessibility
- ARIA labels for screen readers
- Keyboard navigation support
- Focus indicators for interactive elements
- Proper heading hierarchy

## Testing

### Unit Tests
Located in: `/services/frontend/src/__tests__/projects/tabs/ProjectDataTabs.test.tsx`

Tests cover:
- Tab rendering and navigation
- URL synchronization
- Project loading behavior
- Component props passing

### Running Tests
```bash
cd services/frontend
npm test ProjectDataTabs.test.tsx
```

## Future Enhancements

### Evaluation Tab
The evaluation tab is currently a placeholder and will include:
- A/B testing capabilities
- Quality metrics and scoring
- Performance trend analysis
- Model comparison tools

### Additional Features
- Cross-tab data persistence
- Advanced filtering across tabs
- Real-time collaboration indicators
- WebSocket updates for live data

## Migration Notes

### For Developers
- The original project data page content has been moved to `AnnotationTab.tsx`
- No breaking changes to existing APIs
- All existing functionality is preserved

### For Users
- The default view (Annotation tab) remains unchanged
- New Generation tab provides LLM data visibility
- URL structure includes tab parameter for direct access

## Troubleshooting

### Common Issues

1. **Tab not loading**: Ensure project data is fetched before rendering tabs
2. **URL not updating**: Check that `useSearchParams` hook is properly initialized
3. **Tab content missing**: Verify component imports and project ID passing

### Debug Steps
1. Check browser console for errors
2. Verify API responses in Network tab
3. Ensure project store is properly initialized
4. Check URL parameters are correctly formatted

## Related Documentation
- [Project Management](./project-management.md)
- [LLM Integration](./llm-integration.md)
- [Native Annotation System](./native-annotation-system.md)