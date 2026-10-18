// @ts-check
'use strict';
const { body, send, httpError } = require('./responses');
const { MAX_BACKUP, decodeBackup } = require('../backup-format');
// @llr LLR-SRV-BACKUP-012
/** Reached only after the common administrator/session/origin checks.
 * @param {import('node:http').IncomingMessage} req @param {import('node:http').ServerResponse} res
 * @param {URL} url @param {import('../types/http').HttpContext} context */
async function backupRoutes(req, res, url, context) {
  if (!url.pathname.startsWith('/api/server/backup')) return false;
  const service = context.backups;
  if (!service) throw httpError(503, 'Backup service unavailable.');
  if (req.method === 'GET' && url.pathname === '/api/server/backup/status')
    return send(res, 200, service.status());
  const download = req.method === 'GET' && url.pathname === '/api/server/backup';
  const preview = req.method === 'POST' && url.pathname === '/api/server/backup/check';
  const restore = req.method === 'POST' && url.pathname === '/api/server/backup/restore';
  if (!download && !preview && !restore) return false;
  if (service.busy) throw httpError(409, 'Another backup operation is in progress.');
  service.busy = true;
  try {
    if (download) {
      const bytes = await service.download();
      res.setHeader(
        'Content-Disposition',
        'attachment; filename="zmala-server-' +
          new Date().toISOString().replace(/[:.]/g, '-') +
          '.zmala-backup"',
      );
      return send(res, 200, bytes, 'application/octet-stream');
    }
    const backup = await decodeBackup(await body(req, MAX_BACKUP));
    if (preview)
      return send(res, 200, {
        created_at: backup.created_at,
        accounts: Object.keys(backup.state.users).length,
        terminals: Object.keys(backup.state.profiles).length,
        groups: Object.keys(backup.state.groups).length,
        pictures: backup.files.size - 4,
        configuration_version: context.store.value.configuration_version,
      });
    // @llr LLR-SRV-BACKUP-006
    if (req.headers['x-zmala-confirm-restore'] !== 'replace')
      throw httpError(400, 'Confirm replacement before restoring.');
    await service.stage(backup, Number(req.headers['x-zmala-configuration-version']));
    // Restart even if the response is lost. The durable journal is already committed.
    setTimeout(() => service.restart?.(), 250).unref();
    return send(res, 202, { restarting: true });
  } finally {
    service.busy = false;
  }
}
module.exports = { backupRoutes };
