# ADR-008: Custom API Cache Design

## Status
Accepted (October 2025)

## Context

BenGER's frontend implements a custom API caching layer in `BaseApiClient` instead of using established libraries like React Query or SWR. During architecture review (Issue #765), this was flagged as "reinventing the wheel" and recommended for migration to React Query.

### Current Implementation

**Location**: `services/frontend/src/lib/api/base.ts`

**Key Features**:
```typescript
interface CacheEntry {
  data: any
  timestamp: number
  userId: string | null  // User-aware caching
}

export class BaseApiClient {
  private responseCache = new Map<string, CacheEntry>()
  private lastKnownUserId: string | null = null
  private pendingRequests = new Map<string, Promise<any>>()

  // User-aware cache invalidation
  private invalidateCacheForUserSwitch(newUserId: string) {
    if (this.lastKnownUserId && this.lastKnownUserId !== newUserId) {
      this.responseCache.clear()
    }
    this.lastKnownUserId = newUserId
  }

  // Request deduplication
  private async getCachedOrFetch<T>(cacheKey: string, fetcher: () => Promise<T>): Promise<T> {
    // Check cache
    const cached = this.responseCache.get(cacheKey)
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      return cached.data
    }

    // Deduplicate concurrent requests
    if (this.pendingRequests.has(cacheKey)) {
      return this.pendingRequests.get(cacheKey)
    }

    // Fetch and cache
    const promise = fetcher()
    this.pendingRequests.set(cacheKey, promise)

    try {
      const data = await promise
      this.responseCache.set(cacheKey, {
        data,
        timestamp: Date.now(),
        userId: this.lastKnownUserId
      })
      return data
    } finally {
      this.pendingRequests.delete(cacheKey)
    }
  }
}
```

### Concern Raised
"Custom cache implementation instead of React Query - reinventing the wheel, maintenance burden, missing features (background refetch, optimistic updates)."

## Decision

**We have decided to maintain the custom cache implementation** because it provides critical features that React Query/SWR do not support out-of-the-box.

### Rationale

#### 1. User-Aware Cache Invalidation (Critical Feature)

**Problem**: BenGER supports user switching in same browser session (development feature + multi-user testing)

**Scenario**:
```
1. User A logs in → Fetches projects → Cache stores User A's projects
2. User B logs in (same browser, session manager) → Must NOT see User A's cached data
3. System must invalidate ALL cached data when user switches
```

**React Query Approach**:
```typescript
// React Query: Cache key doesn't include user context automatically
const { data } = useQuery(['projects'], fetchProjects)
// Problem: User B sees User A's cached projects!

// Workaround: Manual user ID in every query key
const { data } = useQuery(['projects', userId], fetchProjects)
// Problem: Every query must remember to include userId
// Problem: Easy to forget, causing data leaks
```

**Custom Cache Approach**:
```typescript
// Automatic user-aware cache
private invalidateCacheForUserSwitch(newUserId: string) {
  if (this.lastKnownUserId && this.lastKnownUserId !== newUserId) {
    this.responseCache.clear()  // Automatic full invalidation
  }
}
```

