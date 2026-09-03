'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');

require('dotenv').config({ path: path.resolve(process.cwd(), '.env') });

const QRCode = require('qrcode');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');

const host = '127.0.0.1';
const port = integerEnv('WHATSAPP_BRIDGE_PORT', 8780, 1, 65535);
const ackTimeoutMs = integerEnv('WHATSAPP_ACK_TIMEOUT_MS', 20000, 1000, 60000);
const mediaRoot = path.resolve(process.env.UPLOAD_DIR || 'uploads');
const sessionRoot = path.resolve(
  process.env.WHATSAPP_SESSION_DIR || '.whatsapp-session',
);
const runtimeRoot = path.resolve(
  process.env.WHATSAPP_RUNTIME_DIR || '.whatsapp-runtime',
);
const qrPath = path.join(runtimeRoot, 'qr.png');
const tokenPath = path.join(runtimeRoot, 'bridge-token');

fs.mkdirSync(mediaRoot, { recursive: true });
fs.mkdirSync(sessionRoot, { recursive: true });
fs.mkdirSync(runtimeRoot, { recursive: true });
const bridgeToken = loadOrCreateBridgeToken();

let connectionState = 'starting';
let lastError = null;
let latestQrAt = null;
const acknowledgementById = new Map();
const acknowledgementWaiters = new Map();
const completedRequests = new Map();

const client = new Client({
  authStrategy: new LocalAuth({
    clientId: 'hayka-content-platform',
    dataPath: sessionRoot,
  }),
  puppeteer: {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  },
});

client.on('qr', async (qr) => {
  connectionState = 'qr_required';
  latestQrAt = new Date().toISOString();
  lastError = null;
  try {
    await QRCode.toFile(qrPath, qr, {
      errorCorrectionLevel: 'M',
      margin: 2,
      width: 420,
    });
    console.log(`[whatsapp] QR ready: ${qrPath}`);
  } catch (_error) {
    lastError = 'qr_write_failed';
    console.error('[whatsapp] QR image could not be written');
  }
});

client.on('authenticated', () => {
  connectionState = 'authenticated';
  lastError = null;
});

client.on('ready', () => {
  connectionState = 'ready';
  lastError = null;
  removeQrFile();
  console.log('[whatsapp] client is ready');
});

client.on('auth_failure', () => {
  connectionState = 'auth_failure';
  lastError = 'authentication_failed';
  console.error('[whatsapp] authentication failed; a fresh QR is required');
});

client.on('disconnected', (reason) => {
  connectionState = 'disconnected';
  lastError = safeReason(reason);
  console.error(`[whatsapp] disconnected: ${lastError}`);
});

client.on('change_state', (state) => {
  if (connectionState !== 'ready') {
    connectionState = String(state || 'unknown').toLowerCase();
  }
});

client.on('message_ack', (message, acknowledgement) => {
  const messageId = serializedMessageId(message);
  if (!messageId) return;
  const current = acknowledgementById.get(messageId) ?? -1;
  acknowledgementById.set(messageId, Math.max(current, acknowledgement));
  if (acknowledgement >= 1) {
    const waiter = acknowledgementWaiters.get(messageId);
    if (waiter) {
      clearTimeout(waiter.timer);
      acknowledgementWaiters.delete(messageId);
      waiter.resolve(true);
    }
  }
});

