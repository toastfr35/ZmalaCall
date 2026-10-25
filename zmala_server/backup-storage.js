// @ts-check
'use strict';
// Restore is a startup transaction: no listener serves a partially replaced store.
const fs = require('node:fs');
const path = require('node:path');
const { FILES, PHOTO, decodeBackup, encodeBackup } = require('./backup-format');
const { SOUND } = require('./ringtones');

/** @param {string} directory */
function syncDirectory(directory) {
  if (process.platform === 'win32') return; // Isolated Windows development tests only.
  const fd = fs.openSync(directory, 'r');
  try {
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}
/** @param {string} file @param {Buffer | string} contents */
function atomicWrite(file, contents) {
  const temporary = file + '.restore-tmp';
  const fd = fs.openSync(temporary, 'w', 0o600);
  try {
    fs.writeFileSync(fd, contents);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(temporary, file);
  syncDirectory(path.dirname(file));
}
/** Only immutable regular images are read. Bound memory before reading each file.
 * @param {string} directory @param {Map<string, Buffer>} files */
async function readPhotos(directory, files) {
  const folder = path.join(directory, 'photos');
  if (!fs.existsSync(folder)) return;
  if (!fs.lstatSync(folder).isDirectory()) throw Error('Invalid pictures directory.');
  let bytes = [...files.values()].reduce((total, value) => total + value.length, 0);
  for (const name of await fs.promises.readdir(folder)) {
    if (!PHOTO.test('photos/' + name)) continue;
    const file = path.join(folder, name),
      stat = await fs.promises.lstat(file);
    if (!stat.isFile()) throw Error('Pictures must be regular files.');
    bytes += stat.size;
    if (bytes > 47 * 1024 * 1024 || files.size >= 1004) throw Error('Backup is too large.');
    files.set('photos/' + name, await fs.promises.readFile(file));
  }
}

// @llr LLR-SRV-CONFIG-024
/** Only the catalog in the captured snapshot owns private immutable audio.
 * @param {string} directory @param {Map<string, Buffer>} files */
async function readRingtones(directory, files) {
  const state = JSON.parse((files.get('server.json') || Buffer.from('{}')).toString());
  let bytes = [...files.values()].reduce((total, value) => total + value.length, 0);
  for (const id of Object.keys(state.ringtones || {})) {
    const name = `ringtones/${id}.wav`;
    if (!SOUND.test(name)) throw Error('Invalid ringtone filename.');
    const file = path.join(directory, name),
      stat = await fs.promises.lstat(file);
    if (!stat.isFile()) throw Error('Ringtones must be regular files.');
    bytes += stat.size;
    if (bytes > 47 * 1024 * 1024 || files.size >= 1004) throw Error('Backup is too large.');
    files.set(name, await fs.promises.readFile(file));
  }
}

/** Replace only known application data. The external password destination comes
 * from local configuration, never from the uploaded archive.
 * @param {string} directory @param {string} passwordFile @param {Map<string, Buffer>} files */
// @llr LLR-SRV-BACKUP-009
function applyFiles(directory, passwordFile, files) {
  const photos = path.join(directory, 'photos');
  const sounds = path.join(directory, 'ringtones');
  fs.mkdirSync(sounds, { recursive: true });
  if (!fs.lstatSync(sounds).isDirectory()) throw Error('Invalid ringtone directory.');
  fs.mkdirSync(photos, { recursive: true });
  if (!fs.lstatSync(photos).isDirectory()) throw Error('Invalid pictures directory.');
  fs.mkdirSync(path.dirname(passwordFile), { recursive: true });
  for (const [name, bytes] of files) {
    if (!FILES.includes(name) && !PHOTO.test(name) && !SOUND.test(name))
      throw Error('Invalid restore filename.');
    const destination = name === 'admin-password.json' ? passwordFile : path.join(directory, name);
    if (fs.existsSync(destination) && !fs.lstatSync(destination).isFile())
      throw Error('Invalid restore destination.');
    atomicWrite(destination, bytes);
  }
  for (const name of fs.readdirSync(photos))
    if (PHOTO.test('photos/' + name) && !files.has('photos/' + name))
      fs.unlinkSync(path.join(photos, name));
  syncDirectory(photos);
  for (const name of fs.readdirSync(sounds))
    if (SOUND.test('ringtones/' + name) && !files.has('ringtones/' + name))
      fs.unlinkSync(path.join(sounds, name));
  syncDirectory(sounds);
}

/** Commit a durable journal last. Before that point the live data is untouched.
 * @param {string} directory @param {Map<string, Buffer>} previous @param {Map<string, Buffer>} next */
// @llr LLR-SRV-BACKUP-007
async function stageRestore(directory, previous, next) {
  const recovery = path.join(directory, 'restore-recovery');
  fs.mkdirSync(recovery, { recursive: true, mode: 0o700 });
  if (!fs.lstatSync(recovery).isDirectory()) throw Error('Invalid recovery directory.');
  if (fs.existsSync(path.join(recovery, 'pending.json')))
    throw Error('A restore is already pending.');
  atomicWrite(path.join(recovery, 'previous.zmala-backup'), await encodeBackup(previous));
  atomicWrite(path.join(recovery, 'next.zmala-backup'), await encodeBackup(next));
  atomicWrite(path.join(recovery, 'pending.json'), JSON.stringify({ phase: 'apply' }));
  syncDirectory(directory);
}

/** Idempotent across power loss in either phase. Failed rollback leaves the journal
 * and fails startup, preserving the recovery backup instead of serving mixed data.
 * @param {string} directory @param {string} passwordFile
 * @param {typeof applyFiles} [apply] */
// @llr LLR-SRV-BACKUP-008
async function recoverRestore(directory, passwordFile, apply = applyFiles) {
  const recovery = path.join(directory, 'restore-recovery'),
    journal = path.join(recovery, 'pending.json');
  if (!fs.existsSync(journal)) return;
  const pending = JSON.parse(fs.readFileSync(journal, 'utf8'));
  let result = 'restored';
  if (pending.phase === 'apply') {
    try {
      const next = await decodeBackup(fs.readFileSync(path.join(recovery, 'next.zmala-backup')));
      apply(directory, passwordFile, next.files);
    } catch {
      atomicWrite(journal, JSON.stringify({ phase: 'rollback' }));
      pending.phase = 'rollback';
    }
  }
  if (pending.phase === 'rollback') {
    const previous = await decodeBackup(
      fs.readFileSync(path.join(recovery, 'previous.zmala-backup')),
    );
    apply(directory, passwordFile, previous.files);
    result = 'rolled_back';
  } else if (pending.phase !== 'apply') throw Error('Invalid restore recovery journal.');
  atomicWrite(
    path.join(directory, 'restore-result.json'),
    JSON.stringify({ result, completed_at: new Date().toISOString() }),
  );
  fs.unlinkSync(journal);
  syncDirectory(recovery);
}
module.exports = {
  atomicWrite,
  readPhotos,
  readRingtones,
  applyFiles,
  stageRestore,
  recoverRestore,
};
