// Account list, editing and connection details. Device configuration belongs on the Terminals page.
import { accountPicture, emailAddresses } from './admin-shared.js';
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
        u.type === 'terminal' ? 'Terminal' : 'Linphone',
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
    ['linphone', 'Linphone'],
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
  for (const title of ['Account', 'Type', 'Groups', 'SIP status', 'Actions']) {
    const th = el('th', title);
    th.scope = 'col';
    tr.append(th);
  }
  head.append(tr);
  const body = el('tbody');
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
export function openAccount(id = '') {
  state.editingId = id;
  const u = state.model.users[id];
  $('account-form').reset();
  state.accountPhoto = u?.photo || '';
  $('account-picture-preview').replaceChildren(avatar(u || { name: '?', type: 'linphone' }));
  $('edit-remove-photo').disabled = !state.accountPhoto;
  message('account-error', '');
  $('account-title').textContent = u ? 'Edit account' : 'New account';
  $('account-save').textContent = u ? 'Save changes' : 'Create account';
  $('edit-id').value = id;
  $('edit-name').value = u?.name || '';
  $('edit-emails').value = (u?.emails || []).join(', ');
  $('edit-type').value = u?.type || 'linphone';
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
$('edit-photo').onchange = () => {
  const file = $('edit-photo').files?.[0];
  if (!file) return;
  if (state.accountPreviewUrl) URL.revokeObjectURL(state.accountPreviewUrl);
  state.accountPreviewUrl = URL.createObjectURL(file);
  const image = el('img');
  image.src = state.accountPreviewUrl;
  image.alt = 'New account picture preview';
  $('account-picture-preview').replaceChildren(image);
};
$('account-dialog').addEventListener('close', () => {
  if (state.accountPreviewUrl) URL.revokeObjectURL(state.accountPreviewUrl);
  state.accountPreviewUrl = undefined;
});
$('account-form').onsubmit = (e) => {
  e.preventDefault();
  submit(
    $('account-form'),
    async () => {
      const update = {
        id: $('edit-id').value,
        name: $('edit-name').value,
        emails: emailAddresses($('edit-emails').value),
        type: $('edit-type').value,
        password: $('edit-password').value,
        photo: $('edit-remove-photo').checked ? '' : state.accountPhoto,
      };
      update.photo = await accountPicture(
        $('edit-photo').files?.[0],
        state.accountPhoto,
        $('edit-remove-photo').checked,
      );
      const result = await api(
        state.editingId ? `/api/users/${state.editingId}` : '/api/users',
        state.editingId ? 'PUT' : 'POST',
        update,
      );
      $('account-dialog').close();
      await state.refresh(true);
      notice(
        state.editingId
          ? `Saved ${result.id}.${state.editingId !== result.id ? ' Its SIP address has changed.' : ''}`
          : `Created ${result.id}. Add it to a group to enable calls.`,
      );
    },
    'account-error',
  );
};
/** @param {string} id */
export function deleteAccount(id) {
  confirm(
    'Delete this account?',
    `“${id}” will be removed from its groups and its terminal settings will be deleted. This cannot be undone.`,
    async () => {
      await api(`/api/users/${id}`, 'DELETE');
      notice(`Deleted ${id}.`);
    },
    'Delete account',
  );
}
/** @param {string} value @param {HTMLButtonElement} b */
export async function copyValue(value, b) {
  await navigator.clipboard.writeText(value);
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
    code = el('code', secret ? '••••••••••••' : value);
  content.append(el('small', name), code);
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
  const b = iconButton('Copy ' + name, 'copy', () => copyValue(value, b));
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
    badge(u.type === 'terminal' ? 'Terminal account' : 'Linphone account', 'accent'),
  );
  const list = el('div', null, 'credential-list');
  for (const [name, value, secret] of /** @type {const} */ ([
    ['Username', id],
    ['Password', u.password, true],
    ['Domain', `${state.model.host}:${state.model.sip_port}`],
    ['SIP server', `sip:${state.model.host}:${state.model.sip_port};transport=udp`],
    ['SIP address', `sip:${id}@${state.model.host}`],
  ]))
    list.append(credential(name, value, secret));
  container.append(list);
  if (u.type === 'linphone')
    container.append(
      el(
        'p',
        'In Linphone, add a third-party SIP account. Use UDP, enable video, set media encryption to None, and disable ICE/STUN. Keep the phone on the same Wi-Fi as this PC.',
        'info-box',
      ),
    );
  else {
    container.append(
      el(
        'p',
        id === state.model.local_terminal_id
          ? 'This account is assigned to the Windows terminal on this PC.'
          : 'Assign this account to the terminal on this PC, or download its setup for another Windows instance on this PC.',
        'info-box',
      ),
    );
    const actions = el('div', null, 'button-row'),
      assign = actionButton(
        'Use on this PC',
        () => {
          confirm(
            'Assign this terminal?',
            `Use “${id}” for the Windows terminal on this PC. Close and reopen the terminal window after assigning it.`,
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
  if (u.type === 'terminal')
    container.append(
      actionButton('Download server QR PDF', () => serverPdf(id), 'primary', 'down'),
    );
}
/** @param {string} id */
export function openConnection(id) {
  state.detailsId = id;
  renderConnection();
  $('connection-dialog').showModal();
}
