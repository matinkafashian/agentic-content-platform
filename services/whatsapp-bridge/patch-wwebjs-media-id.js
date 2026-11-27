'use strict';

const fs = require('fs');
const path = require('path');

const target = path.join(
  __dirname,
  'node_modules',
  'whatsapp-web.js',
  'src',
  'util',
  'Injected',
  'Utils.js',
);
const source = fs.readFileSync(target, 'utf8');
const marker = 'delete message.__x_id;';

if (source.includes(marker)) {
  console.log('[whatsapp] media id compatibility patch already applied');
  process.exit(0);
}

const anchor = `            ...extraOptions,\n        };\n\n        // Bot's won't reply`;
const replacement = `            ...extraOptions,\n        };\n\n        // MediaData exposes an internal id that must not replace the MsgKey.\n        delete message.__x_id;\n\n        // Bot's won't reply`;

if (!source.includes(anchor)) {
  throw new Error('Unsupported whatsapp-web.js Utils.js; media patch anchor missing');
}

fs.writeFileSync(target, source.replace(anchor, replacement), 'utf8');
console.log('[whatsapp] applied media id compatibility patch');
