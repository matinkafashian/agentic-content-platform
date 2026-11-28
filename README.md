# Hayka Agentic Content Platform

Hayka helps a retail team turn catalog records into reviewed product posts and answer customer questions from its own knowledge base. An operator can draft a caption, edit a product photo, record a voice note and approve exactly what will be sent. A separate customer-support workflow retrieves business information before answering private messages.

The admin interface, generation prompts and bundled sample knowledge are designed for Persian-speaking teams. This guide is in English. You can evaluate drafting and publishing locally without API keys or messaging accounts.

## What to review

| Engineering question | Implementation |
| --- | --- |
| How does the system ground a reply? | The [retriever](app/support/openai_provider.py) combines lexical overlap (40%) with embedding similarity (60%) and selects up to five passages. The [decision engine](app/support/engine.py) routes a grounded answer to human support when it lacks source references or its reported confidence is below 0.90. This threshold is a routing rule, not a measured accuracy score. |
| What is the editor approving? | The [content service](app/content/service.py) maintains draft versions. Approving a replacement supersedes the earlier approved version. The publisher snapshots the selected caption, image and optional voice recording so later edits cannot change a queued post. |
| What happens if delivery fails halfway? | The [publishing tests](tests/publishing/) cover scheduling and platform-specific failures. The system records external message IDs and partial deliveries so a failed follow-up voice note does not trigger a duplicate main post. |
| Where does each integration work? | Telegram, Bale and Rubika support publishing and private customer support. WhatsApp publishing uses an optional local WhatsApp Web bridge. The sandbox simulates delivery without sending a message. |

Hayka is a Python 3.12 modular monolith using FastAPI, Jinja2, SQLAlchemy, Alembic and SQLite. One application worker handles scheduled deliveries and bot polling. OpenAI is optional for template-based drafts and simulated delivery. Model-generated captions, image editing and AI support require appropriate provider credentials.

## Run a local evaluation

From the repository root in Windows PowerShell:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from getpass import getpass; from app.core.security import hash_password; print(hash_password(getpass('Admin password: ')))"
```

Set `SECRET_KEY` and `ADMIN_PASSWORD_HASH` in the local `.env` to the two generated values. Keep `CONTENT_PROVIDER=template`, leave messaging credentials empty and set `DEBUG=true` for **local loopback HTTP only**. Production uses HTTPS and `DEBUG=false` for secure session cookies. The database and upload directory must be writable. See [.env.example](.env.example) for the complete configuration.

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [admin login](http://127.0.0.1:8000/admin/login) and sign in with the configured username and password. The [health endpoint](http://127.0.0.1:8000/health) reports service readiness. Password changes are available at `/admin/security`.

1. Set the brand tone, support handle, call to action and approved commercial claims. Add a product with its actual image and attributes.
2. Generate a template caption from a brief. Review the product facts alongside the editable text, generate a second version and approve one.
3. Optionally record a voice note in a browser on localhost or HTTPS. OGG and WebM recordings are validated by MIME type, signature, size and duration. Defaults are 25 MiB and ten minutes. Original recordings are stored privately.
4. Create a publication bundle, select the **sandbox** destination and schedule it for immediate delivery. Check the delivery record for the simulated message ID.
5. Pause publishing and schedule another bundle. The worker preserves queued jobs while paused. Resume processing to finish the exercise.

## Generation and approval

Set `CONTENT_PROVIDER=openai` and configure `OPENAI_API_KEY` locally to enable paid generation. The Responses API uses a strict JSON schema. Captions use catalog facts and direct price inquiries to the brand contact. Review generated claims before approval. The template provider is labeled separately in the interface.

Image editing supports studio and cinematic modes. The model is asked to preserve product shape, color and material. The application adds branding locally after generation and stores the edit separately from the original. Compare textures, edges and hardware before approval. Edited images and voice recordings are served through authenticated admin routes.

Manual mode requires an approved draft. Automatic mode checks the active product, caption and available image before bundling. Scheduled jobs persist in SQLite. Delivery records track attempts, idempotency keys, external message IDs and errors. Temporary failures use backoff. Permanent configuration errors and partial deliveries require operator review.

## Connect a messaging channel

Use a test destination first. Restart the application after updating its environment.

| Destination | Setup and delivery details |
| --- | --- |
| Telegram | Create a bot with BotFather, grant channel posting rights and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_DEFAULT_DESTINATION` (public handle or private channel ID starting with `-100`). For a forum topic, set `TELEGRAM_MESSAGE_THREAD_ID`. Photo captions are limited to 1,024 characters. Install FFmpeg for WebM/Opus voice delivery, optionally setting `TELEGRAM_FFMPEG_BINARY`. Audio is remuxed to OGG without re-encoding. |
| Bale | Create a bot with [BotFather](https://ble.ir/botfather), grant posting rights and set `BALE_BOT_TOKEN` and `BALE_DEFAULT_DESTINATION` to a channel handle or numeric ID. The adapter uses the [standard Bot API](https://docs.bale.ai/) for the photo, caption and optional voice note. |
| Rubika | Create a bot with [BotFather](https://rubika.ir/BotFather), grant posting rights and set `RUBIKA_BOT_TOKEN` and the channel chat ID in `RUBIKA_DEFAULT_DESTINATION`. The [Bot API](https://rubika.ir/botapi) uses an upload followed by a send operation. Browser recordings are sent as audio files to preserve the original format. |
| WhatsApp | Follow the [bridge setup](services/whatsapp-bridge/README.md). Pair a linked device and select a test group before trying a channel. Delivery depends on the unofficial WhatsApp Web integration. |

Enable inbound support separately with the platform-specific support flags in [.env.example](.env.example). The support engine handles private text messages, ignores channel/group traffic and routes uncertain cases to a human. Its fallback messages and provider instructions are Persian. English-language answer quality has not been established.

## Verification and deployment

```powershell
python -m ruff check app tests
python -m pytest -q
```

Review the [support tests](tests/support/) for decision rules and provider boundaries. Live provider calls and real channel deliveries require separate integration checks with the owner's accounts.

For a single-server deployment, use the [VPS guide](deploy/README.md), [security policy](SECURITY.md) and [handover checklist](docs/security-finalization-checklist.md). Back up SQLite and the complete upload tree at a consistent point in time. Keep real environment files, customer data, private media, bridge tokens and linked-device sessions outside Git.
