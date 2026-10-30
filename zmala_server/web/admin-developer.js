import { api, el, actionButton } from './admin-shared.js';

// @llr LLR-SRV-HOST-007
/** @param {string} id */
export async function openDeveloperAccess(id) {
  const dialog = el('dialog');
  const status = el('p');
  const explanation = el(
    'p',
    'Developer access stays enabled until you turn it off. Only one terminal can have access. Your development PC must be on the server’s local subnet.',
  );
  const instructions = el(
    'p',
    'Connect through the server to 127.0.0.1 port 22001, using the remote Pi’s own SSH account. Point its C20 at the TV to check the picture during plugin testing.',
  );
  const error = el('p', null, 'banner error');
  error.hidden = true;
  error.setAttribute('role', 'alert');
  const enable = actionButton('Enable for this terminal', async () => change(id), 'primary');
  const disable = actionButton('Disable developer access', async () => change(null), 'secondary');
  const close = actionButton('Close', () => dialog.close(), 'secondary');
  dialog.append(
    el('h2', 'Developer access — ' + id),
    explanation,
    status,
    instructions,
    error,
    enable,
    disable,
    close,
  );
  document.body.append(dialog);
  dialog.showModal();
  let busy = false;
  async function refresh() {
    if (busy || !dialog.open) return;
    busy = true;
    try {
      const data = await api('/api/developer-access');
      status.textContent = !data.supported
        ? 'Not installed on this server.'
        : data.terminal_id
          ? `Enabled for ${data.terminal_id} · ${data.connected ? 'Tunnel connected' : 'Waiting for tunnel'}`
          : 'Developer access is off.';
      enable.disabled = !data.supported || !!data.terminal_id;
      disable.disabled = !data.terminal_id;
    } catch {
      error.textContent = 'Could not read developer access status.';
      error.hidden = false;
    } finally {
      busy = false;
    }
  }
  /** @param {string | null} terminal */
  async function change(terminal) {
    enable.disabled = disable.disabled = true;
    try {
      await api('/api/developer-access', 'PUT', { terminal_id: terminal });
      error.hidden = true;
    } catch (failure) {
      error.textContent =
        failure instanceof Error ? failure.message : 'Developer access change failed.';
      error.hidden = false;
    }
    await refresh();
  }
  const timer = setInterval(refresh, 3000);
  dialog.addEventListener(
    'close',
    () => {
      clearInterval(timer);
      dialog.remove();
    },
    { once: true },
  );
  await refresh();
}
