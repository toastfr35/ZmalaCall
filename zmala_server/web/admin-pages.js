import { backupPanel } from './admin-backups.js';
import { query } from './admin-shared.js';
// Overview and activity views combine persisted account configuration with live SIP/device status.
import { $, state } from './admin-state.js';
import {
  el,
  online,
  link,
  icon,
  panel,
  avatar,
  badge,
  setView,
  actionButton,
  api,
  message,
} from './admin-shared.js';
export function renderOverview() {
  $('page-actions').replaceChildren();
  const hero = el('section', null, 'welcome-panel'),
    intro = el('div');
  intro.append(el('h2', 'Keep your family connected.'));
  const productLogo = el('img', null, 'welcome-logo');
  productLogo.src = '/zmala-icon.svg';
  productLogo.alt = '';
  hero.append(intro, productLogo);
  const stats = el('div', null, 'stats-grid'),
    metrics = /** @type {[string, number, string, string][]} */ ([
      ['Accounts', Object.keys(state.model.users).length, 'accounts', '/accounts'],
      ['Registered', state.model.sip_status.registrations.length, 'link', '/activity'],
      [
        'Terminals online',
        Object.keys(state.model.profiles).filter(online).length,
        'terminal',
        '/terminals',
      ],
      ['Active calls', state.model.sip_status.active_calls, 'phone', '/activity'],
    ]);
  for (const [name, value, glyph, url] of metrics) {
    const c = link('', url, 'stat-card'),
      top = el('div', null, 'stat-heading');
    top.append(el('span', name), icon(glyph));
    c.append(top, el('strong', String(value)), el('small', 'View details →'));
    stats.append(c);
  }
  const columns = el('div', null, 'overview-grid'),
    server = panel('Shared SIP server', 'The same domain and server for every account.'),
    details = el('dl', null, 'server-details');
  for (const [name, value] of [
    ['Domain', `${state.model.host}:${state.model.sip_port}`],
    ['Proxy', `sip:${state.model.host}:${state.model.sip_port};transport=udp`],
  ]) {
    const row = el('div');
    row.append(el('dt', name), el('dd', value));
    details.append(row);
  }
  server.append(details);
  const sshBox = el('div', null, 'server-ssh');
  server.append(sshBox);
  async function refreshServerSsh() {
    try {
      const ssh = await api('/api/server/ssh');
      if (!ssh.supported || !sshBox.isConnected) return;
      const button = actionButton(
        ssh.enabled ? 'Turn SSH off' : 'Turn SSH on',
        async () => {
          button.disabled = true;
          try {
            await api('/api/server/ssh', 'PUT', { enabled: !ssh.enabled });
            await refreshServerSsh();
          } catch (error) {
            message('error', error instanceof Error ? error.message : 'Could not change SSH.');
            button.disabled = false;
          }
        },
        'secondary',
      );
      sshBox.replaceChildren(
        el('h3', 'Wired SSH'),
        el('p', ssh.active ? 'On · Ethernet only' : 'Off', 'muted'),
        el(
          'p',
          'Remote maintenance access. Web administration and calls remain available.',
          'muted',
        ),
        button,
      );
    } catch (error) {
      if (sshBox.isConnected) sshBox.replaceChildren(el('p', 'SSH status unavailable', 'muted'));
    }
  }
  void refreshServerSsh();
  const terminals = panel('Your terminals', 'Live state from connected devices.');
  query(terminals, '.panel-heading').append(link('Manage →', '/terminals'));
  const list = el('div', null, 'terminal-status-list');
  for (const [id, u] of Object.entries(state.model.users))
    if (u.type === 'terminal') {
      const row = el('div', null, 'list-row'),
        text = el('div');
      text.append(el('strong', u.name), el('small', id));
      row.append(
        avatar(u),
        text,
        badge(
          online(id) ? state.model.terminal_statuses[id].state : 'Offline',
          online(id) ? 'success' : 'neutral',
        ),
      );
      list.append(row);
    }
  if (!list.children.length)
    list.append(el('p', 'No terminals yet. Create a Terminal account to get started.', 'muted'));
  terminals.append(list);
  columns.append(server, terminals);
  setView(hero, stats, columns, backupPanel());
}
/** @param {number} limit */
export function eventList(limit) {
  const list = el('div', null, 'event-list'),
    events = state.model.sip_status.events.slice().reverse().slice(0, limit);
  for (const event of events) {
    const row = el('div', null, 'event-row');
    row.append(
      el('span', null, 'event-dot'),
      el('span', event.message),
      el('time', new Date(event.time).toLocaleTimeString()),
    );
    query(row, 'time').dateTime = event.time;
    list.append(row);
  }
  if (!events.length)
    list.append(el('p', 'No events yet. Registration and call events appear here.', 'muted'));
  return list;
}
export function renderActivity() {
  $('page-actions').replaceChildren(
    actionButton('Refresh', () => state.refresh(true), 'secondary', 'activity'),
  );
  const registrations = panel(
      'Registered accounts',
      `${state.model.sip_status.registrations.length} connected · ${state.model.sip_status.active_calls} active calls`,
    ),
    list = el('div', null, 'registration-list');
  for (const r of state.model.sip_status.registrations) {
    const u = state.model.users[r.user];
    if (!u) continue;
    const row = el('div', null, 'list-row'),
      names = el('div');
    names.append(el('strong', u.name), el('small', `${r.user} · ${r.address}`));
    row.append(avatar(u), names, badge('Registered', 'success'));
    list.append(row);
  }
  if (!list.children.length)
    list.append(
      el(
        'p',
        'No accounts registered. Open connection details on the Accounts page to set up a client.',
        'muted',
      ),
    );
  registrations.append(list);
  const events = panel('Server timeline', 'Latest events first. Updates automatically.');
  events.append(eventList(100));
  setView(registrations, events);
}
