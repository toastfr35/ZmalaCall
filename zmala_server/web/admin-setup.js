// Authenticated provisioning downloads and local test enrollment actions.
import { $ } from './admin-state.js';
import { link, notice, message, submit } from './admin-shared.js';
/** @param {string} route @param {string} filename @param {import('../types/contracts').JsonObject} [value] */
export async function downloadPdf(route, filename, value) {
  /** @type {Record<string, string>} */
  const headers = {};
  if (value) headers['Content-Type'] = 'application/json';
  const response = await fetch(route, {
    method: value ? 'POST' : 'GET',
    headers,
    body: value ? JSON.stringify(value) : undefined,
  });
  if (!response.ok) throw Error((await response.json()).error || 'PDF generation failed.');
  const url = URL.createObjectURL(await response.blob()),
    a = link('', url);
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  notice('PDF downloaded. Print at actual size, then show the code to the terminal camera.');
}
/** @param {string} id */
export function serverPdf(id) {
  return downloadPdf(
    '/api/setup/server.pdf?id=' + encodeURIComponent(id),
    `zmalacall-server-${id}.pdf`,
  );
}
export function openWifi() {
  message('wifi-error', '');
  $('wifi-form').reset();
  $('wifi-password-field').hidden = false;
  $('wifi-password').required = true;
  $('wifi-dialog').showModal();
}
$('wifi-security').onchange = () => {
  const open = $('wifi-security').value === 'nopass';
  $('wifi-password-field').hidden = open;
  $('wifi-password').required = !open;
  if (open) $('wifi-password').value = '';
};
$('wifi-dialog').addEventListener('close', () => {
  $('wifi-form').reset();
});
$('wifi-form').onsubmit = (e) => {
  e.preventDefault();
  submit(
    $('wifi-form'),
    async () => {
      await downloadPdf('/api/setup/wifi.pdf', 'zmalacall-wifi.pdf', {
        ssid: $('wifi-ssid').value,
        password: $('wifi-password').value,
        security: $('wifi-security').value,
        hidden: $('wifi-hidden').checked,
      });
      $('wifi-dialog').close();
    },
    'wifi-error',
  );
};
