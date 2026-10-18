// @ts-check
'use strict';
// Shared HTTP response encoding and bounded JSON request parsing.

/** @param {import('node:http').ServerResponse} res @param {number} status
 * @param {unknown} value @param {string} [type] */
function send(res, status, value, type = 'application/json', cache = 'no-store') {
  res.writeHead(status, {
    'Content-Type': type,
    'Cache-Control': cache,
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy':
      "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'",
  });
  if (type === 'application/json') res.end(JSON.stringify(value));
  else if (typeof value === 'string' || value instanceof Uint8Array) res.end(value);
  else throw TypeError('Non-JSON responses require text or bytes.');
  return true;
}

/** @param {number} status @param {string} message */
function httpError(status, message) {
  return Object.assign(Error(message), { status });
}

/** @param {import('node:http').IncomingMessage} req @param {number} [limit] */
async function body(req, limit = 2 * 1024 * 1024) {
  const parts = [];
  let size = 0;
  for await (const part of req) {
    size += part.length;
    if (size > limit) throw httpError(413, 'Upload is too large.');
    parts.push(part);
  }
  return Buffer.concat(parts);
}

// @llr LLR-SRV-AUTH-009
/** @param {import('node:http').IncomingMessage} req @param {number} [limit]
 * @param {boolean} [allowEmpty] @returns {Promise<Record<string, unknown>>} */
async function readJson(req, limit, allowEmpty = false) {
  const text = (await body(req, limit)).toString('utf8');
  let value;
  try {
    value = JSON.parse(allowEmpty && !text ? '{}' : text);
  } catch {
    throw httpError(400, 'Send a valid JSON object.');
  }
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw httpError(400, 'Send a valid JSON object.');
  return value;
}

/** @param {string | undefined} id @returns {string} */
function requireDevice(id) {
  if (!id) throw httpError(401, 'Device authentication required.');
  return id;
}

module.exports = { send, body, readJson, httpError, requireDevice };
