# WhatsApp publishing bridge

This optional Node.js service connects the Python publisher to a linked WhatsApp Web session. It listens on loopback and requires a bearer token for operational endpoints. WhatsApp Web changes can interrupt delivery. Review the [security policy](../../SECURITY.md) and the pinned Puppeteer/Chromium dependency chain before upgrading or deploying.

## Pair a test device

From the repository root:

```powershell
npm ci --prefix services/whatsapp-bridge
npm --prefix services/whatsapp-bridge start
```

On first start, use **Linked devices** in WhatsApp to scan `.whatsapp-runtime/qr.png`. The session is stored in `.whatsapp-session/` and the generated token in `.whatsapp-runtime/bridge-token`. Treat the QR, session and token as private credentials.

Use the local `GET /destinations` endpoint with the bearer token to list visible groups and channels. Set `WHATSAPP_DEFAULT_DESTINATION` to the chosen group (`@g.us`) or channel (`@newsletter`), restart the Python application and test with one message in a test group. The default bridge URL is `http://127.0.0.1:8780`.

The install hook applies a compatibility patch and checks the expected dependency structure. Review audit findings before upgrading the pinned version and validate media delivery against a controlled destination.
