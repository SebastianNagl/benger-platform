# Organization Management Guide

This guide covers the multi-organization features in BenGER, allowing institutions and research groups to collaborate while maintaining proper access controls.

## Overview

BenGER supports **multi-organization management** to enable:
- **Collaborative research** across institutions
- **Access control** for tasks and data
- **Institutional oversight** via TUM integration
- **Flexible user permissions** based on organization membership

## User Roles and Organizations

### **Global Roles**
- **Superadmin**: Full system access, can manage all organizations
- **Org Admin**: Can manage their assigned organizations
- **Contributor**: Can create tasks and upload data for their organizations
- **Annotator**: Can annotate tasks from their organizations
- **User**: Basic read access to their organization's tasks

### **Organization Permissions**
Users can belong to multiple organizations, with different roles in each:
- **Organization Admin**: Manage users and tasks within the organization
- **Organization Contributor**: Create and manage tasks for the organization
- **Organization User**: Basic access to organization tasks

## Organization Features

### **Automatic Task Assignment**
When creating a new task:
- **Default organizations**: Creator's organization + TUM (always included)
- **Additional organizations**: Superadmins and TUM users can assign to other organizations
- **Visibility**: Only users from assigned organizations can see the task

### **Organization Display**
Tasks show their associated organizations:
- **Task lists**: Organization badges indicate task membership
- **Task details**: Full organization listing with edit capabilities
- **Visual indicators**: TUM organization specially marked for recognition

## Inviting Users to Organizations

### **Enhanced Invitation Flow** ✨

BenGER provides a streamlined invitation system that allows organization admins to invite new users who will automatically join the organization upon account creation.

#### **How It Works**

1. **Admin sends invitation** with email and role specification
2. **User receives invitation email** with registration link
3. **User creates account** using invitation token
4. **Email verification automatically grants organization access**
5. **User immediately has full organization permissions**

#### **Creating Invitations**

**For Organization Admins:**

1. Navigate to **User Management → Organization Roles**
2. Select your organization from the dropdown
3. Click **Invite** button in the Members section
4. Fill in invitation details:
   - **Email Address**: User's email (must match exactly during signup)
   - **Role**: Select appropriate role (Annotator, Contributor, Org Admin)
5. Click **Send Invitation**

**Invitation Features:**
- ✅ **Automatic email sending** with German/English localization
- ✅ **7-day expiration** for security
- ✅ **Single-use tokens** prevent abuse
- ✅ **Email verification required** before access granted

#### **User Experience for Invited Users**

**Step 1: Receive Invitation**
- Email contains invitation details and signup link
- Link includes secure token for seamless registration

**Step 2: Create Account**
- Click invitation link or enter invitation code manually
- Fill out registration form with **same email address**
- Password and username can be chosen freely

**Step 3: Verify Email**
- Check email for verification message
- Click verification link
- **Automatic organization membership granted immediately**

**Step 4: Access Organization**
- Log in with new credentials
- Full organization access with assigned role
- No additional approval needed

#### **Managing Invitations**

**Tracking Invitations:**
- View pending invitations in organization management interface
- Monitor acceptance status and expiration dates
- See which users have successfully joined

**Invitation States:**
- **Pending**: Invitation sent, awaiting user registration
- **Linked**: User registered, awaiting email verification  
- **Accepted**: User verified email and joined organization
- **Expired**: Invitation past 7-day expiration (can be resent)

#### **Multi-Language Support**

The invitation system provides full German localization:
- **German UI**: "Mit Einladung registrieren", "Einladungscode"
- **German Emails**: Verification emails in German for German users
- **Automatic Detection**: Language detected from browser settings
- **Fallback Support**: English default for unsupported languages

#### **Troubleshooting Invitations**

**Common Issues:**

| Issue | Cause | Solution |
|-------|-------|----------|
| "Invitation not found" | Invalid/expired token | Create new invitation |
| "Email must match" | Different email used | Use exact invitation email |
| "Already accepted" | Token previously used | User already has access |
| German text not showing | Browser language settings | Check Accept-Language header |

**For Admins:**
- **Resend Invitations**: Create new invitation if original expired
- **Check Email Delivery**: Verify invitation emails aren't in spam
- **Monitor Acceptance**: Track invitation success in admin interface

## Managing Organizations

### **For Superadmins**

#### Creating Organizations
1. Navigate to **Organizations** page
2. Click **Create Organization**
3. Fill in organization details:
   - Name (e.g., "Technical University of Munich")
   - Slug (e.g., "tum")
   - Description
4. Click **Create**

#### Managing Organization Members
1. Go to **Organizations** page
2. Select an organization
3. Click **Manage Users**
4. Add/remove users and assign roles:
   - Search for users by email
   - Set organization-specific roles
   - Update global user roles if needed

#### Editing Organizations
1. Navigate to **Organizations** page
2. Click on organization name
3. Modify name, description, or settings
4. Save changes

### **For TUM Users**

TUM users have special privileges for institutional oversight:
- Can assign any task to additional organizations
- Can modify organization assignments on existing tasks
- Automatic inclusion in all new tasks for oversight

