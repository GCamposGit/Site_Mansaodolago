# DarkFac weekly SEO mailer

This is a one-shot worker for the Hub pilot. It reads Google Search Console,
compares the latest complete Monday-to-Sunday week with the preceding week, and
sends the report by SMTP to the comma-separated recipient list held in the
Dokploy secret store. It does not send to Telegram or to the owner's Hub.

## Build and run once

Build from the repository root on branch `darkfac/m1-seo` (the Docker build
context must be the repository root):

```sh
docker build -f darkfac_mailer/Dockerfile -t darkfac-mailer:latest .
```

Set the runtime variables below in the deployment's secret/environment store,
then run the one-shot command:

```sh
docker run --rm --env-file /path/to/runtime.env darkfac-mailer:latest
```

`runtime.env` is an operator-managed file outside this repository. Do not commit
it, put values in build arguments, or bake values into the image. The image
starts as the unprivileged `app` user and defaults to
`python -m darkfac_mailer.main`. `darkfac_mailer/compose.yaml` provides the
Dokploy Compose service definition; deploy it with the repository root as its
build context and set the service name to `darkfac-mailer`.

## Runtime variables

Configure every variable in Dokploy. Keep credentials and the recipient list
in its secret store; ordinary non-sensitive settings may use Dokploy's regular
environment variables.

| Variable | Purpose |
| --- | --- |
| `MANSAODOLAGO_REPORT_RECIPIENTS` | Required comma-separated administrator recipients; secret-store value only. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Required service-account JSON with read access to the Search Console property; secret-store value only. |
| `GSC_SITE_URL` | Search Console property URL or exact property identifier. |
| `SMTP_HOST` | SMTP server hostname. |
| `SMTP_PORT` | SMTP port; 465 uses implicit TLS, other ports use STARTTLS. |
| `SMTP_USERNAME` | SMTP account; secret-store value only. |
| `SMTP_PASSWORD` | SMTP password; secret-store value only. |
| `SMTP_FROM` | Sender address authorized by the SMTP account. |

The worker validates configuration before sending. Recipient addresses and
credential values are never included in its structured stdout events.

## Dokploy schedule

Create a Dokploy Scheduled Job for this service with:

- Name: `darkfac-mailer`
- Schedule: every Thursday at 09:00
- Time zone: `America/Sao_Paulo`
- Command: `python -m darkfac_mailer.main`
- Source: branch `darkfac/m1-seo`

Use the scheduled job's execution history as the operational record. The
worker emits one JSON line with event `weekly_seo_report`, status, stage, safe
error code, reporting period, and `recipient_count`. Successful deliveries
have `status: "success"`, `stage: "send"`, and `code: "sent"`; the process
exits zero. Failures have `status: "failure"`, a stable code and stage, and
exit nonzero. The event intentionally contains neither recipient addresses nor
credential material.

## Failure recovery

If Dokploy records a nonzero exit, inspect the event's `stage` and `code`, then
check the matching Dokploy secret/configuration or the Google Search Console
and SMTP service status. Correct the configuration in Dokploy and rerun the
one-shot command. Do not paste secret values, recipient addresses, or raw
provider exceptions into tickets or logs. A successful SMTP acceptance is
recorded as `sent`; confirm mailbox receipt with the configured recipients.
