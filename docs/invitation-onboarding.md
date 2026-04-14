# Invitation-Based User Onboarding

This document describes the invitation-based user onboarding system implemented to solve issues with users invited to organizations who couldn't complete their account setup.

## Overview

The invitation onboarding system provides two distinct user registration paths:

1. **Self-Registered Users**: Traditional signup with immediate password creation → Email verification → Login
2. **Invited Users**: Invitation email → Email verification → Profile completion (username/password setup) → Organization access

## Feature Flags

This functionality is controlled by three feature flags that must be enabled through the admin interface (`/admin/feature-flags`):

- `AUTH_INVITATION_PROFILE_COMPLETION`: Enable profile completion flow for invited users
- `AUTH_ENHANCED_VERIFICATION_SUCCESS`: Enable enhanced email verification success pages
- `AUTH_PASSWORDLESS_INVITATION`: Allow users to be invited without initial password

## Database Schema Changes

### New User Fields

- `hashed_password`: Changed from NOT NULL to nullable to support invited users
- `invitation_token`: Stores the invitation token for tracking
- `profile_completed`: Boolean flag indicating if profile setup is complete
- `created_via_invitation`: Boolean flag to distinguish invited users

## API Endpoints

### New Endpoints

#### `POST /auth/complete-profile`
Allows invited users to set their username and password after email verification.

**Request:**
```json
{
  "username": "string",
  "password": "string", 
  "name": "string" // optional
}
```

**Response:**
```json
{
  "success": boolean,
  "message": "string",
  "user_id": "string",
  "username": "string", 
  "email": "string",
  "profile_completed": boolean,
  "redirect_url": "string"
}
```

#### `GET /auth/check-profile-status`
Checks if the current user needs to complete their profile.

**Response:**
```json
{
  "user_id": "string",
  "email": "string",
  "profile_completed": boolean,
  "created_via_invitation": boolean,
  "has_password": boolean,
  "needs_profile_completion": boolean,
  "message": "string"
}
```

#### `POST /auth/verify-email-enhanced/{token}`
Enhanced email verification that returns user type and appropriate redirect information.

**Response:**
```json
{
  "success": boolean,
  "message": "string",
  "user_type": "invited|self_registered",
  "profile_completed": boolean,
  "redirect_url": "string",
  "invitation_info": {
    "organization_id": "string",
    "role": "string"
  }
}
```

### Modified Endpoints

#### `POST /auth/signup`
Now handles invitation-based registration when `AUTH_PASSWORDLESS_INVITATION` is enabled.

#### `POST /invitations/accept/{token}`
Now checks if profile completion is required before allowing invitation acceptance.

## Frontend Pages

### `/complete-profile`
New page for invited users to set up their username and password after email verification.

**Features:**
- Username validation (uniqueness check)
- Password confirmation
- Optional display name
- Automatic redirect after completion

### Updated Pages

#### `/verify-email/[token]`
Enhanced to differentiate between user types and redirect appropriately:
- Invited users with incomplete profiles → `/complete-profile`
- Invited users with complete profiles → Organization page
- Self-registered users → Login page

#### `/register`
Updated to handle invitation tokens in URL parameters for seamless flow.

## User Flows

### Invited User Flow

1. **Organization admin sends invitation**
   - Creates invitation with token
   - Email sent to invitee

2. **User clicks invitation link**
   - Redirected to registration page with pre-filled email
   - Can create account without password (if feature enabled)

3. **Email verification**
   - User receives verification email
   - Clicks verification link
   - System detects invited user type

4. **Profile completion**
   - Redirected to `/complete-profile`
   - Sets username and password
   - Profile marked as completed

5. **Organization access**
   - Can now accept organization invitation
   - Gets full access to organization resources

### Self-Registered User Flow

1. **User registers normally**
   - Provides username, email, name, password
   - Account created with complete profile

2. **Email verification**
   - Receives verification email
   - Clicks verification link
   - Redirected to login page

3. **Login and access**
   - Can immediately log in
   - Standard user experience

## Error Handling

### Profile Completion Errors

- **Username already taken**: Returns 400 with descriptive message
- **Feature flag disabled**: Returns 403 with feature unavailable message
- **Not an invited user**: Returns 400 indicating profile completion not needed
- **Profile already complete**: Returns success with existing data

### Invitation Acceptance Errors

- **Profile incomplete**: Returns redirect to profile completion instead of error
- **Feature flags disabled**: Falls back to standard behavior

## Security Considerations

1. **Token Validation**: All invitation tokens are validated for expiry and authenticity
2. **Email Matching**: Ensures invitation email matches the user attempting to accept
3. **Feature Flag Protection**: All new functionality is behind feature flags for safe rollout
4. **Password Requirements**: Profile completion enforces same password strength as registration

## Testing

### Unit Tests
Located in `services/api/tests/test_invitation_onboarding.py`:
- Profile completion flow
- Feature flag behavior
- Username conflict handling
- Enhanced email verification
- Database schema changes

### Integration Testing
- Full invitation → verification → profile completion → organization access flow
- Fallback behavior when feature flags are disabled
- Cross-browser compatibility

### Manual Testing
1. Enable feature flags in `/admin/feature-flags`
2. Create organization and send invitation
3. Register with invitation token
4. Verify email and complete profile
5. Accept organization invitation

## Deployment

### Prerequisites
1. Run database migration: `alembic upgrade head`
2. Restart API container to load new endpoints
3. Deploy frontend with new pages

### Feature Flag Rollout
1. Deploy code with flags disabled (default)
2. Test in staging environment
3. Enable flags one by one in production
4. Monitor for issues and rollback if needed

### Rollback Plan
1. Disable feature flags immediately
2. Users fall back to standard password reset flow
3. Database changes are backward compatible

## Monitoring

Monitor the following metrics after deployment:
- Profile completion success rate
- Time between invitation and profile completion
- Feature flag usage and errors
- User feedback on new flow

Check logs for:
- Profile completion failures
- Feature flag access denials
- Email verification issues
- API endpoint errors

## Future Enhancements

1. **Magic Link Authentication**: Replace password setup with magic links
2. **Bulk Invitations**: Support for inviting multiple users at once  
3. **Custom Invitation Messages**: Allow organizations to customize invitation emails
4. **Progressive Profile Setup**: Split profile completion into multiple optional steps
5. **Social Login Integration**: Allow invited users to connect social accounts