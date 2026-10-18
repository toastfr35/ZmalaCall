// @ts-check
'use strict';
// SIP Digest authentication. Signed, short-lived nonces and nonce counts bound replay attempts.
const crypto = require('node:crypto');
const sip = require('sip');
// MD5 is required by the SIP Digest wire protocol; nonce signatures use HMAC-SHA256.
/** @param {string} s */
const md5 = (s) => crypto.createHash('md5').update(s).digest('hex');
/** @param {unknown} s */
const unquote = (s) => (typeof s === 'string' ? s.replace(/^"|"$/g, '') : '');
class DigestAuth {
  /** @param {string} realm */
  constructor(realm) {
    this.realm = realm;
    this.secret = crypto.randomBytes(32);
    /** @type {Map<string, { count: number; time: number }>} */
    this.seen = new Map();
  }
  nonce() {
    const time = Date.now().toString();
    return Buffer.from(
      `${time}:${crypto.createHmac('sha256', this.secret).update(time).digest('hex')}`,
    ).toString('base64');
  }
  /** @param {import('sip').Message} request @param {boolean} [proxy] */
  challenge(request, proxy = false) {
    const response = sip.makeResponse(
      request,
      proxy ? 407 : 401,
      proxy ? 'Proxy Authentication Required' : 'Unauthorized',
    );
    response.headers[proxy ? 'proxy-authenticate' : 'www-authenticate'] = [
      {
        scheme: 'Digest',
        realm: `"${this.realm}"`,
        nonce: `"${this.nonce()}"`,
        algorithm: 'MD5',
        qop: '"auth"',
      },
    ];
    return response;
  }
  // @llr SLLR026
  /** Return the authenticated username, or null. Consume the nonce count only after verification.
   * @param {import('sip').Message} request
   * @param {Record<string, { password: string }>} users
   * @param {boolean} [proxy] @returns {string | null} */
  verify(request, users, proxy = false) {
    const a = request.headers[proxy ? 'proxy-authorization' : 'authorization']?.[0];
    if (!a || a.scheme?.toLowerCase() !== 'digest') return null;
    const user = unquote(a.username),
      nonce = unquote(a.nonce),
      uri = unquote(a.uri),
      cnonce = unquote(a.cnonce),
      nc = a.nc;
    if (
      !Object.hasOwn(users, user) ||
      unquote(a.realm) !== this.realm ||
      typeof request.uri !== 'string' ||
      uri !== sip.stringifyUri(request.uri) ||
      a.qop !== 'auth' ||
      typeof nc !== 'string' ||
      !/^[a-f\d]{8}$/i.test(nc) ||
      !cnonce ||
      (a.algorithm && a.algorithm.toUpperCase() !== 'MD5')
    )
      return null;
    const [time, signature] = Buffer.from(nonce, 'base64').toString().split(':');
    if (!/^\d+$/.test(time) || Date.now() - Number(time) > 300000 || Number(time) > Date.now())
      return null;
    const expectedSig = crypto.createHmac('sha256', this.secret).update(time).digest('hex');
    if (signature !== expectedSig) return null;
    const expected = md5(
      `${md5(`${user}:${this.realm}:${users[user].password}`)}:${nonce}:${nc}:${cnonce}:auth:${md5(`${request.method}:${uri}`)}`,
    );
    const got = unquote(a.response);
    if (
      !/^[a-f0-9]{32}$/i.test(got) ||
      !crypto.timingSafeEqual(Buffer.from(got), Buffer.from(expected))
    )
      return null;
    // A client nonce has its own increasing count; repeat requests cannot authenticate twice.
    const key = `${nonce}:${user}:${cnonce}`,
      count = parseInt(nc, 16);
    if (count <= (this.seen.get(key)?.count || 0)) return null;
    this.seen.set(key, { count, time: Number(time) });
    for (const [k, v] of this.seen) if (Date.now() - v.time > 300000) this.seen.delete(k);
    return user;
  }
}
module.exports = { DigestAuth };
