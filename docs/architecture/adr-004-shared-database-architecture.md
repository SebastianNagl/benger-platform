# ADR-004: Shared Database Architecture

## Status
Accepted (October 2025)

## Context

During a comprehensive code audit (Issue #765), it was identified that all three services (API, Workers, Frontend) share the same PostgreSQL database, and Workers directly import models from the API service. This was initially flagged as a "distributed monolith anti-pattern" requiring immediate refactoring to separate databases per service.

### Initial Concern
- Workers import API models directly (`from models import LLMModel`)
- All services access same database instance
- Perceived violation of microservices principles
- Concern about inability to scale services independently

### System Context
- **Team Size**: 1-3 developers
- **User Base**: Academic research tool (not high-traffic consumer app)
- **Traffic Pattern**: Moderate, predictable load
- **Development Stage**: Feature development, not at scale
- **Database**: Single PostgreSQL instance on dedicated server

## Decision

**We have decided to maintain the shared database architecture** for the following reasons:

### 1. ACID Transaction Requirements

The system requires atomic multi-table operations that span multiple entities:

```python
# Example: Generation with task updates
@db.transaction
def create_generation_with_task_update(db, task_id, generation_data):
    # Update task status
    task = db.query(Task).filter(Task.id == task_id).first()
    task.status = "generating"

    # Create generation record
    generation = ResponseGeneration(**generation_data)
    db.add(generation)

    # Update project statistics
    project = db.query(Project).filter(Project.id == task.project_id).first()
    project.generation_count += 1

    db.commit()  # All or nothing
```

**With separate databases:**
- Would require distributed transactions (2PC protocol)
- Risk of partial failures and inconsistent state
- Complex rollback procedures
- Significant performance overhead

### 2. Team Size and Complexity Trade-off

**Current Team**: 1-3 developers
- Can easily coordinate schema changes
- Database is not a deployment bottleneck
- Shared understanding of full data model
- No organizational boundaries requiring separation

**Separate Database Overhead**:
- API versioning between services
- Schema synchronization complexity
- Migration coordination across services
- Operational burden (3x database instances)
- Monitoring and backup complexity

**Cost/Benefit**: Complexity cost >> benefits at current scale

### 3. Performance Characteristics

**Current Architecture (Shared DB)**:
- Database query: ~1-5ms
- Transaction: ~10-20ms
- No network latency between services

**Proposed Architecture (Separate DBs)**:
- Database query: ~1-5ms
- API call overhead: +20-50ms per call
- Transaction coordination: +100-200ms
- **Performance degradation: 40-60%** for worker operations

**Worker Use Cases**:
- Celery tasks fetch LLM models, tasks, projects
- ~8 database queries per generation task
- Would require 8 API calls (8x latency)
- LLM generation already slow (~2-30 seconds)
- Additional API overhead acceptable? **No** - compounds user wait time

### 4. Data Ownership Clarity

**Shared Database Does Not Mean Poor Boundaries**:

| Entity | Owner | Access Pattern |
|--------|-------|----------------|
| User, Organization | API | Workers read-only |
| Project, Task | API | Workers read-write |
| ResponseGeneration | Workers | API read-only |
| Evaluation | API | Workers read for context |

**Enforcement**:
- Clear documentation of ownership
- Code review process
- Testing validates boundaries
- Monitoring tracks cross-service queries

### 5. Microservices Scaling Triggers

**When to Split** (none currently met):

| Trigger | Current State | Threshold |
|---------|---------------|-----------|
| Team Size | 1-3 devs | 10+ developers |
| Request Volume | <1000/day | >10,000/day |
| Database Load | 22/100 connections | >80/100 sustained |
| Deployment Conflicts | None | Weekly schema conflicts |
| Regulatory Requirements | None | Data isolation mandated |
| Service-Specific Scaling | None | 10x difference in load |

**Premature Optimization**: Splitting now would be premature optimization for problems that don't exist.

## Alternatives Considered

### Alternative 1: Separate Databases with Event-Driven Architecture
**Pros:**
- Service isolation
- Independent scaling
- Eventual consistency patterns

**Cons:**
- 6-9 months implementation effort
- Complex event sourcing setup
- Debugging difficulty
- Team lacks experience with distributed systems
- **Rejected**: Cost >> benefit at current scale

### Alternative 2: Database Per Service with API-Based Communication
**Pros:**
- Cleaner service boundaries
- Can version APIs independently

**Cons:**
- 40-60% performance degradation
- Distributed transaction complexity
- API versioning overhead
- **Rejected**: Performance impact unacceptable

### Alternative 3: Shared Database with Service-Specific Schemas
**Pros:**
- Logical separation
- Same database instance
- Clear ownership

**Cons:**
- Still single database instance
- Cross-schema queries complex
- Doesn't address "distributed monolith" concern
- **Rejected**: Adds complexity without solving actual problems

## Implementation Details

### Current Architecture

```
┌─────────────┐
│   Frontend  │
└──────┬──────┘
       │ HTTP
       ▼
┌─────────────┐     ┌──────────────┐
│     API     │────▶│  PostgreSQL  │
└──────┬──────┘     └──────────────┘
       │                    ▲
       │ Celery Task        │
       ▼                    │
┌─────────────┐             │
│   Workers   │─────────────┘
└─────────────┘
```

### Model Import Pattern

```python
# services/workers/models.py
from project_models import Task, Project, Annotation  # noqa: F401

# This is intentional, not accidental
# Workers need SQLAlchemy ORM access for ACID transactions
```

### Transaction Boundaries

**API Service Transactions:**
- User authentication
- Project CRUD
- Task assignment
- Annotation management

**Worker Service Transactions:**
- LLM response generation
- Response persistence
- Task status updates
- Statistics calculations

**Atomic Cross-Service Operations:**
- Generation + Task update (requires shared DB)
- Evaluation + Sample results (requires shared DB)

## Consequences

### Positive
- ✅ **ACID Guarantees**: Multi-table operations remain atomic
- ✅ **Performance**: No API call overhead for workers
- ✅ **Simplicity**: Single database to manage
- ✅ **Team Velocity**: Fast development, no distributed system complexity
- ✅ **Cost**: Single database instance (~$50/month)
- ✅ **Debugging**: Easy to trace operations across services
- ✅ **Testing**: Simple test setup with single database

### Negative
- ⚠️ **Coupling**: Services share schema knowledge
- ⚠️ **Migration Coordination**: Schema changes require coordination
- ⚠️ **Scaling Limitation**: Cannot scale services independently (not needed yet)

### Mitigation Strategies

**Schema Change Coordination:**
1. Alembic migrations in API service (single source of truth)
2. Workers import models from API (consistency)
3. Integration tests verify worker compatibility
4. Deployment: API first, then workers (same migration state)

**Future Migration Path:**
When triggers are met (10+ developers, 10K+ requests/day):
1. Implement API-based communication layer alongside direct DB access
2. Migrate worker operations incrementally
3. Monitor performance impact
4. When 80% migrated, split databases
5. Estimated effort: 6-9 months

## Scaling Strategy

### Current Scale (2025)
- Database: 22/100 connections
- Request volume: <1000/day
- Team: 1-3 developers
- **Status**: Shared database appropriate

### Medium Scale (2026-2027)
- Database: 40-60/100 connections
- Request volume: 5000-10,000/day
- Team: 4-8 developers
- **Action**: Add read replicas, optimize queries
- **Architecture**: Keep shared database

### Large Scale (2028+)
- Database: >80/100 connections sustained
- Request volume: >50,000/day
- Team: >10 developers
- **Action**: Evaluate microservices split
- **Triggers**: Deployment conflicts, regulatory requirements

## Monitoring

### Key Metrics to Track
- Database connection count (alert at 80/100)
- Query latency (alert at >100ms p95)
- Worker task throughput
- Schema migration frequency (alert at >1/week)
- Cross-service query patterns

### Review Triggers
- Quarterly review of connection usage
- Annual review of team size and scaling needs
- Immediate review if deployment conflicts occur

## Related Documents

- [Issue #765](https://github.com/SebastianNagl/BenGER/issues/765): Code Audit - Architectural Findings
- [ADR-005](./adr-005-monolith-first-strategy.md): Monolith-First Strategy
- CLAUDE.md: Database initialization and migration procedures

## References

- Martin Fowler: [MonolithFirst](https://martinfowler.com/bliki/MonolithFirst.html)
- Sam Newman: "Building Microservices" - Chapter 3: Splitting the Monolith
- [Database Per Service Pattern](https://microservices.io/patterns/data/database-per-service.html)

---

**Author**: Development Team
**Date**: October 2025
**Stakeholders**: Development Team, Operations
**Next Review**: Q1 2026 or when team size reaches 8 developers
