# Demo environment support in the chart

A deployment can run a demo release next to production and staging, for
example `benger-demo` in namespace `benger-demo`, so product demos never show
real user data and prospects can try the product themselves. Its images are
the production images; its data is showcase content that is reset every night
from a golden snapshot. The environment's own values (hosts, cookie domain,
`ENVIRONMENT=demo`, subchart passwords, the `demoReset` block) belong to the
deployment, not to this repository.

## What the chart adds for demo

- `templates/cronjob-demo-reset.yaml` — two CronJobs sharing one pod:
  `<release>-reset` (scheduled) and `<release>-snapshot` (suspended,
  manual), rendered when `demoReset.enabled`. Both run `pg_dump`/`pg_restore`
  **inside the postgresql pod** via `kubectl exec`, so the tools always match
  the server major. The golden dump lives on the node at `demoReset.hostPath`
  (default `/opt/benger-demo/golden/db.dump`).
- `middleware.noindex` — adds `X-Robots-Tag: noindex, nofollow` to every
  response of the release.
- Frontend `DemoEnvBadge` — a fixed "Demo-Umgebung" pill on the demo hosts,
  resolved from the hostname (`isDemoHost` in `lib/utils/subdomain.ts`).

Host lists that must carry the demo apexes (kept in sync by tests):
`BASE_DOMAINS` / `STUDENT_LOCKED_DOMAINS` / `SISTER_HOSTS` in
`services/frontend/src/lib/utils/subdomain.ts` and `_STUDENT_LOCKED_HOSTS` in
`services/shared/mailer/branding.py`.

## Golden snapshot and reset

After curating the demo content (showcase org, demo accounts, projects):

```bash
# re-take the golden dump from the current demo DB
kubectl -n <namespace> create job --from=cronjob/<release>-snapshot snap-$(date +%s)
# restore it now (what the nightly job does)
kubectl -n <namespace> create job --from=cronjob/<release>-reset reset-$(date +%s)
```

A reset scales api/workers/beat to zero, drops and recreates the database,
restores the dump, and scales back up; the api's startup migration runner then
brings an older dump to alembic head. A reset that fails mid-way leaves the app
scaled to zero on purpose: re-run it.

Object storage is not part of the snapshot: nothing deletes objects, the golden
DB only references objects that already exist, and export artifacts expire via
the bucket lifecycle.

## Content rules

- Only self-authored or synthetic content (KI-Generator output, own exams and
  flashcards). Never a production export that contains other people's
  submissions.
- Demo accounts are fixed and part of the snapshot; anything a visitor creates
  lives until the next reset. Institutions that want a real trial get their own
  org on production.
- Give the demo org a dedicated LLM key with a spend cap.
