# Developer Authentication Guide

## Automatic Authentication in Development

BenGER includes an automatic authentication feature for local development environments to streamline the developer experience by eliminating repetitive login steps.

### How It Works

When developing locally, the system can automatically authenticate you as an admin user without requiring manual login. This feature:
- Only works on localhost domains (localhost, 127.0.0.1, benger.localhost)
- Requires explicit opt-in via environment variable
- Provides full superadmin access for testing all features
- Shows visual indicators when active

### Setup

#### Docker Development (Recommended)

The auto-authentication is pre-configured in our Docker setup:

```bash
# Start the development environment
cd infra
docker-compose up -d

# Access the application
open http://benger.localhost
```

You'll be automatically logged in as the admin user.

#### Local Development

For local Next.js development:

```bash
# Set the environment variable
export NEXT_PUBLIC_ENABLE_DEV_AUTH=true

# Start the development server
cd services/frontend
npm run dev

# Access at http://localhost:3000
```

### Configuration

The feature is controlled by the `NEXT_PUBLIC_ENABLE_DEV_AUTH` environment variable:

| Environment | Variable | Value | Effect |
|------------|----------|-------|--------|
| Docker Dev | `NEXT_PUBLIC_ENABLE_DEV_AUTH` | `true` | Auto-login enabled |
| Local Dev | `NEXT_PUBLIC_ENABLE_DEV_AUTH` | `true` | Auto-login enabled |
| Production | Not set or `false` | - | Auto-login disabled |

### Security

The auto-authentication feature has multiple security safeguards:

1. **Domain Restriction**: Only works on localhost domains
   - `localhost`
   - `127.0.0.1`
   - `benger.localhost`

2. **Environment Check**: Requires explicit `NEXT_PUBLIC_ENABLE_DEV_AUTH=true`

3. **Build-time Configuration**: The flag must be set during build for containerized environments

4. **No Production Risk**: Production builds never include this flag

### Visual Indicators

When auto-authentication is active, you'll see:

1. **Development Mode Indicator**: A dismissible notification in the bottom-right corner showing:
   - Current authentication status
   - Username and email
   - Environment details
   - Dismiss option (persists for session)

2. **Dev Mode Badge**: A persistent badge at the top of the screen indicating dev mode is active

### Default Credentials

When auto-authentication is enabled, the system logs in with:
- **Username**: `admin`
- **Password**: `admin`
- **Role**: Superadmin
- **Organization**: TUM (Technical University of Munich)

### Testing Different Roles

To test with different user roles, you can:

1. **Logout manually**: Click the user dropdown → "Abmelden" (Logout)
2. **Login as different user**: Use the login form with test credentials:
   - Contributor: `contributor` / `contributor`
   - Annotator: `annotator` / `annotator`
   - Regular User: `demo@test.com` / `demo`

### Troubleshooting

#### Auto-auth not working?

1. **Check environment variables**:
   ```bash
   docker exec infra-frontend-1 printenv | grep ENABLE_DEV_AUTH
   ```
   Should show: `NEXT_PUBLIC_ENABLE_DEV_AUTH=true`

2. **Verify domain**: Ensure you're accessing via `benger.localhost` (not `localhost:3000` for Docker)

3. **Clear browser data**: Sometimes cached auth state interferes:
   - Open DevTools → Application → Clear Storage

4. **Rebuild container** (if using Docker):
   ```bash
   docker-compose build --no-cache frontend
   docker-compose up -d frontend
   ```

#### Visual indicators not showing?

The indicators only appear when:
- Auto-authentication is enabled (`NEXT_PUBLIC_ENABLE_DEV_AUTH=true`)
- You're on a localhost domain
- You're successfully authenticated
- You haven't dismissed them (for the session)

### API Development

When developing API endpoints, the auto-authenticated session provides:
- Full superadmin permissions
- Access to all organizations
- Ability to create/modify all resources

Example API testing:
```javascript
// The auto-auth session includes these headers automatically
const response = await fetch('http://benger.localhost/api/v1/tasks', {
  credentials: 'include' // Uses the auto-auth session
})
```

### Disabling Auto-Authentication

To disable auto-authentication temporarily:

1. **Docker Environment**:
   ```yaml
   # infra/docker-compose.yml
   environment:
     NEXT_PUBLIC_ENABLE_DEV_AUTH: "false"  # Change to false
   ```
   Then rebuild: `docker-compose build frontend && docker-compose up -d`

2. **Local Development**:
   ```bash
   unset NEXT_PUBLIC_ENABLE_DEV_AUTH
   npm run dev
   ```

### Best Practices

1. **Use for Development Only**: Never enable in production environments
2. **Test Real Login Flow**: Periodically test the actual login flow to ensure it works
3. **Test Different Roles**: Use manual login to test role-based features
4. **Clear Sessions**: Clear browser storage when switching between auto-auth and manual auth
5. **Document Changes**: Update this guide if you modify the auto-auth behavior

### Implementation Details

The auto-authentication is implemented in:
- **AuthContext**: `/services/frontend/src/contexts/AuthContext.tsx`
- **Environment Config**: `/infra/docker-compose.yml`
- **Visual Indicators**: `/services/frontend/src/components/dev/DevModeIndicator.tsx`
- **Tests**: `/services/frontend/src/__tests__/auth/auto-auth-dev.test.tsx`

### Related Documentation

- [Local Development Setup](./LOCAL_DEVELOPMENT.md)
- [Docker Development](./DOCKER_DEVELOPMENT.md)
- [Authentication System](./AUTHENTICATION.md)
- [Environment Variables](./ENVIRONMENT_VARIABLES.md)