# Problem reports ("Report a problem")

People report a problem from inside the app; each report is stored in the
platform and delivered as an issue of a configured GitHub repository, where
it can be picked up. Everything sits behind the platform flag `bug_reports`
(default `off`, see [feature-flags.md](feature-flags.md)).

## Where people report

- the account menu ("Problem melden" / "Report a problem" / "Signaler un
  problème"),
- the footer of every page, signed in or not,
- the error page that replaces a crashed page, and the last-resort crash card.

The dialog asks for a short summary, what happened and (optionally) what was
expected, takes an optional screenshot by file or by pasting it (PNG, JPEG or
WebP, up to 5 MB) and, without a session, an optional contact address. A
collapsible "What is attached" section shows the technical context exactly as
it will be sent.

## The technical context

Built in the browser when the dialog opens (`src/lib/bugReport/context.ts`)
and reduced again by the server to the keys and sizes it allows
(`services/shared/bug_reports.py`, `clean_context`):

- page path and route parameters (project and task ids), the keys of the
  query string (never its values), the referring page of the same site;
- time, time zone, locale and languages, browser, platform, viewport, screen
  size, device pixel ratio, color scheme, online state;
- edition, active extension packages, the feature flags on for the viewer,
  UI mode and the roles of the viewer's organization memberships (no names);
- the last 5 frontend errors with stack traces, the last 10 failed requests to
  the platform API (method, path, status, request id, duration; never bodies,
  headers, cookies or tokens) and the last 15 page changes
  (`src/lib/bugReport/recorder.ts`). Recording starts when the app loads,
  before the flag has answered, so the failures of the first page load are
  kept; once the flag reads off it stops and drops what it recorded.

Path segments that look like secrets (the token of invitation, activation,
password reset and e-mail links, any long token-like segment that is not a
UUID) are replaced by `[redacted]`, in the browser and again on the server.
The server adds when the report arrived, the deployed app and core versions,
the request's browser line and whether the reporter is a superadmin.

## Storage and limits

`POST /api/bug-reports` (multipart) stores a row in `bug_reports` (migration
160) and the screenshot under the durable `bug_reports/` prefix of object
storage. Limits: summary 150 characters, each text 5000, context 64 KiB,
screenshot 5 MB (type checked by its bytes); 10 reports per hour per user,
3 per hour per client address without a session (429 `rate_limited`). If the
screenshot cannot be stored the report is kept without it.

## Delivery

The worker task `tasks.deliver_bug_report` (queue `maintenance`) creates the
issue. Transient errors (network, timeouts, 5xx, rate limits) retry with
back-off (1, 2, 4, 8, 16 minutes); permanent ones (bad token, missing
repository, validation) fail at once. The report records the issue number and
URL, or the attempts and the last error. A pending report nobody touched for
an hour is queued again by the hourly `tasks.sweep_pending_bug_reports` (its
first send was lost, for example while the broker was down). If the
repository refuses the labels, the issue is created without them.

Reports must stay private, so before creating an issue the worker looks up
the target repository (`GET /repos/{owner}/{name}`, same token) and refuses
it unless GitHub answers `"private": true`. A refused report is kept as
`failed` with the error "Delivery refused: the target repository is not
private", no issue is created, and "Deliver again" sends it once the
repository is private. A confirmed private answer is kept for ten minutes
per worker process; a failing lookup counts like any other delivery error.

Configuration (workers; read on every attempt):

| Variable | Meaning |
|---|---|
| `BUG_REPORT_GITHUB_REPO` | `owner/name` of the repository that receives the issues |
| `BUG_REPORT_GITHUB_TOKEN` | a token that may create issues there; a fine-grained token limited to that repository with "Issues: read and write" is enough (the "Metadata: read" it always includes covers the visibility check) |
| `BUG_REPORT_GITHUB_LABELS` | optional, comma-separated, default `bug,user-report` |
| `BUG_REPORT_GITHUB_API_URL` | optional API base, default `https://api.github.com` |

Without repository or token nothing leaves the platform: reports get the
status `stored` and stay in the superadmin list, from which "Deliver again"
sends them once a target is configured.

## What the issue contains

The summary as title; the reporter's texts and the context in fenced blocks
(so nothing in them renders as markup, links or mentions); recent errors,
failed requests and page changes in collapsed sections; links to the report
in the admin list and to the screenshot. The reporter appears only as an
internal user id (or "not signed in"); no name, e-mail or contact address and
no project or task titles. The issues API takes no attachments, so the
screenshot stays in the platform: its link is the superadmin route
`/api/bug-reports/{id}/screenshot`, never a public URL.

## Superadmin view

`/admin/bug-reports` (account menu, "Problem reports") lists the reports
newest first with status filter, issue link and screenshot; a report opens
below the list (`?report=<id>`, the link in the issue) with its texts,
screenshot, technical context, delivery attempts and last error, and can be
delivered again unless it already has an issue.
