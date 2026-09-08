# Demo environment (demo.what-a-benger.net / demo.vertretbar.net)

A third Helm release, `benger-demo` in namespace `benger-demo`, next to prod
(`benger`) and staging (`benger-staging`). It exists so product demos never
show real user data and prospects can try the product themselves.

| | prod | staging | demo |
|---|---|---|---|
| Deployed by | extended `deploy-prod` | extended `deploy-staging` (every PR) | extended `deploy-demo`, right after `deploy-prod` |
| Images | release tag | PR build | **same tag as prod** |
| Data | real | whatever PRs left behind | showcase content, golden snapshot |
| Reset | never | never | nightly 04:00 Europe/Berlin + on demand |
| Values | `values.yaml` | `values-staging.yaml` | `values-demo.yaml` |

## What the chart adds for demo

- `values-demo.yaml` — hosts, cookie domain, `ENVIRONMENT=demo`, `noindex`,
  subchart passwords read from the pre-created credential Secrets, and the
  `demoReset` block.
- `templates/cronjob-demo-reset.yaml` — two CronJobs sharing one pod:
  `benger-demo-reset` (scheduled) and `benger-demo-snapshot` (suspended,
  manual). Both run `pg_dump`/`pg_restore` **inside the postgresql pod** via
  `kubectl exec`, so the tools always match the server major. The golden dump
  lives on the node at `/opt/benger-demo/golden/db.dump`.
- `middleware.noindex` — adds `X-Robots-Tag: noindex, nofollow` to every
  response of the release.
- Frontend `DemoEnvBadge` — a fixed "Demo-Umgebung" pill on the demo hosts,
  resolved from the hostname (`isDemoHost` in `lib/utils/subdomain.ts`).

Host lists that must carry the demo apexes (kept in sync by tests):
`BASE_DOMAINS` / `STUDENT_LOCKED_DOMAINS` / `SISTER_HOSTS` in
`services/frontend/src/lib/utils/subdomain.ts`, `_STUDENT_LOCKED_HOSTS` in
`services/shared/mailer/branding.py`, the vertretbar host list in the extended
student `brand.ts`, and `VERTRETBAR_HOSTS` in the extended billing config.

## Bootstrapping the namespace (once)

```bash
kubectl create ns benger-demo
# pull secret (copy from staging)
kubectl get secret ghcr-secret -n benger-staging -o yaml | sed 's/namespace: benger-staging/namespace: benger-demo/' | kubectl apply -f -
# fresh credentials — never reuse prod/staging values
PG=$(openssl rand -hex 16); RD=$(openssl rand -hex 16)
kubectl -n benger-demo create secret generic benger-postgres-credentials \
  --from-literal=host=benger-demo-postgresql --from-literal=port=5432 \
  --from-literal=username=postgres --from-literal=password=$PG --from-literal=database=benger \
  --from-literal=uri="postgresql://postgres:$PG@benger-demo-postgresql:5432/benger"
kubectl -n benger-demo create secret generic benger-redis-credentials \
  --from-literal=password=$RD --from-literal=uri="redis://:$RD@benger-demo-redis-master:6379/0"
kubectl -n benger-demo create secret generic benger-api-secrets \
  --from-literal=secret_key=$(openssl rand -hex 32) --from-literal=encryption_key=$(openssl rand -hex 32)
kubectl -n benger-demo create secret generic benger-minio-credentials \
  --from-literal=access-key=$(openssl rand -hex 8) --from-literal=secret-key=$(openssl rand -hex 20)
kubectl -n benger-demo create secret generic benger-llm-credentials \
  --from-literal=openai_api_key=<DEDICATED key with a hard monthly cap> --from-literal=anthropic_api_key=""
kubectl -n benger-demo create secret generic benger-email-config \
  --from-literal=SENDGRID_API_KEY=<send-only key> --from-literal=EMAIL_FROM_ADDRESS=noreply@what-a-benger.net --from-literal=EMAIL_FROM_NAME="BenGER Demo"
```

DNS: `demo`, `*.demo`, `api.demo`, `storage.demo` under what-a-benger.net
(Cloudflare, the DNS-01 wildcard cert covers `*.demo.`), and `demo.vertretbar.net`
on Namecheap (HTTP-01 apex cert, issues once the A record resolves).

The `ENCRYPTION_KEY` is fresh, so org-level LLM keys must be entered on the
demo env itself (a prod dump would not decrypt there anyway).

## Golden snapshot and reset

After curating the demo content (showcase org, demo accounts, projects):

```bash
# re-take the golden dump from the current demo DB
kubectl -n benger-demo create job --from=cronjob/benger-demo-snapshot snap-$(date +%s)
# restore it now (what the nightly job does)
kubectl -n benger-demo create job --from=cronjob/benger-demo-reset reset-$(date +%s)
```

Or run the extended repo's **Demo Ops** workflow (Actions → Demo Ops →
`reset` / `snapshot`). A reset scales api/workers/beat to zero, drops and
recreates the database, restores the dump, and scales back up; the api's
startup migration runner then brings an older dump to alembic head. A reset
that fails mid-way leaves the app scaled to zero on purpose: re-run it.

Object storage is not part of the snapshot: nothing deletes objects, the golden
DB only references objects that already exist, and export artifacts expire via
the bucket lifecycle.

## Content rules

- Only self-authored or synthetic content (KI-Generator output, own exams and
  flashcards). Never a prod export that contains other people's submissions.
- Demo accounts are fixed and part of the snapshot; anything a visitor creates
  lives until the next reset. Institutions that want a real trial get their own
  org on prod.
- The demo org's OpenAI key is a dedicated key with a spend cap.
