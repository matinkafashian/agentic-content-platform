# Security policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability or exposed credential. Contact the repository owner privately and include the affected revision, reproduction steps, and impact. Never include production tokens, passwords, session data, customer media, or database files in a report.

## Public repository boundaries

- Runtime secrets belong only in local or server-side environment files. `.env`, databases, uploads, WhatsApp sessions, QR codes, and generated bridge tokens are intentionally excluded from Git.
- The FastAPI service should be deployed behind HTTPS with `DEBUG=false`; production environment files should be readable only by the service account.
- The WhatsApp bridge is optional, binds to `127.0.0.1`, and uses an unofficial WhatsApp Web dependency. It must not be exposed directly to the internet. Its compatibility and dependency audit status should be reviewed before every production upgrade.
- The pinned WhatsApp Web stack currently includes transitive audit findings for which an automatic compatible fix is not available. Keep the bridge isolated, do not run `npm audit fix --force`, and validate a supported upgrade separately before changing the pinned revision.
- Rotate any credential immediately if it is ever pasted into a public issue, commit, log, screenshot, or chat.
