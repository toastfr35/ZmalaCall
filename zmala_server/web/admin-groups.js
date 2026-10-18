import { query } from './admin-shared.js';
// Group membership editing defines call permissions; persist changes through the shared API helper.
import { $, state } from './admin-state.js';
import {
  actionButton,
  el,
  icon,
  panel,
  iconButton,
  avatar,
  badge,
  empty,
  setView,
  message,
  submit,
  api,
  notice,
  confirm,
} from './admin-shared.js';
export function renderGroups() {
  $('page-actions').replaceChildren(
    actionButton('New group', () => openGroup(), 'primary', 'plus'),
  );
  const intro = el('div', null, 'group-intro');
  intro.append(
    icon('accounts'),
    el(
      'div',
      'Sharing any group enables calls in both directions. Membership in one group does not grant access to members of another group.',
    ),
  );
  const grid = el('div', null, 'groups-grid');
  for (const [id, g] of Object.entries(state.model.groups)) {
    const card = panel(g.name, g.description || 'A shared calling group.'),
      actions = el('div', null, 'row-actions');
    actions.append(
      iconButton(`Edit group ${g.name}`, 'edit', () => openGroup(id)),
      iconButton(`Delete group ${g.name}`, 'trash', () => deleteGroup(id)),
    );
    query(card, '.panel-heading').append(actions);
    const members = el('div', null, 'group-card-members');
    for (const user of g.members) {
      const u = state.model.users[user],
        row = el('div', null, 'list-row'),
        names = el('div');
      names.append(el('strong', u.name), el('small', user));
      row.append(
        avatar(u),
        names,
        badge(
          u.type === 'terminal' ? 'Terminal' : 'Linphone',
          u.type === 'terminal' ? 'accent' : 'neutral',
        ),
      );
      members.append(row);
    }
    if (!g.members.length)
      members.append(el('p', 'No members yet. Edit this group to add accounts.', 'muted'));
    card.append(members);
    const note = el('div', null, 'panel-note');
    note.append(
      el('span', `${g.members.length} ${g.members.length === 1 ? 'member' : 'members'}`),
      el(
        'span',
        g.members.length > 1
          ? 'Members can call each other'
          : 'Add at least two members to enable calls',
      ),
    );
    card.append(note);
    grid.append(card);
  }
  if (!grid.children.length)
    grid.append(
      empty(
        'Create your first group',
        'Add people and terminals to a group so they can call each other.',
        actionButton('New group', () => openGroup(), 'primary', 'plus'),
      ),
    );
  setView(intro, grid);
}
// @llr LLR-SRV-UI-005
export function openGroup(id = '') {
  state.editingGroupId = id;
  state.groupVersion = state.model.configuration_version;
  const g = state.model.groups[id];
  $('group-form').reset();
  $('group-title').textContent = g ? 'Edit group' : 'New group';
  $('group-save').textContent = g ? 'Save group' : 'Create group';
  $('group-name').value = g?.name || '';
  $('group-description').value = g?.description || '';
  message('group-error', '');
  $('group-members').replaceChildren();
  for (const [user, u] of Object.entries(state.model.users)) {
    const row = el('label', null, 'group-member-option'),
      box = el('input');
    box.type = 'checkbox';
    box.value = user;
    box.checked = g?.members.includes(user) || false;
    box.setAttribute('aria-label', `Include ${user} in group`);
    box.onchange = selectedGroupCount;
    const names = el('span');
    names.append(
      el('strong', u.name),
      el('small', `${user} · ${u.type === 'terminal' ? 'Terminal' : 'Linphone'}`),
    );
    row.append(box, avatar(u), names);
    $('group-members').append(row);
  }
  if (!Object.keys(state.model.users).length)
    $('group-members').append(el('p', 'Create accounts first to add group members.', 'muted'));
  selectedGroupCount();
  $('group-dialog').showModal();
}
export function selectedGroupCount() {
  $('group-selected-count').textContent =
    `${$('group-members').querySelectorAll(/** @type {const} */ ('input:checked')).length} selected`;
}
$('group-form').onsubmit = (e) => {
  e.preventDefault();
  submit(
    $('group-form'),
    async () => {
      const update = {
        name: $('group-name').value,
        description: $('group-description').value,
        members: [
          .../** @type {NodeListOf<HTMLInputElement>} */ (
            $('group-members').querySelectorAll('input:checked')
          ),
        ].map((b) => b.value),
        configuration_version: state.groupVersion,
      };
      await api(
        state.editingGroupId ? `/api/groups/${state.editingGroupId}` : '/api/groups',
        state.editingGroupId ? 'PUT' : 'POST',
        update,
      );
      $('group-dialog').close();
      await state.refresh(true);
      notice('Group saved. Shared members can now call each other.');
    },
    'group-error',
  );
};
/** @param {string} id */
export function deleteGroup(id) {
  const g = state.model.groups[id],
    version = state.model.configuration_version;
  confirm(
    'Delete this group?',
    `Delete “${g.name}”? Accounts remain. Members can still call each other if they share another group.`,
    async () => {
      await api(`/api/groups/${id}`, 'DELETE', { configuration_version: version });
      notice(`Deleted group ${g.name}.`);
    },
    'Delete group',
  );
}