**Why Custom?**
- Automatic user tracking (can't forget to include userId)
- Fail-safe: All cache cleared on user switch
- Development feature: Essential for testing multi-user scenarios
- **React Query would require custom plugin** (not built-in)

#### 2. Request Throttling Per User

**Feature**: Prevent request flooding, especially for expensive LLM API calls

**Implementation**:
```typescript
private requestCounts = new Map<string, { count: number, resetTime: number }>()

private checkRateLimit(userId: string): boolean {
  const key = `rate_limit_${userId}`
  const now = Date.now()
  const record = this.requestCounts.get(key)

  if (!record || now > record.resetTime) {
    this.requestCounts.set(key, { count: 1, resetTime: now + 60000 })
    return true
  }

  if (record.count >= MAX_REQUESTS_PER_MINUTE) {
    return false  // Rate limited
  }

  record.count++
  return true
}
```

**React Query**: No client-side rate limiting built-in
**SWR**: No client-side rate limiting built-in

**Why Custom?**
- Protects against accidental API floods
- Essential for LLM API cost control
- User-specific limits (not global)

#### 3. Multi-User Session Management

**Use Case**: Development and demo environments support switching between test users

**Requirements**:
```
Admin switches to Contributor view → Cache must clear
Contributor switches back to Admin → Cache must clear
Each user sees only their data (never stale data from previous user)
```

**Custom Cache Benefits**:
- Tracks user ID in each cache entry
- Automatic invalidation on user switch
- No manual intervention required
- **Fail-safe by design**

**React Query Approach**:
- Would need custom query client per user
- Or manual queryClient.clear() calls
- Or user ID in every single query key
- **Error-prone** (easy to miss a query key)

#### 4. Development Experience Priority

**Philosophy**: BenGER prioritizes development experience and safety over "industry standard" tools

**Custom Cache Advantages**:
- Clear, debuggable code (~200 lines)
- No hidden magic
- Team fully understands implementation
- Easy to modify for specific needs
- No dependency updates breaking behavior

**React Query/SWR**:
- ~30KB additional bundle size
- Complex internals (harder to debug)
- Breaking changes in major versions
- May not align with future needs

## React Query Feature Comparison

### Features React Query Provides (We Don't Need)

| Feature | React Query | Custom Cache | Need? |
|---------|-------------|--------------|-------|
| **Background Refetching** | ✅ Built-in | ❌ Manual | ❌ Not needed (data rarely stale) |
| **Automatic Retries** | ✅ Configurable | ❌ Manual | ❌ API failures should surface immediately |
| **Optimistic Updates** | ✅ Built-in | ❌ Manual | ❌ Rare use case in BenGER |
| **Pagination Helpers** | ✅ Built-in | ❌ Manual | ⚠️ Nice to have (implement if needed) |
| **Infinite Scroll** | ✅ Built-in | ❌ Manual | ❌ Not used |
| **DevTools** | ✅ Built-in | ❌ None | ⚠️ Nice to have |

### Features Custom Cache Provides (React Query Doesn't)

| Feature | Custom Cache | React Query | Need? |
|---------|--------------|-------------|-------|
| **User-Aware Invalidation** | ✅ Automatic | ❌ Manual workaround | ✅ **CRITICAL** |
| **Request Throttling** | ✅ Built-in | ❌ External library | ✅ **HIGH** |
| **Session-Aware Caching** | ✅ Automatic | ❌ Manual | ✅ **HIGH** |
| **Fail-Safe User Switch** | ✅ Automatic | ❌ Manual | ✅ **HIGH** |

**Conclusion**: Custom cache provides critical features React Query lacks.

## Migration Cost Analysis

### React Query Migration Effort

**Phase 1: Setup** (1 week)
- Install React Query
- Configure QueryClient
- Setup user-aware query keys pattern
- Implement user switch handling

**Phase 2: Migration** (3-4 weeks)
- Migrate API client methods to hooks (~50 endpoints)
- Update all components using API client (~100 components)
- Implement custom plugins for user awareness
- Testing and bug fixes

**Phase 3: Cleanup** (1 week)
- Remove custom cache code
- Update documentation
- Performance testing

**Total**: 5-6 weeks

### Benefits After Migration
- ⚠️ Background refetching (low value - data rarely stale)
- ⚠️ DevTools (nice but not critical)
- ⚠️ "Industry standard" (perception benefit)
- ❌ User-aware caching (still need custom plugin)
- ❌ Request throttling (still need separate solution)

### Cost-Benefit Analysis
```
Cost: 5-6 weeks engineering time (~$15K-20K)
Benefit: Marginal improvements, lose critical features
ROI: Negative

Decision: Not worth the investment
```

## When to Migrate

### Triggers for Reconsidering

| Trigger | Current | Threshold | Action |
|---------|---------|-----------|--------|
| **Cache Bugs** | 0 | 3+ per quarter | Investigate React Query |
| **Missing Features** | None | Critical feature gap | Evaluate options |
| **Maintenance Burden** | Low | High | Consider migration |
| **Team Consensus** | Custom OK | Prefer React Query | Re-evaluate |
| **User Switch Feature Removed** | No | Yes | **MIGRATE** immediately |

**Key**: If user switching feature is removed, primary blocker for React Query goes away.

### Migration Readiness

**Prerequisites Before Migration**:
1. ✅ Remove user switching feature (or accept manual invalidation)
2. ✅ Implement request throttling elsewhere (API rate limiting)
3. ✅ 5-6 weeks available for migration
4. ✅ Team training on React Query
5. ✅ Consensus that benefits > costs

**Status**: 1/5 prerequisites met → Not ready

## Alternatives Considered

### Alternative 1: Migrate to React Query Now
**Pros:**
- Industry standard
- Rich feature set
- Active community

**Cons:**
- 5-6 weeks effort
- Lose user-aware caching (critical feature)
- Lose request throttling
- Need custom plugins for our needs
- Marginal benefit

**Decision**: ❌ Rejected - Cost > benefit

### Alternative 2: Migrate to SWR
**Pros:**
- Lighter weight than React Query
- Simpler API

**Cons:**
- Same issues as React Query (no user-aware caching)
- Less feature-rich
- Still 4-5 weeks migration

**Decision**: ❌ Rejected - Same issues as React Query

### Alternative 3: Enhance Custom Cache
**Pros:**
- Keep critical features
- No migration cost
- Add missing features incrementally

**Cons:**
- Ongoing maintenance
- Not "industry standard"

**Decision**: ✅ Accepted - Best fit for current needs

#### Enhancements to Consider

1. **Add DevTools** (1-2 days)
   ```typescript
   // Cache visualization in development
   if (process.env.NODE_ENV === 'development') {
     window.__API_CACHE__ = this.responseCache
   }
   ```

2. **Background Refresh** (2-3 days)
   ```typescript
   // Fetch fresh data in background if cache is older than 5 minutes
   if (cached && Date.now() - cached.timestamp > STALE_TIME) {
     fetcher().then(data => this.updateCache(cacheKey, data))
     return cached.data  // Return stale data immediately
   }
   ```

3. **Metrics/Monitoring** (2 days)
   ```typescript
   // Track cache hit rate
   private cacheHits = 0
   private cacheMisses = 0

   getCacheMetrics() {
     return {
       hitRate: this.cacheHits / (this.cacheHits + this.cacheMisses),
       size: this.responseCache.size
     }
   }
   ```

**Total Enhancement Effort**: 1 week vs. 5-6 weeks for React Query migration

## Implementation Details

### Current Cache Architecture

```typescript
┌─────────────────────────────────────────┐
│         BaseApiClient                   │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────────────┐  │
│  │     responseCache (Map)          │  │
│  │  key: url + params               │  │
│  │  value: { data, timestamp, userId}│  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  pendingRequests (Map)           │  │
│  │  (request deduplication)         │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  User Session Tracker            │  │
│  │  lastKnownUserId                 │  │
│  │  (automatic invalidation)        │  │
│  └──────────────────────────────────┘  │
│                                         │
└─────────────────────────────────────────┘
```

### Cache Invalidation Strategies

**1. Time-Based** (30 seconds):
```typescript
const CACHE_TTL = 30000
if (Date.now() - cached.timestamp > CACHE_TTL) {
  // Fetch fresh data
}
```

**2. User Switch**:
```typescript
if (currentUserId !== cached.userId) {
  this.responseCache.clear()
}
```

**3. Mutation-Based** (manual):
```typescript
// After creating project
await apiClient.projects.create(data)
apiClient.invalidateCache('/projects')  // Clear project list cache
```

### Request Flow

```
Component
   │
   ├─ useEffect / onClick
   │
   ▼
apiClient.projects.list()
   │
   ├─ Check cache (with user ID)
   │   ├─ Hit: Return cached
   │   └─ Miss: Continue
   │
   ├─ Check pending requests (deduplication)
   │   ├─ Exists: Return existing promise
   │   └─ None: Continue
   │
   ├─ Check rate limit
   │   ├─ Exceeded: Throw error
   │   └─ OK: Continue
   │
   ├─ Fetch from API
   │
   ├─ Store in cache (with timestamp, userId)
   │
   └─ Return data
```

## Consequences

### Positive
- ✅ **User-Aware Caching**: Automatic, fail-safe
- ✅ **Request Throttling**: Protects against API floods
- ✅ **Multi-User Support**: Critical for development/demo
- ✅ **Simple**: ~200 lines, fully understood by team
- ✅ **No Dependencies**: No external library updates
- ✅ **Fast**: No migration cost
- ✅ **Debuggable**: Clear code, easy to trace

### Negative
- ⚠️ **Maintenance**: Team responsible for cache logic
- ⚠️ **Missing Features**: No background refetch, no DevTools
- ⚠️ **Perception**: May seem "not modern" to external observers

### Mitigation
- **Document Decision**: This ADR explains rationale
- **Enhance Incrementally**: Add features as needed (DevTools, background refresh)
- **Monitor**: Track cache bugs, consider migration if problems emerge

## Testing Strategy

### Current Tests
- Cache hit/miss scenarios
- User switch invalidation
- Request deduplication
- Rate limiting
- TTL expiration

### Additional Tests Needed
- Performance testing (cache size limits)
- Memory leak detection
- Concurrent request handling
- Edge cases (rapid user switching)

## Monitoring

### Metrics to Track
- Cache hit rate (target: >80%)
- Cache size (alert if >1000 entries)
- Cache invalidations per session
- Request duplication prevented
- Rate limit triggers

### Review Schedule
- Quarterly: Review cache performance
- Annual: Evaluate migration to React Query
- Ad-hoc: If 3+ cache bugs per quarter

## Related Documents

- [ADR-003](./adr-003-authentication-architecture-refactor.md): Authentication Architecture (user switching context)
- [ADR-007](./adr-007-state-management-strategy.md): State Management Strategy
- [Issue #765](https://github.com/SebastianNagl/BenGER/issues/765): Architectural Audit

## References

- React Query: [Documentation](https://tanstack.com/query/latest/docs/framework/react/overview)
- SWR: [Documentation](https://swr.vercel.app/)
- [When Not to Use React Query](https://tkdodo.eu/blog/thinking-in-react-query#when-not-to-use-react-query)

---

**Author**: Development Team
**Date**: October 2025
**Stakeholders**: Frontend Team
**Next Review**: Q1 2026
**Migration Trigger**: User switching feature removed OR 3+ cache bugs per quarter
