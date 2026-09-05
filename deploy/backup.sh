#!/usr/bin/env bash
set -euo pipefail
umask 077

backup_root="/var/backups/hayka"
state_root="/var/lib/hayka"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${backup_root}/${stamp}"

install -d -m 0700 "${destination}"
sqlite3 "${state_root}/app.db" ".backup '${destination}/app.db'"
tar -C "${state_root}" -czf "${destination}/uploads.tar.gz" uploads
tar -C "${state_root}" -czf "${destination}/whatsapp-session.tar.gz" \
  whatsapp-session whatsapp-runtime
sha256sum "${destination}"/* > "${destination}/SHA256SUMS"

echo "Backup created at ${destination}"
