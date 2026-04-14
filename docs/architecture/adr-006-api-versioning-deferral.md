# ADR-006: API Versioning Deferral

## Status
Accepted (October 2025)

## Context

During architecture review (Issue #765), it was noted that BenGER's API does not implement versioning (e.g., `/api/v1/`, `/api/v2/`). All endpoints use the `/api/*` pattern without version identifiers. This was flagged as a moderate priority issue requiring implementation of versioning strategy.

### Current API Structure
```
/api/projects
/api/tasks
/api/annotations
/api/evaluations
/api/users
/api/organizations
```

### Concerns Raised
1. Cannot evolve API without breaking clients
2. No way to deprecate endpoints gracefully
3. Mobile apps cannot specify minimum API version
4. Difficult to run A/B tests on API changes

### System Context
- **Primary Client**: Web frontend (same repository, same deployment)
- **External Clients**: None (no public API, no mobile apps, no third-party integrations)
- **API Consumers**: 1 (internal frontend)
- **Breaking Changes**: Rare (can coordinate with frontend)
- **Deployment**: Atomic (frontend + API deployed together)

## Decision

**We have decided to defer API versioning** until external API consumers exist or breaking changes become frequent.

### Rationale

#### 1. No External API Consumers

**Current Reality:**
- Only consumer: BenGER frontend (same repo)
- No public API
- No mobile applications
- No third-party integrations
- No webhooks to external systems

**Versioning Benefit**: Near zero
- Frontend and API deploy atomically
- Breaking changes can be coordinated
- No "old clients" to support

**Industry Examples:**
- Basecamp: No API versioning for years (same repo pattern)
- GitHub: Added versioning only when public API launched
- Stripe: Versioning came with partner integrations

#### 2. Atomic Deployment Pattern

**Current Deployment**:
```
┌─────────────────────────────┐
│  Git Commit                 │
│  ├── Frontend changes       │
│  └── API changes            │
└────────────┬────────────────┘
             │
             ▼
     ┌───────────────┐
     │  CI/CD Build  │
     └───────┬───────┘
             │
             ▼
┌─────────────────────────────┐
│  Kubernetes Deployment      │
│  ├── Frontend (updated)     │
│  └── API (updated)          │
│  (deployed simultaneously)  │
└─────────────────────────────┘
```

**Key Point**: Frontend and API are **always in sync**. No scenario where old frontend talks to new API (or vice versa).

**Versioning Solves**: Asynchronous client/server updates
**BenGER Reality**: Synchronous updates

#### 3. Low Breaking Change Frequency

**Historical Analysis** (git history review):
- 2023: 2 breaking API changes
- 2024: 3 breaking API changes
- 2025: 1 breaking API change (prompt system removal)

**Average**: ~2 breaking changes per year

**With Atomic Deployment**:
- Breaking changes coordinated with frontend updates
- Released together in single deployment
- No old clients to break

**Cost of Versioning**: Maintaining multiple API versions
**Benefit**: Minimal (no clients to protect)

#### 4. Versioning Overhead

**Implementation Cost** (one-time):
- Route restructuring: `/api/*` → `/api/v1/*`
- Update all frontend API calls
- Version negotiation middleware
- Documentation updates
- **Effort**: 2-3 days

**Maintenance Cost** (ongoing):
- Support N and N-1 versions
- Deprecation notices
- Duplicate code for similar endpoints
- Testing matrix expansion (v1 tests + v2 tests)
- Documentation for multiple versions
- **Effort**: +15-20% per API change

**Current ROI**: Negative (cost > benefit with no external clients)

## When to Implement Versioning

### Quantitative Triggers (any 1 met)

| Trigger | Current | Threshold | Priority |
|---------|---------|-----------|----------|
| **External API Consumers** | 0 | 1 | IMMEDIATE |
| **Public API Launch** | No | Yes | IMMEDIATE |
| **Mobile App** | No | Yes | IMMEDIATE |
| **Third-Party Integrations** | 0 | 1 | HIGH |
| **Breaking Changes Frequency** | 2/year | >6/year | MEDIUM |
| **Separate Release Cycles** | No | Yes | MEDIUM |

**Status**: 0/6 triggers met → Versioning not needed

### Qualitative Triggers (any 1 met)

- 🚀 **Public API Beta**: Planning to allow external developers
- 📱 **Mobile App Development**: iOS/Android clients planned
- 🔌 **Webhook System**: External systems need stable contracts
- 🤝 **Partner Integrations**: Third parties building on API
- 📊 **API-as-a-Product**: Commercializing API access

**Status**: None met → Versioning not needed

## Current Breaking Change Process

### Process (without versioning)

1. **Identify Breaking Change**
   - Schema change (rename field, change type)
   - Endpoint removal
   - Behavior change

2. **Coordinate with Frontend**
   - Update frontend code in same commit/PR
   - Ensure tests cover both sides
   - Review both changes together

3. **Deploy Atomically**
   - Single deployment for frontend + API
   - No window where versions mismatch
   - Rollback affects both simultaneously

4. **Migration Path** (if needed)
   - Database migration (Alembic)
   - Data transformation scripts
   - Deployed before code changes

**Key Advantage**: Simplicity. No version negotiation, no duplicate code, no deprecation periods.

### Example: Prompt System Removal (Issue #759)

**Changes Required**:
- Remove `/api/prompts/*` endpoints
- Remove Prompt model from database
- Update frontend to remove prompt UI
- Migration to clean up prompt data

**With Versioning**:
```
/api/v1/prompts  (maintain for deprecation period)
/api/v2/prompts  (removed)
Frontend must handle both versions
Migration period: 3-6 months
```

**Without Versioning** (what we did):
- Single PR with frontend + API changes
- Deployed atomically
- Immediate cleanup (no technical debt)
- Zero maintenance overhead

**Result**: Clean, fast, simple

## Alternatives Considered

### Alternative 1: Implement URL Versioning Now
**Pattern**: `/api/v1/projects`

**Pros:**
- "Best practice"
- Prepared for future external clients

**Cons:**
- 2-3 days implementation
- +15-20% ongoing maintenance
- No current benefit
- Premature optimization

**Decision**: ❌ Rejected - YAGNI (You Aren't Gonna Need It)

### Alternative 2: Header-Based Versioning
**Pattern**: `Accept: application/vnd.benger.v1+json`

**Pros:**
- URLs stay clean
- Versioning in headers

**Cons:**
- More complex than URL versioning
- Harder to test manually
- Same overhead as URL versioning
- Still no benefit without external clients

**Decision**: ❌ Rejected - Even more complex with no benefit

### Alternative 3: Semantic Versioning in Headers
**Pattern**: `X-API-Version: 2025-10-15`

**Pros:**
- Date-based versioning (Stripe pattern)
- Granular version control

**Cons:**
- Complex client implementation
- Same maintenance overhead
- No current benefit

**Decision**: ❌ Rejected - Over-engineering

### Alternative 4: Defer Until Needed (CHOSEN)
**Pattern**: Keep `/api/*`, implement versioning when external clients exist

**Pros:**
- Zero overhead today
- Fast iteration
- Simple codebase
- Clear trigger for implementation

**Cons:**
- Migration work when needed
- Need to coordinate breaking changes

**Decision**: ✅ Accepted - Pragmatic choice

## Migration Plan (When Triggered)

### Phase 1: Version Detection (1 day)
```python
# Add version middleware
@app.middleware("http")
async def version_middleware(request: Request, call_next):
    # Default to v1 for backward compatibility
    version = request.headers.get("X-API-Version", "v1")
    request.state.api_version = version
    return await call_next(request)
```

### Phase 2: Duplicate Routes (1 week)
```python
# Keep existing routes as v1
router_v1 = APIRouter(prefix="/api/v1")
router_v1.include_router(projects_router)

# Add new routes as v2
router_v2 = APIRouter(prefix="/api/v2")
router_v2.include_router(projects_router_v2)

app.include_router(router_v1)
app.include_router(router_v2)
```

### Phase 3: Deprecation Notices (ongoing)
```python
# Add deprecation headers
@router.get("/old-endpoint")
async def old_endpoint():
    headers = {
        "X-API-Deprecated": "true",
        "X-API-Sunset": "2026-12-31",
        "X-API-Replacement": "/api/v2/new-endpoint"
    }
    return Response(content, headers=headers)
```

### Phase 4: Version Retirement (6-12 months)
- Monitor usage of deprecated endpoints
- Notify clients via email/dashboard
- Remove old version when usage < 1%

**Total Effort**: 2-3 weeks + ongoing maintenance

## Documentation Requirements

### Current State (to maintain)
- ✅ OpenAPI/Swagger documentation
- ✅ Clear endpoint documentation
- ✅ Request/response examples
- ✅ Error code documentation

### When Versioning Implemented
- Document version negotiation
- Changelog per version
- Migration guides
- Deprecation timeline
- Version support policy

## Consequences

### Positive
- ✅ **Fast Iteration**: No versioning overhead
- ✅ **Simple Codebase**: Single implementation of each endpoint
- ✅ **Easy Breaking Changes**: Coordinate with frontend directly
- ✅ **No Technical Debt**: No old versions to maintain
- ✅ **Clear Trigger**: Know exactly when to implement

### Negative
- ⚠️ **Migration Work**: Will need versioning when external clients arrive
- ⚠️ **Perception**: May seem "unprofessional" to external observers
- ⚠️ **Breaking Changes**: Need careful coordination with frontend

### Mitigation
- **Document Decision**: This ADR explains rationale
- **Monitor Triggers**: Quarterly review of trigger conditions
- **Quick Implementation**: Migration plan ready when needed
- **Clear Communication**: Team understands when versioning is needed

## Monitoring

### Quarterly Review Checklist
- [ ] Any external API consumers?
- [ ] Public API planned?
- [ ] Mobile app in development?
- [ ] Third-party integrations?
- [ ] Breaking changes frequency increasing?
- [ ] Frontend/API deployment coupling problematic?

**If YES to any**: Initiate versioning implementation

### Metrics to Track
- Number of external API consumers (alert at 1)
- Breaking changes per quarter (alert at 2+)
- Frontend/API deployment coupling issues (alert at 1)

## Related Documents

- [ADR-005](./adr-005-monolith-first-strategy.md): Monolith-First Strategy
- [Issue #765](https://github.com/SebastianNagl/BenGER/issues/765): Architectural Audit
- OpenAPI Specification: `services/api/openapi.json`

## References

- Roy Fielding: [REST APIs must be hypertext-driven](https://roy.gbiv.com/untangled/2008/rest-apis-must-be-hypertext-driven)
- Stripe API Versioning: [Versioning Guide](https://stripe.com/docs/api/versioning)
- Microsoft Azure: [API Versioning](https://docs.microsoft.com/en-us/azure/architecture/best-practices/api-design#versioning-a-restful-web-api)

---

**Author**: Development Team
**Date**: October 2025
**Stakeholders**: Development Team, Product
**Next Review**: Q1 2026
**Implementation Trigger**: First external API consumer
