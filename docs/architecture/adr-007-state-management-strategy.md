# ADR-007: State Management Strategy

## Status
Accepted (October 2025)

## Context

BenGER's frontend uses multiple state management approaches: Zustand stores, React Context, and component local state. During architecture review (Issue #765), this was flagged as "mixed state management patterns" requiring consolidation to a single approach (preferably Zustand or React Query).

### Current State Management

**Zustand Stores** (Global State):
- `stores/projectStore.ts` - Project list, filters, selections
- `stores/notificationStore.ts` - Notification management
- `stores/uiStore.ts` - UI preferences, sidebar state
- `stores/annotationStore.ts` - Annotation UI state

**React Context**:
- `contexts/AuthContext.tsx` (566 lines) - Authentication, user, organizations

**Local State**:
- Form inputs
- Modal open/closed
- Component-specific UI state

### Concern Raised
"Inconsistent state management creates confusion about where to put new state. Consolidate to single pattern (Zustand)."

## Decision

**We have decided to maintain the current multi-pattern approach** with clear guidelines for when to use each pattern.

### Rationale

#### 1. Different State Types Require Different Solutions

**State Type Taxonomy**:

| State Type | Example | Best Tool | Rationale |
|-----------|---------|-----------|-----------|
| **Server State** | User profile, projects | Custom Cache | Need user-aware invalidation |
| **Client State** | UI preferences | Zustand | Simple global state |
| **Context/DI** | Auth, API clients | React Context | Dependency injection |
| **Component State** | Form inputs | useState | Ephemeral, local |

**Key Insight**: There is no single "best" state management tool. Different patterns for different needs.