const server = http.createServer(async (request, response) => {
  try {
    if (request.method === 'GET' && request.url === '/health') {
      return json(response, 200, {
        ok: true,
        state: connectionState,
        ready: connectionState === 'ready',
        qr_available: fs.existsSync(qrPath),
        qr_generated_at: latestQrAt,
        last_error: lastError,
      });
    }
    if (!authorized(request)) {
      return json(response, 401, {
        ok: false,
        error_code: 'whatsapp_bridge_unauthorized',
        retryable: false,
      });
    }
    if (request.method === 'GET' && request.url === '/destinations') {
      if (connectionState !== 'ready') return notReady(response);
      const chats = await client.getChats();
      const destinations = chats
        .filter((chat) => chat.isGroup || chat.isChannel)
        .map((chat) => ({
          id: chat.id?._serialized || '',
          name: String(chat.name || chat.formattedTitle || 'بدون نام'),
          kind: chat.isChannel ? 'channel' : 'group',
          read_only: Boolean(chat.isReadOnly),
        }))
        .filter((item) => validDestination(item.id));
      return json(response, 200, { ok: true, destinations });
    }
    if (request.method === 'POST' && request.url === '/send') {
      if (connectionState !== 'ready') return notReady(response);
      const body = await readJson(request);
      const result = await sendBundle(body);
      return json(response, result.status, result.body);
    }
    return json(response, 404, { ok: false, error_code: 'not_found' });
  } catch (error) {
    console.error(`[whatsapp] request failed: ${safeReason(error?.message)}`);
    return json(response, 500, {
      ok: false,
      error_code: 'whatsapp_bridge_error',
      retryable: true,
    });
  }
});

server.listen(port, host, () => {
  console.log(`[whatsapp] bridge listening on http://${host}:${port}`);
});

client.initialize().catch((error) => {
  connectionState = 'startup_failed';
  lastError = safeReason(error?.message);
  console.error(`[whatsapp] startup failed: ${lastError}`);
});

async function sendBundle(body) {
  const idempotencyKey = String(body?.idempotency_key || '').trim();
  if (!/^[A-Za-z0-9-]{8,80}$/.test(idempotencyKey)) {
    return badRequest('whatsapp_media_invalid');
  }
  if (completedRequests.has(idempotencyKey)) {
    return completedRequests.get(idempotencyKey);
  }
  const destination = String(body?.destination || '').trim();
  if (!validDestination(destination)) {
    return badRequest('whatsapp_destination_invalid');
  }
  const imagePath = safeMediaPath(body?.image_path);
  const voicePath = body?.voice_path ? safeMediaPath(body.voice_path) : null;
  if (!imagePath || (body?.voice_path && !voicePath)) {
    return badRequest('whatsapp_media_invalid');
  }

  const sentIds = [];
  try {
    const imageMedia = MessageMedia.fromFilePath(imagePath);
    const imageResult = await sendAndConfirm(destination, imageMedia, {
      caption: String(body?.caption || ''),
      sendSeen: false,
    });
    if (imageResult.id) sentIds.push(imageResult.id);
    if (!imageResult.acknowledged) {
      const result = unverified(sentIds);
      completedRequests.set(idempotencyKey, result);
      return result;
    }
  } catch (error) {
    return sendFailure(error);
  }

  if (voicePath) {
    try {
      const voiceMedia = MessageMedia.fromFilePath(voicePath);
      const voiceResult = await sendAndConfirm(destination, voiceMedia, {
        sendAudioAsVoice: false,
        sendSeen: false,
      });
      if (voiceResult.id) sentIds.push(voiceResult.id);
      if (!voiceResult.acknowledged) {
        const result = voicePartial(sentIds);
        completedRequests.set(idempotencyKey, result);
        return result;
      }
    } catch (_error) {
      const result = voicePartial(sentIds);
      completedRequests.set(idempotencyKey, result);
      return result;
    }
  }

  const result = {
    status: 200,
    body: { ok: true, message_ids: sentIds },
  };
  completedRequests.set(idempotencyKey, result);
  return result;
}

async function sendAndConfirm(destination, content, options) {
  const message = await client.sendMessage(destination, content, options);
  const id = serializedMessageId(message);
  if (!id) return { id: null, acknowledged: false };
  const acknowledged = await waitForAcknowledgement(id);
  return { id, acknowledged };
}

function waitForAcknowledgement(messageId) {
  if ((acknowledgementById.get(messageId) ?? -1) >= 1) {
    return Promise.resolve(true);
  }
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      acknowledgementWaiters.delete(messageId);
      resolve(false);
    }, ackTimeoutMs);
    acknowledgementWaiters.set(messageId, { resolve, timer });
  });
}

function serializedMessageId(message) {
  const value = message?.id?._serialized;
  return typeof value === 'string' && value ? value : null;
}

