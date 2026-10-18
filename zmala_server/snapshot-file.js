// @ts-check
'use strict';
const fs = require('node:fs/promises');

/** Serialize complete snapshots per file. Capture bytes before yielding so
 * later in-memory mutations cannot change an earlier queued revision. Callers
 * must await flush before acknowledging a save or stopping the process. */
class SnapshotFile {
  /** @param {string} file */
  constructor(file) {
    this.file = file;
    /** @type {Promise<void>} */
    this.tail = Promise.resolve();
    this.pending = this.tail;
    this.failed = false;
    /** @type {Promise<void> | undefined} */
    this.failedOperation = undefined;
    this.contents = '';
    /** @type {{contents: string} | undefined} */
    this.queued = undefined;
  }
  // @llr LLR-SRV-DATA-014
  /** @param {string} contents @returns {Promise<void>} */
  write(contents) {
    this.contents = contents;
    // Every caller supplies the full latest state. A revision not yet writing
    // can be replaced by a later one; all its acknowledgements wait for that
    // same commit. Retain at most one active and one queued serialized snapshot.
    if (this.queued) {
      this.queued.contents = contents;
      return this.pending;
    }
    const queued = { contents };
    this.queued = queued;
    const temporary = this.file + '.tmp';
    const operation = this.tail.then(async () => {
      this.queued = undefined;
      try {
        await fs.writeFile(temporary, queued.contents);
        await fs.rename(temporary, this.file);
        if (this.pending === operation) this.failed = false;
      } catch (error) {
        if (this.pending === operation) {
          this.failed = true;
          this.failedOperation = operation;
        }
        // Cleanup must not replace the actual disk error or poison the queue.
        await fs.rm(temporary, { force: true }).catch(() => {});
        throw Object.assign(Error('Could not save configuration snapshot.', { cause: error }), {
          status: 500,
        });
      }
    });
    this.pending = operation;
    // Observe rejection even if a synchronous domain method ignores the return
    // value. Preserve it in pending for flush; let a later full snapshot retry.
    this.tail = operation.catch(() => {});
    return operation;
  }
  flush() {
    // Retry the latest immutable revision only on a subsequent barrier call.
    // The original failed write still rejects its acknowledgement.
    if (this.failed && this.pending === this.failedOperation) return this.write(this.contents);
    return this.pending;
  }
}
module.exports = { SnapshotFile };
