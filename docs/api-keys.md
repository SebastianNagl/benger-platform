# API keys

Access keys let scripts and other systems call the public API under
`/api/v1` without a browser session. This page describes the model behind
them. The endpoints themselves are documented in [Public API](public-api.md).

## Key format

```
bgr_<live|test>_<kid>_<secret>
```

* `kid` is an 8 character public id, `secret` 43 random characters.
* `bgr_<env>_<kid>` is the key prefix. It is stored in clear and shown in
  every list, so a key can be recognised without revealing it.
* Only a SHA-256 hash of the key (mixed with the server secret
  `API_KEY_PEPPER`) is stored. The full key is shown exactly once, in the
  response that creates it. A lost key cannot be recovered, only replaced.
* Production issues and accepts `live` keys, every other deployment `test`
  keys (`API_KEY_ENVIRONMENT` overrides this). A staging key never works in
  production.

Keys are sent as `Authorization: Bearer bgr_...`. They are never read from a
cookie or a query string, and WebSocket connections refuse them.

## Personal and organisation keys

| | Personal key | Organisation key |
|---|---|---|
| Created by | any user, for themselves | an org admin, or a group admin for their group |
| Acts as | its owner | its own service account |
| Sees | what the owner sees | what the service account's role sees |
| Managed under | `/api/users/me/access-keys` | `/api/organizations/{org_id}/access-keys` |

An organisation key gets a **service account**: a user record that exists
only so the key passes the normal permission checks. It holds an
organisation membership with the key's role (ANNOTATOR or CONTRIBUTOR,
never admin) and, for a group key, a membership in that group. Service
accounts cannot sign in, reset a password or receive notifications, use the
reserved username prefix `svc-`, and do not appear in member lists, member
counts or user lists (superadmins can include them in `GET /api/users` with
`include_service_accounts=true`). Revoking the key deactivates the service
account and ends its memberships.

A key never carries superadmin rights, even when a superadmin created it
for themselves.

## Managing keys in the web UI

* **Organisation keys**: *Users & organizations* → organisation →
  **API access** (org admins, and group admins for their groups).
* **Personal keys**: the **API access** section at the end of the profile
  page.
* **All keys** (superadmins): `/admin/access-keys`, with filters by
  organisation, owner type and status, revocation and the usage CSV.

Creating a key starts from a preset (`benchmark_read`, `benchmark_submit`,
`org_full`); *Advanced* lists every scope the caller may grant. The full key
is shown once, together with `curl` and Python snippets and a **Test
connection** button that calls `GET /api/v1/me` with the new key. **Renew**
creates a key with the same settings; the old key keeps working until it is
revoked, so scripts can switch over without downtime. The how-to guide
*API-Zugänge* (`/how-to#api-zugaenge`) walks non-technical users through
the same steps.

## Principal

Every authenticated request records who is calling as a *principal*
(`request.state.principal`): either a browser session or a key. For a key
the principal also carries its scopes, its optional project list, its
organisation and group, and its rate limits. Browser sessions pass every
scope check.

## Scopes

A key only reaches the `/api/v1` routes its scopes cover. Some scopes imply
others (`submissions:write` implies `submissions:read`).

| Scope | Allows |
|---|---|
| `org:read` | reading the organisation and the key's own membership |
| `projects:read` | reading projects |
| `tasks:read` | reading tasks, without reference solutions |
| `tasks:read_reference` | reading tasks with reference solutions (implies `tasks:read`; only for personal keys and CONTRIBUTOR organisation keys) |
| `submissions:read`, `submissions:write` | reading and creating submissions |
| `systems:read`, `systems:manage` | reading and registering systems |
| `runs:read`, `runs:write` | reading and creating runs |
| `evaluations:read`, `evaluations:run` | reading and starting evaluations |
| `results:read` | reading results |
| `exports:read` | downloading exports |
| `keys:manage` | managing the owner's own keys (personal keys only) |

Overlays can add scopes of their own. `GET /api/access-keys/scopes` lists
all scopes with German and English descriptions plus the presets
`benchmark_read`, `benchmark_submit` and `org_full`.

A key can additionally be limited to a list of projects. A group key only
sees projects attached to its group, and no key sees a project that
requires the Safe Exam Browser. For a key, every project it may not see
answers 404.

## Deny by default

Keys authenticate only on `/api/v1/...` and the health probes. Any other
path answers `401` with the code `api_key_not_allowed_here`, so a key can
never use the browser API. Every `/api/v1` route must declare its scopes;
the API refuses to start when one does not.

A missing scope answers `403 insufficient_scope` with
`WWW-Authenticate: Bearer error="insufficient_scope", scope="..."`.

## Rate limits

Each key has a per-minute and a per-day budget (its own values, or
`API_KEY_DEFAULT_RPM` / `API_KEY_DEFAULT_RPD`). Responses carry
`X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`; an
exhausted budget answers `429` with `Retry-After`.

## Usage log and retention

Every `/api/v1` request made with a key is recorded: key, method, route
template (never the concrete path), project, status, duration, scope, a
shortened client IP (`API_USAGE_IP_MODE`), user agent and byte counts. No
request or response body is stored. Admins see per-key summaries and
events and can export the log as CSV; superadmins can export across all
organisations.

Usage events are deleted after `API_USAGE_RETENTION_DAYS` (default 400) by
a daily task. Deleting a user removes their personal keys and unlinks the
usage history from them; anonymizing a user revokes their personal keys
and removes IP and user agent from their usage history. Deleting an
organisation or a group revokes its keys first.
