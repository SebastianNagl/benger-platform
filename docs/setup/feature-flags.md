# Feature Flags Documentation

BenGER includes a comprehensive feature flag system that allows you to safely test new features in production with select users, perform gradual rollouts, and quickly disable features if needed.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Usage Examples](#usage-examples)
- [Admin Interface](#admin-interface)
- [API Reference](#api-reference)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

The feature flag system provides:

- **Selective User Testing**: Enable features for specific users or organizations
- **Gradual Rollout**: Control feature rollout with percentage-based targeting
- **Environment Targeting**: Different behavior per environment (dev, staging, production)
- **Role-Based Access**: Target features to specific user roles
- **Real-time Control**: Enable/disable features instantly without deployments
- **Performance Optimized**: Redis caching for fast lookups
- **Audit Trail**: Track who created and modified flags

## Architecture

### Database Schema

```sql
-- Feature flag configuration
CREATE TABLE feature_flags (
    id VARCHAR PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL,
    description TEXT,
    is_enabled BOOLEAN DEFAULT FALSE,
    target_criteria JSON,
    rollout_percentage INTEGER DEFAULT 0,
    created_by VARCHAR REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- User-specific overrides
CREATE TABLE user_feature_flags (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR REFERENCES users(id),
    feature_flag_id VARCHAR REFERENCES feature_flags(id),
    is_enabled BOOLEAN,
    created_by VARCHAR REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, feature_flag_id)
);

-- Organization-specific overrides
CREATE TABLE organization_feature_flags (
    id VARCHAR PRIMARY KEY,
    organization_id VARCHAR REFERENCES organizations(id),
    feature_flag_id VARCHAR REFERENCES feature_flags(id),
    is_enabled BOOLEAN,
    created_by VARCHAR REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(organization_id, feature_flag_id)
);
```

### Evaluation Priority

Feature flags are evaluated in the following priority order:

1. **User Override** - Specific setting for a user
2. **Organization Override** - Setting for user's organization
3. **Global Settings** - Base flag configuration with targeting and rollout
4. **Default** - Returns `false` if flag doesn't exist

## Getting Started

### 1. Create Your First Feature Flag

As a superadmin, go to `/admin/feature-flags` and create a new flag:

```json
{
  "name": "new_annotation_ui",
  "description": "New annotation interface with improved UX",
  "is_enabled": false,
  "rollout_percentage": 0,
  "target_criteria": {
    "environments": ["production"],
    "user_roles": ["superadmin", "ORG_ADMIN"]
  }
}
```

### 2. Use in React Components

```tsx
import { FeatureFlag } from '@/components/FeatureFlag'

function MyComponent() {
  return (
    <div>
      <h1>Main Interface</h1>
      
      <FeatureFlag flag="new_annotation_ui">
        <NewAnnotationInterface />
      </FeatureFlag>
      
      <FeatureFlag 
        flag="experimental_export" 
        fallback={<StandardExport />}
      >
        <ExperimentalExport />
      </FeatureFlag>
    </div>
  )
}
```

### 3. Use with Hooks

```tsx
import { useFeatureFlag } from '@/contexts/FeatureFlagContext'

function MyComponent() {
  const isNewUIEnabled = useFeatureFlag('new_annotation_ui')
  
  return (
    <div>
      {isNewUIEnabled ? (
        <NewInterface />
      ) : (
        <LegacyInterface />
      )}
    </div>
  )
}
```

### 4. Enable for Select Users

```bash
# Via API
curl -X POST http://localhost:8000/api/feature-flags/{flag_id}/user-override \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "is_enabled": true
  }'
```

## Usage Examples

### Basic Component Wrapping

```tsx
import { FeatureFlag } from '@/components/FeatureFlag'

// Simple feature gating
<FeatureFlag flag="beta_dashboard">
  <BetaDashboard />
</FeatureFlag>

// With fallback content
<FeatureFlag flag="advanced_analytics" fallback={<BasicAnalytics />}>
  <AdvancedAnalytics />
</FeatureFlag>

// With loading state
<FeatureFlag 
  flag="async_feature" 
  loading={<Spinner />}
  fallback={<DefaultComponent />}
>
  <NewFeature />
</FeatureFlag>
```

### Async Feature Checking

```tsx
import { AsyncFeatureFlag } from '@/components/FeatureFlag'

// For features that need real-time checking
<AsyncFeatureFlag flag="dynamic_feature">
  <DynamicComponent />
</AsyncFeatureFlag>
```

### Imperative Usage

```tsx
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'

function MyComponent() {
  const { checkFlag, isEnabled } = useFeatureFlags()
  
  const handleClick = async () => {
    const canUseFeature = await checkFlag('advanced_export')
    if (canUseFeature) {
      // Use new feature
    } else {
      // Fallback behavior
    }
  }
  
  // Or use synchronous check
  const showButton = isEnabled('show_advanced_button')
  
  return (
    <div>
      {showButton && <AdvancedButton onClick={handleClick} />}
    </div>
  )
}
```

### Higher-Order Component

```tsx
import { withFeatureFlag } from '@/components/FeatureFlag'

const ProtectedComponent = withFeatureFlag(
  MyComponent,
  'protected_feature',
  <div>Feature not available</div>
)
```

### Debug Mode

```tsx
import { FeatureFlagDebug } from '@/components/FeatureFlag'

// Only shows in development
<FeatureFlagDebug flag="my_feature" showDetails={true} />
```

## Admin Interface

### Accessing the Admin Interface

1. **Login** as a superadmin user
2. **Navigate** to `/admin/feature-flags`
3. **Create, edit, or delete** feature flags

### Creating a Feature Flag

- **Name**: Unique identifier (e.g., `new_dashboard_ui`)
- **Description**: Human-readable description
- **Enabled**: Global on/off switch
- **Rollout Percentage**: 0-100% of users (based on stable hashing)
- **Target Criteria**: JSON object for advanced targeting

### Target Criteria Examples

```json
{
  "environments": ["production"],
  "user_roles": ["superadmin", "ORG_ADMIN"]
}
```

```json
{
  "environments": ["production", "staging"],
  "user_roles": ["CONTRIBUTOR", "ORG_ADMIN"]
}
```

### Setting User Overrides

```bash
# Enable for specific user
curl -X POST /api/feature-flags/{flag_id}/user-override \
  -d '{"user_id": "user-123", "is_enabled": true}'

# Enable for organization
curl -X POST /api/feature-flags/{flag_id}/org-override \
  -d '{"organization_id": "org-456", "is_enabled": true}'
```

## API Reference

### Endpoints

#### List Feature Flags
```http
GET /api/feature-flags
Authorization: Bearer {token}
```

#### Create Feature Flag
```http
POST /api/feature-flags
Content-Type: application/json

{
  "name": "string",
  "description": "string",
  "is_enabled": boolean,
  "rollout_percentage": integer,
  "target_criteria": object
}
```

#### Update Feature Flag
```http
PUT /api/feature-flags/{flag_id}
Content-Type: application/json

{
  "description": "string",
  "is_enabled": boolean,
  "rollout_percentage": integer,
  "target_criteria": object
}
```

#### Check Feature Flag
```http
GET /api/feature-flags/check/{flag_name}?organization_id={org_id}
```

#### Get User's Feature Flags
```http
GET /api/feature-flags/user/all?organization_id={org_id}
```

#### Set User Override
```http
POST /api/feature-flags/{flag_id}/user-override
Content-Type: application/json

{
  "user_id": "string",
  "is_enabled": boolean
}
```

#### Set Organization Override
```http
POST /api/feature-flags/{flag_id}/org-override
Content-Type: application/json

{
  "organization_id": "string",
  "is_enabled": boolean
}
```

### Response Types

```typescript
interface FeatureFlag {
  id: string
  name: string
  description?: string
  is_enabled: boolean
  target_criteria?: Record<string, any>
  rollout_percentage: number
  created_by: string
  created_at: string
  updated_at?: string
}

interface FeatureFlagStatus {
  flag_name: string
  is_enabled: boolean
  source: 'user_override' | 'org_override' | 'global' | 'default'
}
```

## Best Practices

### Naming Conventions

- Use descriptive names: `new_annotation_ui` instead of `feature_1`
- Use consistent prefixes: `experimental_`, `beta_`, `v2_`
- Use lowercase with underscores: `advanced_export_feature`

### Development Workflow

1. **Create flag disabled** in production
2. **Develop feature** behind the flag
3. **Test with specific users** using overrides
4. **Gradually roll out** using percentage
5. **Monitor and adjust** based on feedback
6. **Remove flag** once feature is stable

### Performance Considerations

- **Cache TTL**: User flags cached for 1 minute, global flags for 5 minutes
- **Batch requests**: Use `getUserFeatureFlags()` for multiple flags
- **Minimize checks**: Don't check flags in tight loops
- **Use sync checks**: Prefer `useFeatureFlag()` over `checkFlag()`

### Security

- Only **superadmins** can create/modify flags
- **Audit trail** tracks all changes
- **Environment isolation** prevents accidental production changes
- **Graceful degradation** on service failures

## Troubleshooting

### Common Issues

#### Flag Not Working
1. **Check flag exists**: Verify in admin interface
2. **Check user permissions**: Ensure user has access
3. **Check cache**: Flags are cached, may take 1-5 minutes to update
4. **Check targeting**: Verify target criteria match user/environment

#### Performance Issues
1. **Check Redis**: Ensure Redis is running and accessible
2. **Monitor cache hit rate**: Check cache performance stats
3. **Reduce flag checks**: Minimize unnecessary evaluations
4. **Use batch loading**: Load multiple flags at once

#### API Errors
1. **Check authentication**: Ensure user is logged in
2. **Check permissions**: Only superadmins can manage flags
3. **Check request format**: Verify JSON payload structure
4. **Check network**: Ensure API is accessible

### Debug Mode

Enable debug mode in development:

```tsx
import { FeatureFlagDebug } from '@/components/FeatureFlag'

<FeatureFlagDebug flag="my_feature" showDetails={true} />
```

### Logging

Check application logs for feature flag activities:

```bash
# API logs
docker-compose logs api | grep "feature_flag"

# Frontend logs
console.log('Feature flags:', useFeatureFlags().flags)
```

### Cache Management

Clear feature flag cache:

```bash
# Via Redis CLI
redis-cli FLUSHDB

# Or restart Redis
docker-compose restart redis
```

## Integration Examples

### Task Creation Flow

```tsx
// In task creation page
<FeatureFlag flag="enhanced_task_creation">
  <EnhancedTaskCreationForm />
</FeatureFlag>

// In task list
<FeatureFlag flag="bulk_task_operations">
  <BulkActionButtons />
</FeatureFlag>
```

### Navigation Features

```tsx
// In navigation menu
<FeatureFlag flag="beta_features_menu">
  <NavItem href="/beta">Beta Features</NavItem>
</FeatureFlag>
```

### API Features

```python
# In FastAPI endpoints
from feature_flag_service import is_feature_enabled

@app.get("/api/tasks/advanced")
async def get_advanced_tasks(current_user: User = Depends(require_user)):
    if not is_feature_enabled("advanced_task_api", current_user):
        raise HTTPException(status_code=404, detail="Feature not available")
    
    # Advanced implementation
    return advanced_tasks
```

## Migration Guide

### Removing Feature Flags

When a feature becomes stable:

1. **Set flag to 100%** rollout for all users
2. **Monitor** for any issues
3. **Remove flag checks** from code
4. **Delete flag** from admin interface
5. **Clean up** unused components

### Legacy Feature Migration

Moving from environment variables to feature flags:

```tsx
// Before
const showFeature = process.env.NEXT_PUBLIC_ENABLE_FEATURE === 'true'

// After
const showFeature = useFeatureFlag('new_feature')
```

This documentation should help your team effectively use the feature flag system for safe production testing and gradual feature rollouts.