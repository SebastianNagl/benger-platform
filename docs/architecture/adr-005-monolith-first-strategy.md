# ADR-005: Monolith-First Strategy

## Status
Accepted (October 2025)

## Context

BenGER is structured with three separate services (Frontend, API, Workers) deployed in separate containers, but shares a database and model layer. During architecture review (Issue #765), this was flagged as an inappropriate "distributed monolith" that should be refactored into true microservices with isolated databases and API-based communication.

### The Question
Should BenGER adopt a full microservices architecture now, or continue with the current monolith-first approach?

### System Characteristics
- **Type**: Academic research tool for LLM evaluation
- **Users**: Researchers, not high-volume consumers
- **Team**: 1-3 developers
- **Deployment**: Self-hosted, Kubernetes (k3s)
- **Stage**: Active feature development
- **Maturity**: 2 years in production

## Decision

**We have decided to maintain the monolith-first architecture** and defer microservices adoption until specific scaling triggers are met.

### Rationale

#### 1. Martin Fowler's MonolithFirst Pattern

> "Almost all the successful microservice stories have started with a monolith that got too big and was broken up. Almost all the cases where I've heard of a system that was built as a microservice system from scratch, it has ended up in serious trouble."
> — Martin Fowler, [MonolithFirst](https://martinfowler.com/bliki/MonolithFirst.html)

**Key Principles:**
- Start with modular monolith
- Identify service boundaries through real usage
- Split only when scaling pain points emerge
- Avoid premature optimization

**BenGER Status**: Still identifying optimal service boundaries through usage patterns. Premature split risks incorrect boundaries.

#### 2. Team Size Economics

**Current Team**: 1-3 developers
- Can maintain full system understanding
- No communication overhead
- Fast iteration on features
- Single deployment pipeline

**Microservices Overhead** (per Google/Netflix research):
- Minimum 2 engineers per service for sustainability
- 3 services × 2 engineers = **6 engineers minimum**
- Additional SRE/DevOps overhead
- **Team too small** for microservices

**Reference**: [Microservices Prerequisites](https://martinfowler.com/bliki/MicroservicePrerequisites.html)

#### 3. Domain Boundaries Still Evolving

**Current Architecture** (logical services):
```
┌─────────────────────────────────────┐
│           BenGER Monolith           │
├─────────────────────────────────────┤
│  Authentication & User Management   │
│  Organization & Permissions         │
│  Project Management                 │
│  Task & Annotation System          │
│  LLM Generation Pipeline           │
│  Evaluation & Metrics              │
│  Notification System               │
│  Template Management               │
└─────────────────────────────────────┘
```

**Service Boundary Questions** (still unanswered):
- Should evaluations be separate service? (tightly coupled to projects)
- Should generation be separate? (requires task context)
- Should notifications be separate? (depends on all other domains)
- **Answer**: Unknown until usage patterns stabilize

**Premature Split Risk**: Incorrect boundaries are expensive to fix in microservices.

#### 4. Operational Maturity

**Microservices Prerequisites** (from industry research):
- ✅ Automated deployment pipeline
- ✅ Containerization (Docker)
- ✅ Container orchestration (Kubernetes)
- ❌ Service mesh (Istio/Linkerd)
- ❌ Distributed tracing (Jaeger/Zipkin)
- ⚠️ Centralized logging (basic, needs improvement)
- ❌ Circuit breakers
- ❌ Service discovery (beyond Kubernetes DNS)
- ❌ API gateway
- ❌ Distributed transactions handling

**Score**: 3/10 microservices readiness

**Operational Complexity**: Current team cannot maintain microservices infrastructure.

## Current Architecture

### Physical Deployment
```
┌─────────────┐
│  Frontend   │ (Next.js container)
│  Container  │
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────┐     ┌──────────────┐
│     API     │────▶│  PostgreSQL  │
│  Container  │     │   (shared)   │
└──────┬──────┘     └──────────────┘
       │ Celery
       ▼
┌─────────────┐
│   Workers   │
│  Container  │
└─────────────┘
```

### Logical Modules (within monolith)
```
services/
├── api/              # FastAPI application
│   ├── routers/      # API endpoints by domain
│   ├── models.py     # SQLAlchemy models
│   ├── services/     # Business logic
│   └── middleware/   # Cross-cutting concerns
├── workers/          # Celery async tasks
│   ├── tasks.py      # Task definitions
│   └── models.py     # Model imports (shared)
└── frontend/         # Next.js application
    └── src/
        ├── app/      # Pages
        └── lib/      # API client
```

**Key Point**: Containers ≠ Microservices. This is a **modular monolith** deployed in containers.

## When to Split

### Quantitative Triggers (any 3 met)

| Trigger | Current | Threshold | Met? |
|---------|---------|-----------|------|
| **Team Size** | 1-3 devs | 10+ developers | ❌ |
| **Request Volume** | <1K/day | >50K/day | ❌ |
| **Deployment Frequency** | 1-2/week | >5/day | ❌ |
| **Database Connections** | 22/100 | >80/100 sustained | ❌ |
| **Code Churn** | Manageable | >100 commits/week | ❌ |
| **Service Scaling Mismatch** | None | 10x load difference | ❌ |

**Status**: 0/6 triggers met → Monolith appropriate

### Qualitative Triggers (any 2 met)

| Trigger | Status | Met? |
|---------|--------|------|
| **Deployment Conflicts** | None | ❌ |
| **Team Organizational Boundaries** | Single team | ❌ |
| **Different Scaling Requirements** | None | ❌ |
| **Different Technology Requirements** | None | ❌ |
| **Regulatory Data Isolation** | None | ❌ |
| **Independent Release Cycles Needed** | No | ❌ |

**Status**: 0/6 triggers met → Monolith appropriate

### Early Warning Indicators (monitor quarterly)

- 📊 Database connection usage trending toward 80%
- 👥 Team planning to grow beyond 8 developers
- 🚀 Feature velocity declining due to code complexity
- 🔧 Schema migrations causing deployment delays
- 📈 API latency trending upward (>200ms p95)
- 🔒 Compliance requirements emerging

## Phased Migration Strategy

### Phase 0: Modular Monolith (Current - 2025)
**Focus**: Clear module boundaries within monolith
- Organize code by domain (already done in routers/)
- Document service boundaries
- Enforce boundaries via code review
- Extract business logic to service layer

**Investment**: 1-2 weeks
**Team**: 1-2 developers

### Phase 1: Strangler Fig Pattern (2026+, if needed)
**Focus**: Identify first service to extract
- Extract read-only operations first
- Run old and new in parallel
- Route subset of traffic to new service
- Validate before full migration

**Investment**: 3-4 months
**Team**: 2-3 developers

### Phase 2: Incremental Extraction (2027+, if needed)
**Focus**: Extract remaining services one at a time
- API gateway for routing
- Service mesh for observability
- Event-driven communication
- Database per service

**Investment**: 6-12 months
**Team**: 4-6 developers + SRE

### Phase 3: Full Microservices (2028+, if needed)
**Focus**: Independent service teams
- Team per service (2-3 devs)
- Independent release cycles
- Service-specific databases
- Advanced orchestration

**Investment**: Ongoing
**Team**: 8+ developers + SRE team

## Alternatives Considered

### Alternative 1: Immediate Microservices Split
**Pros:**
- "Best practice" architecture
- Future-proof scaling

**Cons:**
- 6-9 months implementation effort
- Team lacks distributed systems expertise
- Uncertain service boundaries (risk of wrong splits)
- Operational complexity unsustainable for small team
- **Cost**: $150K+ in engineering time

**Decision**: ❌ Rejected - Premature and unsustainable

### Alternative 2: Keep Current "As-Is"
**Pros:**
- No changes needed
- Continue current velocity

**Cons:**
- No plan for future scaling
- No monitoring of scaling triggers
- Risk of emergency refactoring later

**Decision**: ❌ Rejected - Need clear strategy

### Alternative 3: Modular Monolith with Clear Boundaries (CHOSEN)
**Pros:**
- Fast iteration maintained
- Clear service boundaries documented
- Defined scaling triggers
- Incremental migration path
- Team can maintain
- **Cost**: 1-2 weeks documentation

**Decision**: ✅ Accepted - Best fit for current stage

## Implementation

### Immediate Actions (Q4 2025)

1. **Document Service Boundaries** (1 week)
   - Create `docs/architecture/service-boundaries.md`
   - Map domain entities to logical services
   - Document cross-service dependencies

2. **Enforce Module Boundaries** (ongoing)
   - Code review checklist: "Does this cross service boundaries?"
   - Extract business logic to service layer
   - Avoid circular dependencies

3. **Monitor Scaling Triggers** (quarterly)
   - Dashboard for key metrics
   - Team size planning
   - Deployment frequency tracking
   - Database connection monitoring

### Service Layer Extraction (Q1 2026)

```python
# Current: Business logic in routers
@router.post("/projects/{project_id}/generate")
def generate_tasks(project_id: str, config: dict, db: Session):
    project = db.query(Project).filter(Project.id == project_id).first()
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    # ... 50 lines of business logic ...
    return result

# Target: Business logic in service layer
@router.post("/projects/{project_id}/generate")
def generate_tasks(project_id: str, config: dict, db: Session):
    return generation_service.generate_for_project(db, project_id, config)

# services/generation_service.py
class GenerationService:
    def generate_for_project(self, db, project_id, config):
        # Business logic isolated
        # Easy to extract to separate service later
        pass
```

### Monitoring Dashboard (Q2 2026)

Key metrics to track monthly:
- Team size vs. threshold (10 developers)
- Request volume vs. threshold (50K/day)
- Database connections vs. threshold (80/100)
- Deployment conflicts count
- API latency trends
- Feature velocity (story points/sprint)

**Alert**: When 3+ triggers met, initiate Phase 1 planning

## Consequences

### Positive
- ✅ **Fast Iteration**: No distributed system overhead
- ✅ **Team Velocity**: Current team can maintain
- ✅ **Simple Operations**: Single deployment pipeline
- ✅ **Cost-Effective**: No premature infrastructure investment
- ✅ **Clear Strategy**: Defined path to microservices if needed
- ✅ **Risk Mitigation**: Avoid wrong service boundary decisions

### Negative
- ⚠️ **Scaling Ceiling**: Will need refactoring at 10+ developers
- ⚠️ **Technical Debt**: Eventual migration work required
- ⚠️ **Perception**: May be viewed as "not modern" by some

### Risk Mitigation
- **Quarterly Reviews**: Monitor scaling triggers
- **Modular Design**: Clear boundaries enable future extraction
- **Documentation**: Service boundaries documented for future splits
- **Team Education**: Team understands when/why to split

## Success Metrics

### Short-term (2025-2026)
- ✅ Service boundaries documented
- ✅ Business logic extracted to service layer
- ✅ Monitoring dashboard operational
- ✅ Team velocity maintained or improved

### Mid-term (2026-2027)
- ✅ Code organized by domain with clear boundaries
- ✅ <5% circular dependencies between domains
- ✅ Automated testing covers service boundaries
- ✅ Scaling triggers monitored quarterly

### Long-term (2027+)
- ✅ If triggers met: Successful Phase 1 extraction
- ✅ If triggers not met: Monolith still performing well
- ✅ Architecture appropriate for current scale

## Related Documents

- [ADR-004](./adr-004-shared-database-architecture.md): Shared Database Architecture
- [Issue #765](https://github.com/SebastianNagl/BenGER/issues/765): Architectural Audit
- Martin Fowler: [MonolithFirst](https://martinfowler.com/bliki/MonolithFirst.html)
- Sam Newman: "Monolith to Microservices" (O'Reilly)

---

**Author**: Development Team
**Date**: October 2025
**Stakeholders**: Development Team, Product, Operations
**Next Review**: Q1 2026 (quarterly thereafter)
**Decision Makers**: Tech Lead, Product Owner
