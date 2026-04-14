# GitHub Labels Guide

This document describes the label system used in the BenGER repository for organizing issues and pull requests.

## Label Categories

### 🔴 Priority Labels
Used to indicate the urgency of issues:
- `priority: critical` - Needs immediate attention (production down, security issues)
- `priority: high` - High priority (blocking features, major bugs)
- `priority: medium` - Medium priority (important but not blocking)
- `priority: low` - Low priority (nice to have, minor improvements)

### 📊 Status Labels
Track the current state of work:
- `status: in progress` - Work is actively being done
- `status: ready for review` - Ready for code review
- `status: blocked` - Blocked by dependencies or external factors
- `status: needs investigation` - Requires research before starting

### 🌍 Environment Labels
Indicate which environment is affected:
- `env: production` - Production environment issues
- `env: staging` - Staging environment issues
- `env: development` - Development environment issues

### 🔧 Component Labels
Identify which part of the system is affected:
- `component: api` - Backend/API related
- `component: frontend` - Frontend/UI related
- `component: database` - Database related
- `component: migrations` - Database migration issues
- `component: auth` - Authentication/Authorization
- `component: notifications` - Notification system
- `component: ci/cd` - CI/CD pipeline

### 📝 Type Labels
Categorize the nature of the work:
- `bug` - Something isn't working
- `enhancement` - New feature or request
- `type: feature` - New feature implementation
- `type: refactor` - Code refactoring
- `type: security` - Security-related issue
- `type: performance` - Performance improvement
- `type: test` - Test-related work
- `documentation` - Documentation improvements

### 🏷️ Special Labels
- `good first issue` - Good for newcomers
- `help wanted` - Extra attention is needed
- `duplicate` - This issue already exists
- `wontfix` - This will not be worked on
- `invalid` - This doesn't seem right
- `question` - Further information is requested

### 🔗 Dependency Labels
- `dependencies` - Dependency updates
- `github_actions` - GitHub Actions updates
- `python` - Python code updates
- `javascript` - JavaScript code updates
- `infrastructure` - Infrastructure changes

## Usage Guidelines

### For Issues
1. **Always add a priority label** for bugs and critical features
2. **Add at least one component label** to identify the affected area
3. **Add environment label** if the issue is environment-specific
4. **Add status label** to track progress

### For Pull Requests
1. **Link to related issue** and inherit its labels
2. **Add type label** to indicate the nature of changes
3. **Add component labels** for all affected components
4. **Update status labels** as the PR progresses

### Label Combinations Examples

#### Critical Production Bug
- `bug`
- `priority: critical`
- `env: production`
- `component: api`
- `status: in progress`

#### New Feature Request
- `enhancement`
- `type: feature`
- `priority: medium`
- `component: frontend`
- `status: needs investigation`

#### Database Migration Issue
- `bug`
- `priority: high`
- `component: database`
- `component: migrations`
- `env: production`

## Automation

Consider setting up GitHub Actions to:
- Auto-label PRs based on files changed
- Add `status: in progress` when PR is opened
- Add `status: ready for review` when PR is marked ready
- Add priority labels based on keywords in issue title

## Label Colors Reference

- **Red tones** (#b60205 - #fef2c0): Priority levels
- **Blue tones** (#0052cc - #5319e7): Status indicators
- **Purple tones** (#8b1a8b - #d8b9ff): Environment tags
- **Teal/Cyan** (#006b75 - #c5def5): Components
- **Mixed colors**: Type and special labels

## Maintenance

- Review labels quarterly
- Remove unused labels
- Ensure consistency across issues
- Update this documentation when labels change