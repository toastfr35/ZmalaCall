// Account list, editing and connection details. Device configuration belongs on the Terminals page.
import { accountPicture, validatePicture, emailAddresses } from './admin-shared.js';
import { $, state } from './admin-state.js';
import {
  el,
  avatar,
  badge,
  link,
  statusBadge,
  iconButton,
  empty,
  actionButton,
  panel,
  icon,
  setView,
  message,
  submit,
  api,
  notice,
  confirm,
} from './admin-shared.js';
import { serverPdf } from './admin-setup.js';
import { writeClipboard } from './admin-clipboard.js';
let accountVersion = 0;
let accountGeneration = 0;
export function accountRows() {
  const tbody = $('account-rows');
  if (!tbody) return;
  tbody.replaceChildren();
  const entries = Object.entries(state.model.users).filter(
    ([id, u]) =>
      (state.accountFilter === 'all' || u.type === state.accountFilter) &&
      `${id} ${u.name}`.toLowerCase().includes(state.accountSearch.toLowerCase()),
  );
  $('account-count').textContent =
    `${entries.length} ${entries.length === 1 ? 'account' : 'accounts'}`;
  for (const [id, u] of entries) {
    const row = el('tr'),
      person = el('td'),
      cell = el('div', null, 'person-cell'),
      names = el('div');
    names.append(el('strong', u.name), el('code', id));
    names.append(
      el('small', u.emails?.length ? u.emails.join(', ') : 'Email address needed', 'muted'),
    );
    cell.append(avatar(u), names);
    person.append(cell);
    row.append(person);
    const type = el('td');
    type.append(
      badge(
        u.type === 'terminal' ? 'Terminal' : 'App',
        u.type === 'terminal' ? 'accent' : 'neutral',
      ),
    );
    row.append(type);
    const groups = el('td', null, 'group-chips');
    for (const key of state.model.account_groups[id])
      groups.append(link(state.model.groups[key].name, '/groups', 'badge accent'));
    if (!groups.children.length) groups.append(el('span', 'No groups', 'muted'));
    row.append(groups);
    const status = el('td');
    status.append(statusBadge(id));
    row.append(status);
    const actions = el('td', null, 'row-actions');
    actions.append(
      iconButton(`Connection details for ${id}`, 'link', () => openConnection(id)),
      iconButton(`Edit account ${id}`, 'edit', () => openAccount(id)),
      iconButton(`Delete account ${id}`, 'trash', () => deleteAccount(id)),
    );
    row.append(actions);
    // Keep table semantics and expose column labels when rows stack on phones.
    row.setAttribute('role', 'row');
    for (const [index, title] of ['Account', 'Type', 'Groups', 'SIP status', 'Actions'].entries()) {
      const cell = row.children[index];
      cell.setAttribute('role', 'cell');
      cell.setAttribute('data-label', title);
    }
    tbody.append(row);
  }
  if (!entries.length) {
    const row = el('tr'),
      cell = el('td');
    cell.colSpan = 5;
    cell.append(empty('No accounts found', 'Try another search or create a new account.'));
    row.append(cell);
    tbody.append(row);
  }
}
export function renderAccounts() {
  $('page-actions').replaceChildren(
    actionButton('New account', () => openAccount(), 'primary', 'plus'),
  );
  const p = panel('People & devices'),
    tools = el('div', null, 'table-toolbar'),
    search = el('div', null, 'search-field'),
    input = el('input');
  input.type = 'search';
  input.placeholder = 'Search accounts…';
  input.setAttribute('aria-label', 'Search accounts');
  input.value = state.accountSearch;
  input.oninput = () => {
    state.accountSearch = input.value;
    accountRows();
  };
  search.append(icon('search'), input);
  const filter = el('select');
  filter.setAttribute('aria-label', 'Filter account type');
  for (const [value, text] of [
    ['all', 'All account types'],
    ['app', 'App'],
    ['terminal', 'Terminal'],
  ]) {
    const o = el('option', text);
    o.value = value;
    filter.append(o);
  }
  filter.value = state.accountFilter;
  filter.onchange = () => {
    state.accountFilter = filter.value;
    accountRows();
  };
  const count = el('span', '', 'muted');
  count.id = 'account-count';
  tools.append(search, filter, count);
  p.append(tools);
  const scroll = el('div', null, 'table-scroll'),
    table = el('table', null, 'accounts-table'),
    head = el('thead'),
    tr = el('tr');
  table.setAttribute('role', 'table');
  table.setAttribute('aria-label', 'Accounts');
  head.setAttribute('role', 'rowgroup');
  tr.setAttribute('role', 'row');
  for (const title of ['Account', 'Type', 'Groups', 'SIP status', 'Actions']) {
    const th = el('th', title);
    th.scope = 'col';
    th.setAttribute('role', 'columnheader');
    tr.append(th);
  }
  head.append(tr);
  const body = el('tbody');
  body.setAttribute('role', 'rowgroup');
  body.id = 'account-rows';
  table.append(head, body);
  scroll.append(table);
  p.append(scroll);
  const help = el('div', null, 'panel-note');
  help.append(
    icon('accounts'),
    el('span', 'Add accounts to a shared group to enable calls.'),
    link('Manage groups →', '/groups'),
  );
  p.append(help);
  setView(p);
  accountRows();
}
// @llr LLR-SRV-UI-015
export function openAccount(id = '') {
  accountVersion = state.model.configuration_version;
  accountGeneration++;
  state.editingId = id;
  const u = state.model.users[id];
  $('account-form').reset();
  state.accountPhoto = u?.photo || '';
  $('account-picture-preview').replaceChildren(avatar(u || { name: '?', type: 'app' }));
  $('edit-remove-photo').disabled = !state.accountPhoto;
  message('account-error', '');
  $('account-title').textContent = u ? 'Edit account' : 'New account';
  $('account-save').textContent = u ? 'Save changes' : 'Create account';
  $('edit-id').value = id;
  $('edit-name').value = u?.name || '';
  $('edit-emails').value = (u?.emails || []).join(', ');
  $('edit-type').value = u?.type || 'app';
  $('edit-password').placeholder = u ? 'Leave blank to keep current' : 'Leave blank to generate';
  $('password-help').textContent = u
    ? 'Leave blank to keep the current password.'
    : 'Leave blank to generate a password.';
  $('rename-help').hidden = true;
  $('account-dialog').showModal();
}
$('edit-id').oninput = () => {
  $('rename-help').hidden = !state.editingId || $('edit-id').value === state.editingId;
};
$('edit-photo').onchange = async () => {
  const file = $('edit-photo').files?.[0];
  if (!file) return;
  const generation = accountGeneration;
  try {
    await validatePicture(file);
  } catch (error) {
    if (generation === accountGeneration && $('edit-photo').files?.[0] === file)
      message('account-error', error instanceof Error ? error.message : String(error));
    return;
  }
  if (generation !== accountGeneration || $('edit-photo').files?.[0] !== file) return;
  message('account-error', '');
  if (state.accountPreviewUrl) URL.revokeObjectURL(state.accountPreviewUrl);
  state.accountPreviewUrl = URL.createObjectURL(file);
  const image = el('img');
  image.src = state.accountPreviewUrl;
  image.alt = 'New account picture preview';
  $('account-picture-preview').replaceChildren(image);
};
$('account-dialog').addEventListener('close', () => {
  accountGeneration++;
  if (state.accountPreviewUrl) URL.revokeObjectURL(state.accountPreviewUrl);
  state.accountPreviewUrl = undefined;
});
$('account-form').onsubmit = (e) => {
  e.preventDefault();
  return submit(
    $('account-form'),
    async () => {
      const id = state.editingId,
        generation = accountGeneration;
      const update = {
        configuration_version: accountVersion,
        id: $('edit-id').value,
        name: $('edit-name').value,
        emails: emailAddresses($('edit-emails').value),
        type: $('edit-type').value,
        password: $('edit-password').value,
        photo: $('edit-remove-photo').checked ? '' : state.accountPhoto,
      };
      try {
        update.photo = await accountPicture(
          $('edit-photo').files?.[0],
          state.accountPhoto,
          $('edit-remove-photo').checked,
        );
        if (generation !== accountGeneration) return;
        const result = await api(
          id ? `/api/users/${id}` : '/api/users',
          id ? 'PUT' : 'POST',
          update,
        );
        if (generation !== accountGeneration) return;
        $('account-dialog').close();
        await state.refresh(true);
        notice(
          id
            ? `Saved ${result.id}.${id !== result.id ? ' Its SIP address has changed.' : ''}`
            : `Created ${result.id}. Add it to a group to enable calls.`,
        );
      } catch (error) {
        if (generation === accountGeneration) throw error;
      }
    },
    'account-error',
  );
};
/** @param {string} id */
export function deleteAccount(id) {
  const configurationVersion = state.model.configuration_version;
  confirm(
    'Delete this account?',
    `“${id}” will be removed from its groups and its terminal settings will be deleted. This cannot be undone.`,
    async () => {
      await api(`/api/users/${id}`, 'DELETE', { configuration_version: configurationVersion });
      notice(`Deleted ${id}.`);
    },
    'Delete account',
  );
}
/** @param {string} value @param {HTMLButtonElement} b @param {HTMLElement} feedback */
// @llr LLR-SRV-UI-019
export async function copyValue(value, b, feedback) {
  const copied = await writeClipboard(value, b);
  feedback.textContent = copied
    ? 'Copied.'
    : 'Your browser blocked copying. Reveal the value if hidden, then select and copy it manually.';
  feedback.hidden = false;
  if (!copied) return;
  b.replaceChildren(icon('check'));
  b.setAttribute('aria-label', 'Copied');
  setTimeout(() => {
    b.replaceChildren(icon('copy'));
    b.setAttribute('aria-label', 'Copy ' + b.dataset.field);
  }, 1600);
}
/** @param {string} name @param {string} value @param {boolean} [secret] */
export function credential(name, value, secret = false) {
  const row = el('div', null, 'credential-row'),
    content = el('div'),
    code = el('code', secret ? '••••••••••••' : value),
    feedback = el('small', '', 'credential-feedback');
  feedback.setAttribute('role', 'status');
  feedback.hidden = true;
  content.append(el('small', name), code, feedback);
  row.append(content);
  if (secret) {
    let revealed = false;
    const reveal = iconButton('Show password', 'eye', () => {
      revealed = !revealed;
      code.textContent = revealed ? value : '••••••••••••';
      reveal.setAttribute('aria-label', revealed ? 'Hide password' : 'Show password');
    });
    row.append(reveal);
  }
  const b = iconButton('Copy ' + name, 'copy', () => copyValue(value, b, feedback));
  b.dataset.field = name;
  row.append(b);
  return row;
}
export function renderConnection() {
  const id = state.detailsId,
    u = state.model.users[id];
  if (!u) {
    $('connection-dialog').close();
    return;
  }
  $('details-title').textContent = u.name;
  const container = $('details-content');
  container.replaceChildren(
    badge(u.type === 'terminal' ? 'Terminal account' : 'App account', 'accent'),
  );
  const list = el('div', null, 'credential-list');
  for (const [name, value, secret] of /** @type {const} */ ([
    ['Username', id],
    ['Password', u.password, true],
    ['Domain', state.model.host],
    ['SIP server', state.model.sip_proxy],
    ['SIP address', `sip:${id}@${state.model.host}`],
  ]))
    list.append(credential(name, value, secret));
  container.append(list);
  if (u.type === 'app')
    container.append(
      el(
        'p',
        'ZmalaPhone supports local calls and secure calls across networks when remote access is configured. Incoming alerts while closed require notifications and the server Firebase sender. Install ZmalaPhone, choose Scan setup QR, and scan this account’s server QR code. This account belongs to an app; it cannot also be assigned to a Pi terminal.',
        'info-box',
      ),
    );
  else {
    container.append(
      el(
        'p',
        id === state.model.local_terminal_id
          ? 'This account is assigned to the terminal bootstrap on the server machine.'
          : 'Assign this account to the terminal on the server machine, or download its setup for another terminal. Use the server QR code to enroll a Pi appliance.',
        'info-box',
      ),
    );
    const actions = el('div', null, 'button-row'),
      assign = actionButton(
        'Use on server machine',
        () => {
          confirm(
            'Assign this terminal?',
            `Use “${id}” for the terminal on the server machine. Restart that terminal after assigning it. This does not change enrollment on another device.`,
            async () => {
              await api('/api/local-terminal', 'PUT', { id });
              notice('Terminal assigned. Restart its window to use this account.');
              renderConnection();
            },
            'Assign terminal',
          );
        },
        'secondary',
        'terminal',
      );
    assign.disabled = id === state.model.local_terminal_id;
    actions.append(
      assign,
      actionButton(
        'Download setup',
        async () => {
          const data = await api('/api/terminal-bootstrap?id=' + encodeURIComponent(id)),
            url = URL.createObjectURL(
              new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
            ),
            a = link('', url);
          a.download = `terminal-${id}.json`;
          a.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          notice(`Downloaded setup for ${id}. See the README for starting another terminal.`);
        },
        'secondary',
        'down',
      ),
    );
    container.append(actions);
  }
  container.append(actionButton('Download server QR PDF', () => serverPdf(id), 'primary', 'down'));
}
/** @param {string} id */
export function openConnection(id) {
  state.detailsId = id;
  renderConnection();
  $('connection-dialog').showModal();
}