**Reference**: [Application State Management with React](https://kentcdodds.com/blog/application-state-management-with-react) by Kent C. Dodds

#### 2. React Context Is Not State Management

**Common Misconception**: React Context = State Management
**Reality**: React Context = Dependency Injection

**AuthContext Purpose** (from ADR-003):
```typescript
// AuthContext provides authentication services
// Not storing "state" - providing authentication runtime
export const AuthContext = createContext<AuthService>(null)

// Components inject the auth service
const { user, login, logout } = useAuth()
```

**Key Point**: AuthContext is 566 lines because it provides:
- Authentication service
- Session management
- Organization management
- Development utilities

**This is appropriate** - services are naturally larger than state containers.

**Industry Pattern**:
- Angular: Dependency injection via services (similar pattern)
- Vue: `provide/inject` for services
- React: Context for services, Zustand/Redux for state

#### 3. React Query Evaluated and Rejected

**ADR-003 Analysis** (January 2025):
> "We evaluated migrating authentication to React Query but decided against it because:
> 1. No Clear Benefits: Auth state is simple user/loading/organizations
> 2. Architecture Mismatch: React Query is designed for server state, not client auth
> 3. Unnecessary Complexity: Would require adapters between React Query and auth patterns
> 4. Working System: The refactored AuthContext is clean, testable, and functional"

**Current Custom Cache** (see ADR-008) provides:
- User-aware cache invalidation (React Query doesn't)
- Request throttling per user
- Multi-user session handling
- 30-second cache TTL with user switching

**React Query Would Require**:
- Custom plugins for user-aware invalidation
- Wrapper layer for user context
- Migration effort: 4-6 weeks
- **Benefit**: Minimal (our cache already works)

## State Management Guidelines

### Decision Tree

```
Is this state...

┌─ Server data (projects, users, tasks)?
│  └─ Use: BaseApiClient (custom cache) or direct API call
│
├─ Global UI state (sidebar, theme, preferences)?
│  └─ Use: Zustand store
│
├─ Service/Runtime (auth, API clients)?
│  └─ Use: React Context (dependency injection)
│
└─ Component-specific (form inputs, modal open)?
   └─ Use: useState/useReducer (local state)
```

### Examples

#### ✅ Correct: Project List (Zustand)
```typescript
// stores/projectStore.ts
export const useProjectStore = create((set) => ({
  selectedProjectIds: [],
  filters: { search: '', archived: false },
  setSelectedProjects: (ids) => set({ selectedProjectIds: ids }),
  setFilters: (filters) => set({ filters }),
}))
```

**Why Zustand?**
- Global UI state (selection, filters)
- Not server data (that comes from API)
- Needs to be shared across components
- Simple state updates

#### ✅ Correct: Auth Service (React Context)
```typescript
// contexts/AuthContext.tsx
export const AuthContext = createContext<AuthService>(null)

export const useAuth = () => useContext(AuthContext)

// This is dependency injection, not state management
```

**Why Context?**
- Provides authentication runtime
- Service, not state
- Needed by many components
- Singleton pattern

#### ✅ Correct: Form State (Local)
```typescript
// components/ProjectForm.tsx
export function ProjectForm() {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  // ...
}
```

**Why Local?**
- Component-specific
- Ephemeral (discarded on unmount)
- No need to share
- Simple to reason about

#### ✅ Correct: Server Data (Custom Cache)
```typescript
// Using BaseApiClient with custom cache
const projects = await apiClient.projects.list()
// Cache handles:
// - User-aware invalidation
// - Request deduplication
// - TTL management
```

**Why Custom Cache?** (see ADR-008)
- User-aware invalidation
- Multi-user session handling
- Request throttling

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│                 BenGER Frontend             │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │     React Components                │   │
│  │  ┌─────────┐  ┌──────────┐         │   │
│  │  │ Project │  │  Task    │         │   │
│  │  │  List   │  │  Detail  │         │   │
│  │  └────┬────┘  └─────┬────┘         │   │
│  └───────┼─────────────┼──────────────┘   │
│          │             │                   │
│          ├─────────────┼───────────────┐   │
│          │             │               │   │
│   ┌──────▼─────┐ ┌────▼────┐  ┌──────▼──┐ │
│   │   Zustand  │ │ Context │  │ useState│ │
│   │   Stores   │ │(Auth DI)│  │ (local) │ │
│   └──────┬─────┘ └────┬────┘  └─────────┘ │
│          │            │                    │
│   ┌──────▼────────────▼────────┐          │
│   │   BaseApiClient            │          │
│   │   (Custom Cache)           │          │
│   └──────────┬─────────────────┘          │
│              │                             │
└──────────────┼─────────────────────────────┘
               │ HTTP
               ▼
        ┌─────────────┐
        │   FastAPI   │
        │   Backend   │
        └─────────────┘
```

## When to Consolidate

### Triggers for Changing Strategy

| Trigger | Current | Threshold | Action |
|---------|---------|-----------|--------|
| **State Management Bugs** | None | 2+ per quarter | Review patterns |
| **Developer Confusion** | Low | High | Better docs |
| **Performance Issues** | None | Measurable | Optimize cache |
| **React Query Benefits Clear** | No | Yes | Migrate |

**Status**: 0/4 triggers → Keep current approach

### Migration Consideration Criteria

**Consider React Query if:**
- Need advanced features (pagination, optimistic updates)
- Custom cache has 3+ bugs per quarter
- Team consensus that benefits outweigh migration cost
- **Effort**: 4-6 weeks

**Consider Consolidating to Zustand if:**
- AuthContext becomes pure state (no services)
- Context causing performance issues (unnecessary re-renders)
- **Effort**: 1-2 weeks

## Alternatives Considered

### Alternative 1: Migrate Everything to Zustand
**Cons:**
- Would require Zustand stores for auth service (architectural mismatch)
- Loses React Context's dependency injection benefits
- AuthContext is service provider, not state container
- **Decision**: ❌ Rejected - Wrong tool for auth service

### Alternative 2: Migrate to React Query
**Pros:**
- Industry standard for server state
- Built-in cache, refetching, mutations

**Cons:**
- Doesn't support user-aware cache invalidation (our need)
- 4-6 weeks migration effort
- Current cache working well
- ADR-003 already evaluated and rejected
- **Decision**: ❌ Rejected - Cost > benefit

### Alternative 3: Keep Multi-Pattern with Guidelines (CHOSEN)
**Pros:**
- Each pattern used for appropriate state type
- No migration effort
- Leverages strengths of each tool
- Clear decision framework

**Cons:**
- Requires documentation
- Team must understand when to use each

**Decision**: ✅ Accepted - Pragmatic and appropriate

## Implementation

### Documentation (Complete)
- ✅ This ADR documents strategy
- ✅ Decision tree for state placement
- ✅ Examples of each pattern

### Code Organization
```
src/
├── stores/           # Zustand (global UI state)
│   ├── projectStore.ts
│   ├── notificationStore.ts
│   ├── uiStore.ts
│   └── annotationStore.ts
├── contexts/         # React Context (DI)
│   └── AuthContext.tsx
├── lib/
│   └── api/
│       └── base.ts   # Custom cache (server state)
└── components/       # Local state (useState)
```

### Code Review Checklist
**For New State:**
- [ ] Is this server data? → Use API client
- [ ] Is this global UI state? → Use Zustand
- [ ] Is this a service? → Use Context
- [ ] Is this component-specific? → Use local state

### Testing Strategy
- **Zustand**: Unit tests for store logic
- **Context**: Integration tests for service coordination
- **Local State**: Component tests
- **API Cache**: Integration tests with mock API

## Consequences

### Positive
- ✅ **Right Tool for Job**: Each pattern used appropriately
- ✅ **No Migration Needed**: Current architecture working
- ✅ **Clear Guidelines**: Decision tree for new state
- ✅ **Flexibility**: Can use best tool for each scenario
- ✅ **Testability**: 85 passing auth tests, 7,372 total tests passing

### Negative
- ⚠️ **Learning Curve**: Team must understand multiple patterns
- ⚠️ **Documentation Dependency**: Requires maintaining this ADR

### Trade-offs
- **Complexity vs. Appropriateness**: Multiple patterns are more complex but each is appropriate for its use case
- **Consistency vs. Correctness**: Enforcing single pattern would be "consistent" but incorrect for different state types

## Success Metrics

### Current (Baseline)
- ✅ 7,372 passing tests (99.1%)
- ✅ 85 auth tests passing
- ✅ No state management bugs in production
- ✅ Fast feature development

### Ongoing
- Monitor state management bugs (target: <1 per quarter)
- Developer satisfaction with state patterns
- Feature velocity (should remain high)
- Test coverage (maintain >95%)

## Related Documents

- [ADR-003](./adr-003-authentication-architecture-refactor.md): Authentication Architecture Refactor
- [ADR-008](./adr-008-custom-api-cache-design.md): Custom API Cache Design
- [Issue #765](https://github.com/SebastianNagl/BenGER/issues/765): Architectural Audit

## References

- Kent C. Dodds: [Application State Management with React](https://kentcdodds.com/blog/application-state-management-with-react)
- React Docs: [Context](https://react.dev/reference/react/useContext)
- Zustand: [Documentation](https://github.com/pmndrs/zustand)
- React Query: [When to Use](https://tanstack.com/query/latest/docs/framework/react/overview)

---

**Author**: Development Team
**Date**: October 2025
**Stakeholders**: Frontend Team
**Next Review**: Q2 2026 or when state management bugs emerge
