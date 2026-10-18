'use strict';
// Passwords are salted scrypt hashes; short-lived sessions stay in memory and
// disappear on restart or password change. Never persist a browser credential.
const crypto = require('node:crypto');
const { promisify } = require('node:util');
const scrypt = promisify(crypto.scrypt);
const COOKIE = 'zmala-admin';
const SESSION_MS = 8 * 60 * 60 * 1000;

// @llr LLR-SRV-AUTH-002
/** @param {unknown} password */
async function hashPassword(password) {
  if (typeof password !== 'string' || password.length < 12 || password.length > 256)
    throw Error('Use an admin password between 12 and 256 characters.');
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = await scrypt(password, salt, 64);
  return `${salt}:${hash.toString('hex')}`;
}
/** @param {unknown} password @param {string | undefined} encoded */
async function verifyPassword(password, encoded) {
  if (typeof password !== 'string' || password.length > 256 || !encoded) return false;
  const [salt, expected] = encoded.split(':');
  if (!/^[a-f0-9]{32}$/.test(salt) || !/^[a-f0-9]{128}$/.test(expected)) return false;
  const actual = await scrypt(password, salt, 64);
  return crypto.timingSafeEqual(actual, Buffer.from(expected, 'hex'));
}

class AdminSessions {
  constructor() {
    /** @type {Map<string, number>} */
    this.sessions = new Map();
    /** @type {Map<string, {count: number, until: number}>} */
    this.attempts = new Map();
    this.globalAttempts = { count: 0, until: 0 };
    this.changing = false;
  }
  // @llr LLR-SRV-AUTH-006
  /** Bound hashing work and per-address state even for unauthenticated clients.
   * @param {string} address */
  allowLogin(address) {
    const now = Date.now();
    for (const [key, value] of this.attempts) if (value.until <= now) this.attempts.delete(key);
    if (this.globalAttempts.until <= now) this.globalAttempts = { count: 0, until: now + 60000 };
    if (this.globalAttempts.count >= 30) return false;
    let attempts = this.attempts.get(address);
    if (!attempts) {
      attempts = { count: 0, until: now + 60000 };
      this.attempts.set(address, attempts);
    }
    if (attempts.count >= 5 || this.globalAttempts.count >= 30) return false;
    attempts.count++;
    this.globalAttempts.count++;
    return true;
  }
  // @llr LLR-SRV-AUTH-005
  create() {
    this.prune();
    // Keep session memory bounded; the oldest login must sign in again.
    if (this.sessions.size >= 100) this.sessions.delete(this.sessions.keys().next().value || '');
    const token = crypto.randomBytes(32).toString('base64url');
    this.sessions.set(token, Date.now() + SESSION_MS);
    return token;
  }
  prune() {
    for (const [token, expiry] of this.sessions)
      if (expiry <= Date.now()) this.sessions.delete(token);
  }
  /** @param {string | undefined} token */
  valid(token) {
    this.prune();
    return !!token && this.sessions.has(token);
  }
  /** @param {import('node:http').IncomingMessage} req */
  cookie(req) {
    return req.headers.cookie
      ?.split(';')
      .map((value) => value.trim())
      .find((value) => value.startsWith(COOKIE + '='))
      ?.slice(COOKIE.length + 1);
  }
  // @llr LLR-SRV-AUTH-005
  /** @param {import('node:http').ServerResponse} res @param {string} token
   * @param {boolean} secure @param {boolean} [clear] */
  setCookie(res, token, secure, clear = false) {
    res.setHeader(
      'Set-Cookie',
      `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${clear ? 0 : SESSION_MS / 1000}${secure ? '; Secure' : ''}`,
    );
  }
}
module.exports = { AdminSessions, hashPassword, verifyPassword };
