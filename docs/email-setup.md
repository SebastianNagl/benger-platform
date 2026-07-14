# Transactional email — setup across environments

BenGER sends transactional email (signup verification, password reset,
invitations) via **SendGrid** (`services/shared/mailer/`). The platform serves
two products on two hosts, and the email identity is **host-driven**
(`services/shared/mailer/branding.py`):

| Sending host | From identity | Verify-link host | Language |
|---|---|---|---|
| `what-a-benger.net` | `EMAIL_FROM_ADDRESS` / `EMAIL_FROM_NAME` (BenGER) | `FRONTEND_URL` | en |
| `vertretbar.net` (+ staging/localhost) | `VERTRETBAR_EMAIL_FROM_ADDRESS` / `_FROM_NAME` (default `noreply@vertretbar.net` / "Vertretbar") | derived from the request host (staging→staging, prod→prod, dev→localhost) | de |

So a Vertretbar signup already gets a Vertretbar-branded German email with a
link back to the host the student signed up on — no code change needed per
environment. What differs per environment is **delivery**.

## Local dev — mail catcher (no real delivery)

There is no verified SendGrid sender for `localhost`, so local dev routes sends
to an in-stack **mail catcher** instead (`infra/mailsink/`, a tiny server that
implements the SendGrid `/v3/mail/send` contract). `make dev` starts it
automatically; the api and worker point `SENDGRID_API_URL` at it by default.

- **View captured emails at http://localhost:8026** — with the verify/reset
  links made clickable (they point at `*.localhost`, so click them on this
  machine).
- Full local signup flow: sign up on `vertretbar.localhost` → open
  `localhost:8026` → click the verification link → log in.
- To test against **real** SendGrid instead, set `SENDGRID_API_URL=` (empty) in
  `infra/.env` and configure a verified sender.

## Staging & production — real SendGrid

Delivery uses the per-namespace **`benger-email-config`** Secret
(`SENDGRID_API_KEY`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`, and optional
`VERTRETBAR_EMAIL_FROM_ADDRESS` / `VERTRETBAR_EMAIL_FROM_NAME`). `SENDGRID_API_URL`
is unset there, so the real SendGrid endpoint is used.

**The one requirement to make Vertretbar email deliver:** `vertretbar.net` must
be an **authenticated domain** (or `noreply@vertretbar.net` a verified sender)
in the SendGrid account behind each environment's `benger-email-config`
`SENDGRID_API_KEY`. Without it, SendGrid 403s the send (a valid API key alone is
not enough). Add the domain in SendGrid → Sender Authentication and publish the
CNAME records on the `vertretbar.net` DNS zone; do this for the staging account
and the prod account (whichever accounts those secrets point at). BenGER's
`what-a-benger.net` domain auth is unchanged.

Per-env override (optional): set `VERTRETBAR_EMAIL_FROM_ADDRESS` in that
namespace's `benger-email-config` Secret if an environment must send from a
different verified address; otherwise the `noreply@vertretbar.net` default
applies.
