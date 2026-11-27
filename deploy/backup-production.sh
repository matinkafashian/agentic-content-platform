#!/usr/bin/env bash
set -euo pipefail
umask 077
exec 9>/run/hayka-backup.lock
flock -n 9 || exit 0
destination="/var/backups/hayka/$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "$destination"
restart_bridge=0
cleanup() {
  if [ "$restart_bridge" = 1 ]; then systemctl start hayka-whatsapp; fi
}
trap cleanup EXIT
sqlite3 /var/lib/hayka/app.db ".backup '$destination/app.db'"
tar -C /var/lib/hayka -czf "$destination/uploads.tar.gz" uploads
if systemctl is-active --quiet hayka-whatsapp; then
  restart_bridge=1
  systemctl stop hayka-whatsapp
fi
tar -C /var/lib/hayka -czf "$destination/whatsapp-session.tar.gz" whatsapp-session whatsapp-runtime
cleanup
restart_bridge=0
docker exec hayka-n8n-postgres-1 pg_dump -U n8n -d n8n -Fc > "$destination/n8n.dump"
tar -C /etc/hayka -czf "$destination/config-private.tar.gz" app.env n8n.env
(cd "$destination" && sha256sum app.db *.tar.gz n8n.dump > SHA256SUMS)
test "$(sqlite3 "$destination/app.db" 'PRAGMA integrity_check;')" = ok
docker exec -i hayka-n8n-postgres-1 pg_restore --list < "$destination/n8n.dump" > /dev/null
echo "Verified backup: $destination"
