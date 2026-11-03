// @ts-check
'use strict';
// Public signed feed caching and independent updater telemetry. No approval queue.
const API = 'https://api.github.com/repos/toastfr35/ZmalaCall/releases/latest';
const PHASES = new Set(['idle', 'request', 'updating', 'checking', 'rollback', 'recovery_failed']);
/** @param {string} value */
function publicAsset(value) {
  try {
    const url = new URL(value);
    return (
      url.protocol === 'https:' &&
      !url.username &&
      !url.password &&
      !url.hash &&
      (!url.port || url.port === '443') &&
      (url.hostname === 'release-assets.githubusercontent.com' ||
        (url.hostname === 'github.com' &&
          url.pathname.startsWith('/toastfr35/ZmalaCall/releases/download/')))
    );
  } catch {
    return false;
  }
}

// @llr LLR-SRV-MAINT-022
class TerminalUpdates {
  /** @param {{clock?: () => number, transport?: typeof fetch}} [options] */
  constructor({ clock = Date.now, transport = fetch } = {}) {
    this.clock = clock;
    this.transport = transport;
    this.expires = 0;
    /** @type {unknown} */
    this.value = null;
    /** @type {Promise<unknown> | null} */
    this.pending = null;
  }
  /** @param {string} url @param {number} limit */
  async json(url, limit) {
    for (let redirects = 0; redirects <= 3; redirects++) {
      if (url !== API && !publicAsset(url)) throw Error('Invalid release address.');
      const response = await this.transport(url, {
        redirect: 'manual',
        signal: AbortSignal.timeout(10000),
        headers: { 'User-Agent': 'ZmalaCall-server-updates', Accept: 'application/json' },
      });
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        const next = response.headers.get('location');
        await response.body?.cancel();
        if (url === API || !next || !publicAsset(next)) throw Error('Invalid release redirect.');
        url = next;
        continue;
      }
      if (!response.ok || !response.body) throw Error('Release unavailable.');
      const reader = response.body.getReader();
      const chunks = [];
      let size = 0;
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.length;
          if (size > limit) throw Error('Release response too large.');
          chunks.push(Buffer.from(value));
        }
      } finally {
        await reader.cancel();
      }
      return JSON.parse(Buffer.concat(chunks).toString('utf8'));
    }
    throw Error('Too many release redirects.');
  }
  async refresh() {
    const release = await this.json(API, 1024 * 1024);
    if (release.draft || release.prerelease) return null;
    if (!Array.isArray(release.assets)) throw Error('Invalid release metadata.');
    const matches = release.assets.filter(
      (/** @type {{name?: string}} */ asset) => asset.name === 'ZmalaTerminal-Update.json',
    );
    if (matches.length === 0) return null;
    if (matches.length !== 1 || !publicAsset(matches[0].browser_download_url))
      throw Error('Invalid update manifest.');
    // Terminals authenticate the envelope themselves; the cache cannot sign it.
    return this.json(matches[0].browser_download_url, 65536);
  }
  async manifest() {
    if (this.pending) return this.pending;
    if (this.clock() < this.expires) return this.value;
    this.pending = this.refresh()
      .then((value) => {
        this.value = value;
        this.expires = this.clock() + 300000;
        return value;
      })
      .catch((error) => {
        this.expires = this.clock() + 60000;
        throw error;
      })
      .finally(() => {
        this.pending = null;
      });
    return this.pending;
  }
}

// @llr LLR-SRV-MAINT-022
/** @param {import('./types/contracts').JsonObject} value @param {number} [now]
 * @returns {import('./types/contracts').TerminalUpdateStatus} */
function updateStatus(value, now = Date.now()) {
  if (typeof value.phase !== 'string' || !PHASES.has(value.phase))
    throw Error('Invalid update phase.');
  /** @type {import('./types/contracts').TerminalUpdateStatus} */
  const result = { phase: value.phase, received_at: new Date(now).toISOString() };
  for (const key of /** @type {const} */ (['installed', 'available'])) {
    if (value[key] == null) continue;
    if (
      typeof value[key] !== 'string' ||
      !/^\d+\.\d+\.\d+$/.test(value[key]) ||
      value[key].length > 32
    )
      throw Error('Invalid update version.');
    result[key] = value[key];
  }
  if (value.error != null) {
    if (typeof value.error !== 'string' || !/^[a-z_]{1,48}$/.test(value.error))
      throw Error('Invalid update error.');
    result.error = value.error;
  }
  return result;
}

// @llr LLR-SRV-MAINT-022
/** @param {import('./types/contracts').TerminalStatus | undefined} status @param {number} [now] */
function updateBusy(status, now = Date.now()) {
  const update = status?.update;
  const age = now - Date.parse(update?.received_at || '');
  return (
    !!update &&
    age >= 0 &&
    age <= 60000 &&
    ['updating', 'checking', 'rollback', 'recovery_failed'].includes(update.phase)
  );
}
module.exports = { TerminalUpdates, updateStatus, updateBusy, publicAsset };
