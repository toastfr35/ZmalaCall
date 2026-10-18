// @ts-check
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { validateFiles, encodeBackup, parse } = require('./backup-format');
const { readPhotos, stageRestore } = require('./backup-storage');
const { httpError } = require('./http/responses');

class ServerBackups {
  /** @param {import('./types/contracts').StoreInstance} store
   * @param {import('./types/contracts').CallbackInstance} callbacks
   * @param {InstanceType<typeof import('./console-jobs').ConsoleJobs>} consoleJobs
   * @param {import('./types/http').SipApi} sip
   * @param {() => Promise<void>} flush @param {(() => void) | undefined} restart */
  constructor(store, callbacks, consoleJobs, sip, flush, restart) {
    this.store = store;
    this.callbacks = callbacks;
    this.consoleJobs = consoleJobs;
    this.sip = sip;
    this.flush = flush;
    this.restart = restart;
    this.busy = false;
    this.restoring = false;
    this.requests = 0;
  }
  // @llr LLR-SRV-DATA-008
  async snapshot() {
    // Serialize the complete model before yielding. Pictures have immutable names.
    const files = new Map([
      ['server.json', Buffer.from(JSON.stringify(this.store.value))],
      [
        'admin-password.json',
        Buffer.from(JSON.stringify({ password_hash: this.store.adminPassword.hash })),
      ],
      ['callbacks.json', Buffer.from(JSON.stringify(this.callbacks.requests))],
      ['console-jobs.json', Buffer.from(JSON.stringify(this.consoleJobs.jobs))],
    ]);
    await readPhotos(this.store.dir, files);
    validateFiles(files);
    return files;
  }
  async download() {
    return encodeBackup(await this.snapshot());
  }
  status() {
    const file = path.join(this.store.dir, 'restore-result.json');
    return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : { result: 'none' };
  }
  // @llr LLR-SRV-DATA-010
  /** @param {Awaited<ReturnType<typeof import('./backup-format').decodeBackup>>} backup
   * @param {number} expectedVersion */
  async stage(backup, expectedVersion) {
    if (!this.restart) throw httpError(503, 'Restore requires the supervised server service.');
    if (expectedVersion !== this.store.value.configuration_version)
      throw httpError(409, 'Configuration changed. Check the backup again before restoring.');
    if (
      this.requests > 1 ||
      this.sip.dialogs.size ||
      this.callbacks.sending.size ||
      this.callbacks.email.sending.size ||
      this.consoleJobs.jobs.some((j) => j.status === 'running')
    )
      throw httpError(
        409,
        'Wait for calls, remote commands and other server operations to finish, then retry.',
      );
    this.restoring = true;
    this.sip.maintenance = true;
    this.callbacks.paused = true;
    try {
      await this.flush();
      const previous = await this.snapshot();
      const version =
        Math.max(this.store.value.configuration_version, backup.state.configuration_version) + 1;
      if (!Number.isSafeInteger(version)) throw Error('Configuration revision is too large.');
      backup.state.configuration_version = version;
      // Network identity belongs to this installation, not the old machine.
      // Keep listener ports/address so existing devices and this admin URL remain reachable.
      for (const key of /** @type {const} */ (['host', 'http_port', 'sip_port']))
        backup.state[key] = this.store.value[key];
      backup.files.set('server.json', Buffer.from(JSON.stringify(backup.state)));
      const jobs = parse(backup.files.get('console-jobs.json') || '[]');
      for (const job of jobs) {
        if (['queued', 'running'].includes(job.status)) {
          job.status = job.status === 'queued' ? 'cancelled' : 'lost';
          job.finished_at = new Date().toISOString();
          job.stderr = 'Server backup restored. This command will not be replayed.';
        }
        delete job.lease;
      }
      backup.files.set('console-jobs.json', Buffer.from(JSON.stringify(jobs)));
      await stageRestore(this.store.dir, previous, backup.files);
    } catch (error) {
      // A directory fsync may fail after the commit marker was renamed. Do not
      // resume writes against a transaction that startup will later apply.
      if (fs.existsSync(path.join(this.store.dir, 'restore-recovery', 'pending.json'))) {
        setTimeout(() => this.restart?.(), 250).unref();
        throw httpError(
          503,
          'Restore recovery is pending. The server is restarting; sign in again to check the outcome.',
        );
      }
      this.restoring = false;
      this.sip.maintenance = false;
      this.callbacks.paused = false;
      throw error;
    }
  }
}
module.exports = { ServerBackups };