### **For Organization Admins**

Organization admins can:
- Manage users within their organization
- Assign organization-specific roles
- View all tasks associated with their organization
- Invite new users to their organization

## Task Organization Management

### **Task Visibility System**

BenGER implements a comprehensive visibility system to control task access:

#### **Visibility Levels**
- **Public Tasks**: Accessible to all authenticated users, regardless of organization membership
- **Private Tasks**: Only accessible to users who belong to organizations assigned to the task

#### **Access Rules**
1. **Public Tasks**: 
   - Visible in task listings for all users
   - Accessible for viewing, annotation, and evaluation by all users
   - Useful for open research collaborations and public datasets

2. **Private Tasks**:
   - Only visible to users in assigned organizations
   - Default setting for new tasks to ensure data privacy
   - Recommended for sensitive or proprietary research data

3. **Superadmin Override**:
   - Superadmins can access all tasks regardless of visibility or organization
   - Ensures platform administration and oversight capabilities

#### **Default Settings**
- **New Tasks**: Created as private with TUM organization automatically assigned
- **Synced Tasks**: Tasks synced from enterprise systems are private and assigned to TUM
- **Organization Assignment**: Creator's organizations + TUM (for oversight)

### **Creating Tasks with Organizations**
1. Navigate to **Tasks → Create**
2. Fill in task details
3. **Visibility Setting**:
   - Choose "Private" (default, recommended) or "Public"
   - Private tasks are only visible to organization members
   - Public tasks are visible to all platform users
4. **Organization Selection** (for superadmins/TUM users):
   - Default organizations are pre-selected (creator's orgs + TUM)
   - Check additional organizations as needed
   - TUM is always included for institutional oversight
5. Create the task

### **Modifying Task Organizations**
1. Open a task details page
2. In the **Organizations** section, click **Edit** (if permitted)
3. Select/deselect organizations
4. **Visibility**: Change between public/private as needed
5. Click **Save**

**Permission Requirements:**
- Superadmins: Can modify any task's organizations and visibility
- TUM users: Can modify any task's organizations and visibility
- Task creators: Can modify organizations and visibility if they're superadmin or TUM user

## Access Control and Visibility

### **Task Visibility Rules**
Users can see tasks based on the following rules:

**Public Tasks:**
- Visible to all authenticated users
- No organization membership required
- Accessible for viewing, annotation, and evaluation

**Private Tasks:**
- Only visible to users who belong to at least one organization assigned to the task
- Require appropriate role permissions (contributor+ for task management)
- Hidden from users not in assigned organizations

**Superadmin Access:**
- Can see and manage all tasks regardless of visibility or organization
- Full administrative access for platform oversight

### **Navigation Filtering**
The navigation menu adapts based on user permissions:
- **Data management**: Available to superadmin, org_admin, contributor
- **Tasks**: Available to superadmin, contributor
- **Organizations**: Available to superadmin, TUM users
- **Evaluation**: Available based on task access

### **Organization Switching**
Users can work with different organizations:
1. Visit **Organizations** page
2. Use organization switcher to change context
3. See tasks and data relevant to selected organization

## Best Practices

### **For Administrators**
1. **Clear naming**: Use descriptive organization names and slugs
2. **Regular audits**: Review organization memberships periodically
3. **TUM oversight**: Ensure TUM remains involved for institutional compliance
4. **Permission hierarchy**: Use appropriate roles for access control

### **For Task Creators**
1. **Default settings**: Most tasks should use default organization assignment
2. **Collaboration**: Add partner organizations when collaboration is needed
3. **Documentation**: Document organization assignments in task descriptions

### **For Organization Managers**
1. **User management**: Regularly review and update user roles
2. **Access control**: Ensure users have appropriate permissions
3. **Communication**: Coordinate with other organizations on shared tasks

## Troubleshooting

### **Common Issues**

**"I can't see a task I should have access to"**
- Check your organization memberships
- Verify the task is assigned to your organization
- Contact organization admin to verify your roles

**"I can't edit task organizations"**
- Organization editing requires superadmin or TUM user privileges
- Contact a superadmin if organization assignment needs changes

**"Organization switcher not appearing"**
- Organization switcher appears on the Organizations page
- Not all users need organization switching (based on role)

**"Navigation menu items missing"**
- Menu items are filtered based on user permissions
- Contact organization admin to verify your role assignments

### **Getting Help**
- **Organization issues**: Contact your organization admin
- **Permission problems**: Contact a superadmin
- **Technical issues**: Report via GitHub issues
- **Access requests**: Contact system administrators

## API Integration

For developers integrating with BenGER's organization system:

### **Key Endpoints**
- `GET /api/v1/organizations/` - List organizations
- `POST /api/v1/organizations/` - Create organization
- `PUT /api/v1/organizations/{id}` - Update organization
- `GET /api/v1/organizations/{id}/members` - Get organization members
- `POST /api/v1/organizations/{id}/members` - Add organization member

### **Task Organization Fields**
- `organization_ids`: Array of organization IDs
- `organizations`: Full organization objects (in responses)

Tasks automatically include organization information in API responses for proper access control.