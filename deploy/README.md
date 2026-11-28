# Deploy Hayka on a single VPS

The supplied systemd units run FastAPI with **one worker** and the optional WhatsApp bridge on `127.0.0.1:8780`. Multiple application workers can duplicate polling and delivery. Nginx terminates HTTPS. Optional n8n and PostgreSQL services handle monitoring, notifications and backup workflows. Hayka's application database remains SQLite.

## Prepare the host

The reference host is Ubuntu 24.04 with four vCPUs, 8 GB RAM, 80 GB NVMe storage and a static IPv4 address. Prepare DNS and TLS for the panel and, if used, the automation subdomain. Supply fresh owner-managed credentials and a pinned, supported `N8N_VERSION`.

Install Python 3.12, FFmpeg, SQLite and Nginx. Install Node.js 20 or later for the bridge and Docker Engine with Compose for n8n. Create a system account named `hayka` with no login shell and place the checkout at `/opt/hayka/current`. Run the following from that directory with deployment privileges:

```bash
python3.12 -m venv /opt/hayka/venv
/opt/hayka/venv/bin/pip install --upgrade pip
/opt/hayka/venv/bin/pip install /opt/hayka/current
npm ci --prefix /opt/hayka/current/services/whatsapp-bridge
install -d -o hayka -g hayka -m 0700 /var/lib/hayka /etc/hayka
```

Copy `deploy/app.env.example` to `/etc/hayka/app.env`, set the production paths and credentials for enabled integrations, and restrict permissions to `0600`. The service runs migrations before starting. With the WhatsApp integration enabled:

```bash
cp deploy/hayka-app.service deploy/hayka-whatsapp.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hayka-whatsapp hayka-app
```

The owner pairs the device using `/var/lib/hayka/whatsapp-runtime/qr.png`. Protect that file and the session directory.

## HTTPS and optional automation

Replace example hostnames in `nginx.conf.example` and provision valid certificates. Set `DEBUG=false`. Secure session cookies and browser microphone access require HTTPS on the public host.

Copy the n8n environment outside the checkout, set strong credentials and the pinned version **before starting Compose**:

```bash
cp deploy/n8n.env.example /etc/hayka/n8n.env
chmod 0600 /etc/hayka/n8n.env
# Configure /etc/hayka/n8n.env before running the next command.
docker compose --env-file /etc/hayka/n8n.env -f deploy/compose.n8n.yml up -d
```

Keep `N8N_ENCRYPTION_KEY` stable after credentials have been stored. Follow n8n's rotation procedure with a backup if it must change. Run the built-in security audit after setup.

## Backup and handover

The backup script uses SQLite Online Backup and copies media and WhatsApp session data. Run it manually and test recovery before scheduling it daily with a systemd timer or n8n. Configure a separate PostgreSQL backup using `pg_dump` for n8n.

```bash
install -m 0700 deploy/backup.sh /usr/local/sbin/hayka-backup
/usr/local/sbin/hayka-backup
curl --fail https://panel.example.com/health
curl --fail http://127.0.0.1:8780/health
systemctl --no-pager --full status hayka-app hayka-whatsapp
docker compose --env-file /etc/hayka/n8n.env -f deploy/compose.n8n.yml ps
```

Substitute the real panel hostname and run the bridge and Compose checks for enabled services. At handover, test each configured destination with an owner-approved post, ask two private questions per enabled support bot, and verify a backup restore.
