'use strict';
// Durable command queue. A lease authenticates results, and uncertain executions are never replayed automatically.
const { readJson, writeJson } = require('./json-file');
const { retainHistory } = require('./history');

const path = require('node:path');
const crypto = require('node:crypto');
const { SnapshotFile } = require('./snapshot-file');

class ConsoleJobs {
  /** @param {import('./types/contracts').StoreInstance} store */
  constructor(store) {
    this.store = store;
    this.file = path.join(store.dir, 'console-jobs.json');
    /** @type {import('./types/contracts').ConsoleJob[]} */
    this.jobs = readJson(this.file, []);
    this.expire();
  }
  save() {
    if (this.persistence) return this.persistence.write(JSON.stringify(this.jobs, null, 2));
    writeJson(this.file, this.jobs);
  }
  enableAsyncPersistence() {
    this.persistence = new SnapshotFile(this.file);
  }
  async flush() {
    await this.persistence?.flush();
  }
  // "Lost" means unknown outcome, not safe to retry: commands may have external side effects.
  expire() {
    let changed = false;
    const devices = new Set(
      Object.keys(this.store.value.users).map((id) => this.store.terminalAccount(id)?.device_id),
    );
    for (const j of this.jobs) {
      // Legacy username-only records cannot establish the original device.
      // Never attach their commands or output to a possibly reused username.
      if ((!j.device_id || !devices.has(j.device_id)) && ['queued', 'running'].includes(j.status)) {
        j.status = j.status === 'queued' ? 'cancelled' : 'lost';
        j.finished_at = new Date().toISOString();
        j.stderr =
          'Original device is retired or cannot be established. This command will not be run again.';
        changed = true;
      }
      if (
        j.status === 'running' &&
        Date.now() > Date.parse(j.started_at || '') + (j.timeout_seconds + 45) * 1000
      ) {
        j.status = 'lost';
        j.finished_at = new Date().toISOString();
        j.stderr =
          'Terminal stopped reporting. Execution outcome is unknown; this command will not be run again automatically.';
        changed = true;
      }
    }
    if (changed) this.save();
  }
  /** @param {import('./types/contracts').ConsoleJob} job @param {string} id */
  owns(job, id) {
    return !!job.device_id && job.device_id === this.store.terminalAccount(id)?.device_id;
  }
  /** @param {string} first @param {string} second */
  swapTerminals(first, second) {
    for (const job of this.jobs) {
      if (job.terminal_id === first) job.terminal_id = second;
      else if (job.terminal_id === second) job.terminal_id = first;
    }
    this.save();
  }
  /** @param {string} id */
  list(id) {
    this.store.requireTerminal(id);
    this.expire();
    return this.jobs
      .filter((j) => this.owns(j, id))
      .slice(-50)
      .map(({ lease, ...job }) => ({ ...job, terminal_id: id }));
  }
  /** @param {string} id @param {import('./types/contracts').JsonObject} update */
  create(id, { command, timeout_seconds = 60 }) {
    this.store.requireTerminal(id);
    this.expire();
    if (
      typeof command !== 'string' ||
      !command.trim() ||
      command.length > 8000 ||
      command.includes('\0')
    )
      throw Error('Enter a command (up to 8,000 characters).');
    if (
      typeof timeout_seconds !== 'number' ||
      !Number.isInteger(timeout_seconds) ||
      timeout_seconds < 5 ||
      timeout_seconds > 120
    )
      throw Error('Command timeout must be 5–120 seconds.');
    if (
      this.jobs.filter((j) => this.owns(j, id) && ['queued', 'running'].includes(j.status))
        .length >= 10
    )
      throw Error('This terminal already has 10 pending commands.');
    /** @type {import('./types/contracts').ConsoleJob} */
    const job = {
      id: crypto.randomUUID(),
      terminal_id: id,
      device_id: this.store.terminalAccount(id)?.device_id,
      command,
      shell: this.store.value.profiles[id].command_shell || 'powershell',
      timeout_seconds,
      status: 'queued',
      created_at: new Date().toISOString(),
      stdout: '',
      stderr: '',
      exit_code: null,
      truncated: false,
    };
    this.jobs.push(job);
    this.jobs = retainHistory(this.jobs, (j) => ['queued', 'running'].includes(j.status));
    this.save();
    return job;
  }
  /** @param {string} id */
  claim(id) {
    this.store.requireTerminal(id);
    this.expire();
    if (this.jobs.some((j) => this.owns(j, id) && j.status === 'running')) return null;
    const job = this.jobs.find((j) => this.owns(j, id) && j.status === 'queued');
    if (!job) return null;
    job.status = 'running';
    job.shell ??= 'powershell';
    job.started_at = new Date().toISOString();
    // Persist the claim before replying so another poll cannot receive the same command.
    job.lease = crypto.randomBytes(24).toString('hex');
    this.save();
    return {
      id: job.id,
      command: job.command,
      shell: job.shell,
      timeout_seconds: job.timeout_seconds,
      lease: job.lease,
    };
  }
  /** @param {string} id @param {string} jobId @param {import('./types/contracts').JsonObject} result */
  finish(id, jobId, result) {
    this.store.requireTerminal(id);
    const job = this.jobs.find((j) => j.id === jobId && this.owns(j, id));
    if (!job || typeof result.lease !== 'string' || result.lease !== job.lease)
      throw Error('Command result does not match an outstanding command.');
    if (['completed', 'failed', 'timed_out', 'cancelled'].includes(job.status)) return { ok: true };
    if (!['running', 'lost'].includes(job.status)) throw Error('Command is not running.');
    if (
      (result.status !== 'completed' &&
        result.status !== 'failed' &&
        result.status !== 'timed_out' &&
        result.status !== 'cancelled') ||
      (result.exit_code !== null &&
        (typeof result.exit_code !== 'number' || !Number.isInteger(result.exit_code))) ||
      typeof result.stdout !== 'string' ||
      typeof result.stderr !== 'string' ||
      typeof result.truncated !== 'boolean' ||
      Buffer.byteLength(result.stdout) + Buffer.byteLength(result.stderr) > 65536
    )
      throw Error('Invalid command result.');
    /** @type {Pick<import('./types/contracts').ConsoleJob, 'status' | 'exit_code' | 'stdout' | 'stderr' | 'truncated' | 'finished_at'>} */
    const completed = {
      status: result.status,
      exit_code: result.exit_code,
      stdout: result.stdout,
      stderr: result.stderr,
      truncated: result.truncated,
      finished_at: new Date().toISOString(),
    };
    Object.assign(job, completed);
    // Retain the lease internally for idempotent retry if an HTTP reply is lost.
    this.save();
    return { ok: true };
  }
  /** @param {string} id @param {string} jobId */
  cancel(id, jobId) {
    this.store.requireTerminal(id);
    const job = this.jobs.find((j) => j.id === jobId && this.owns(j, id));
    if (!job || job.status !== 'queued') throw Error('Only queued commands can be removed.');
    job.status = 'cancelled';
    job.finished_at = new Date().toISOString();
    this.save();
  }
  /** @param {string} oldId @param {string} newId */
  rename(oldId, newId) {
    let changed = false;
    for (const j of this.jobs)
      if (j.terminal_id === oldId) {
        j.terminal_id = newId;
        changed = true;
      }
    if (changed) this.save();
  }
}
module.exports = { ConsoleJobs };
