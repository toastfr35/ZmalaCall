import { state } from './admin-state.js';
import { el, panel, actionButton, api } from './admin-shared.js';

// @llr SLLR106
export function backupPanel() {
  const section = panel(
    'Backup and restore',
    'Save accounts, terminal settings, groups, pictures, credentials and histories.',
  );
  const controls = el('div', null, 'backup-controls');
  controls.append(actionButton('Manage backups', openBackups, 'secondary', 'server'));
  const result = el('p', null, 'muted');
  result.hidden = true;
  controls.append(result);
  section.append(controls);
  void api('/api/server/backup/status')
    .then((status) => {
      if (status.result === 'restored' || status.result === 'rolled_back') {
        result.hidden = false;
        result.textContent =
          (status.result === 'restored'
            ? 'Last restore completed: '
            : 'Last restore failed; previous configuration recovered: ') +
          new Date(String(status.completed_at)).toLocaleString();
      }
    })
    .catch(() => {});
  return section;
}

/** @param {string} url @param {RequestInit} [options] */
async function backupRequest(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const failure = await response.json();
    throw Error(failure.error || 'Backup operation failed.');
  }
  return response;
}

// @llr SLLR106
export function openBackups() {
  const dialog = el('dialog', null, 'backup-dialog');
  dialog.setAttribute('aria-labelledby', 'backup-title');
  const title = el('h2', 'Backup and restore');
  title.id = 'backup-title';
  const status = el('p', '', 'muted');
  status.setAttribute('role', 'status');
  const warning = el(
    'p',
    'Backups contain passwords and private pictures. They are not encrypted: keep the file in a private, secure location.',
    'muted',
  );
  const download = actionButton(
    'Download backup',
    async () => {
      status.textContent = 'Preparing backup…';
      try {
        const response = await backupRequest('/api/server/backup');
        const url = URL.createObjectURL(await response.blob());
        const anchor = el('a');
        anchor.href = url;
        anchor.download =
          response.headers.get('content-disposition')?.match(/filename="([^"]+)"/)?.[1] ||
          'zmala-server.zmala-backup';
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        status.textContent = 'Backup download started.';
      } catch (error) {
        status.textContent = error instanceof Error ? error.message : 'Download failed.';
      }
    },
    'primary',
    'down',
  );
  const input = el('input');
  input.type = 'file';
  input.accept = '.zmala-backup';
  input.id = 'backup-file';
  const label = el('label', 'Choose a backup to restore');
  label.htmlFor = input.id;
  const summary = el('p', '', 'muted');
  /** @type {File | undefined} */ let checkedFile;
  let checkedVersion = -1;
  const check = actionButton('Check backup', async () => {
    restore.disabled = true;
    checkedFile = undefined;
    const file = input.files?.[0];
    if (!file) {
      status.textContent = 'Choose a backup file first.';
      return;
    }
    if (file.size > 64 * 1024 * 1024) {
      status.textContent = 'Backup must be at most 64 MB.';
      return;
    }
    input.disabled = true;
    status.textContent = 'Checking backup…';
    try {
      const response = await backupRequest('/api/server/backup/check', {
        method: 'POST',
        body: file,
      });
      const preview = await response.json();
      checkedFile = file;
      checkedVersion = preview.configuration_version;
      summary.textContent = `Created ${new Date(preview.created_at).toLocaleString()} · ${preview.accounts} accounts · ${preview.terminals} terminals · ${preview.groups} groups · ${preview.pictures} pictures`;
      status.textContent =
        'Backup is valid. Restoring replaces the current data and signs everyone out. Use the administrator password saved in this backup afterward.';
      restore.disabled = false;
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : 'Backup check failed.';
      summary.textContent = '';
    } finally {
      input.disabled = false;
    }
  });
  const restore = actionButton(
    'Replace configuration',
    async () => {
      if (
        !checkedFile ||
        !window.confirm(
          'Replace all current accounts, settings, pictures and histories with this backup? The server will restart.',
        )
      )
        return;
      input.disabled = check.disabled = restore.disabled = download.disabled = true;
      status.textContent = 'Preparing restore…';
      try {
        await backupRequest('/api/server/backup/restore', {
          method: 'POST',
          body: checkedFile,
          headers: {
            'X-Zmala-Confirm-Restore': 'replace',
            'X-Zmala-Configuration-Version': String(checkedVersion),
          },
        });
        state.restoring = true;
        close.disabled = true;
        status.textContent = 'Restarting server… You will be asked to sign in again.';
        // Wait for the old session to disappear, not merely for the old process to reply.
        for (let attempt = 0; attempt < 60; attempt++) {
          await new Promise((resolve) => setTimeout(resolve, 1000));
          try {
            const response = await fetch('/api/server/backup/status');
            if (response.status === 401) {
              location.reload();
              return;
            }
          } catch {
            /* The service may be between listeners. */
          }
        }
        status.textContent =
          'The server has not returned yet. Reload this page shortly; if it remains unavailable, check the server service and its recovery backup.';
      } catch (error) {
        status.textContent =
          error instanceof Error
            ? error.message
            : 'Restore failed. Reload the page to check the outcome.';
      } finally {
        input.disabled = check.disabled = download.disabled = close.disabled = false;
      }
    },
    'danger',
  );
  restore.disabled = true;
  input.onchange = () => {
    checkedFile = undefined;
    restore.disabled = true;
    summary.textContent = '';
    status.textContent = '';
  };
  const close = actionButton('Close', () => dialog.close());
  const footer = el('div', null, 'modal-footer');
  footer.append(close, restore);
  dialog.append(
    title,
    warning,
    download,
    el('hr'),
    label,
    input,
    check,
    summary,
    el(
      'p',
      'Calls and remote commands must be finished. The server keeps its current network address, ports, SSH and operating-system configuration. Console commands from the backup are never replayed.',
      'muted',
    ),
    status,
    footer,
  );
  dialog.oncancel = (event) => {
    if (state.restoring) event.preventDefault();
  };
  dialog.onclose = () => dialog.remove();
  document.body.append(dialog);
  dialog.showModal();
}