function validDestination(value) {
  return /^[0-9]+@(g\.us|newsletter)$/.test(String(value || ''));
}

function safeMediaPath(value) {
  if (typeof value !== 'string' || !value) return null;
  const candidate = path.resolve(value);
  const relative = path.relative(mediaRoot, candidate);
  if (relative.startsWith('..') || path.isAbsolute(relative)) return null;
  try {
    const realRoot = fs.realpathSync(mediaRoot);
    const realCandidate = fs.realpathSync(candidate);
    const realRelative = path.relative(realRoot, realCandidate);
    if (realRelative.startsWith('..') || path.isAbsolute(realRelative)) return null;
    return fs.statSync(realCandidate).isFile() ? realCandidate : null;
  } catch (_error) {
    return null;
  }
}

function authorized(request) {
  const provided = String(request.headers.authorization || '').replace(
    /^Bearer\s+/i,
    '',
  );
  const expected = Buffer.from(bridgeToken);
  const actual = Buffer.from(provided);
  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}

function readJson(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    request.on('data', (chunk) => {
      size += chunk.length;
      if (size > 1024 * 1024) {
        reject(new Error('request_too_large'));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch (_error) {
        reject(new Error('invalid_json'));
      }
    });
    request.on('error', reject);
  });
}

function json(response, status, payload) {
  if (response.headersSent) return;
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  });
  response.end(body);
}

function notReady(response) {
  return json(response, 409, {
    ok: false,
    error_code: 'whatsapp_not_ready',
    retryable: true,
    state: connectionState,
    qr_available: fs.existsSync(qrPath),
  });
}

function badRequest(errorCode) {
  return {
    status: 422,
    body: { ok: false, error_code: errorCode, retryable: false },
  };
}

function unverified(messageIds) {
  return {
    status: 207,
    body: {
      ok: false,
      error_code: 'whatsapp_delivery_unverified',
      retryable: false,
      message_ids: messageIds,
    },
  };
}

function voicePartial(messageIds) {
  return {
    status: 207,
    body: {
      ok: false,
      error_code: 'whatsapp_voice_partial',
      retryable: false,
      message_ids: messageIds,
    },
  };
}

function sendFailure(error) {
  const reason = safeReason(error?.message).toLowerCase();
  const forbidden = /admin|authori[sz]|forbidden|not allowed|read.?only/.test(reason);
  return {
    status: forbidden ? 403 : 502,
    body: {
      ok: false,
      error_code: forbidden
        ? 'whatsapp_send_forbidden'
        : 'whatsapp_bridge_error',
      retryable: !forbidden,
    },
  };
}

function integerEnv(name, fallback, minimum, maximum) {
  const parsed = Number.parseInt(process.env[name] || '', 10);
  if (Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum) {
    return parsed;
  }
  return fallback;
}

function loadOrCreateBridgeToken() {
  const configured = String(process.env.WHATSAPP_BRIDGE_TOKEN || '').trim();
  if (configured) {
    if (configured.length < 32) {
      throw new Error('WHATSAPP_BRIDGE_TOKEN must contain at least 32 characters');
    }
    return configured;
  }
  try {
    const stored = fs.readFileSync(tokenPath, 'utf8').trim();
    if (stored.length < 32) throw new Error('stored bridge token is invalid');
    return stored;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const generated = crypto.randomBytes(32).toString('hex');
  try {
    fs.writeFileSync(tokenPath, generated, {
      encoding: 'utf8',
      flag: 'wx',
      mode: 0o600,
    });
    return generated;
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
    return fs.readFileSync(tokenPath, 'utf8').trim();
  }
}

function safeReason(value) {
  return String(value || 'unknown').replace(/[\r\n\t]/g, ' ').slice(0, 180);
}

function removeQrFile() {
  try {
    if (fs.existsSync(qrPath)) fs.unlinkSync(qrPath);
  } catch (_error) {
    console.error('[whatsapp] stale QR image could not be removed');
  }
}

function shutdown() {
  server.close(() => process.exit(0));
  client.destroy().catch(() => process.exit(1));
  setTimeout(() => process.exit(1), 5000).unref();
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
