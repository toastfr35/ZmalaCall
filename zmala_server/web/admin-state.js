// Shared admin state and route metadata. Authentication uses an HttpOnly cookie.
/** @template {string} I @param {I} id @returns {import('../types/admin-dom').IdElement<I>} */
export function $(id) {
  const element = document.getElementById(id);
  if (!element) throw Error('Missing administration element: ' + id);
  return /** @type {import('../types/admin-dom').IdElement<I>} */ (element);
}
// Discard legacy shortcut credentials; passwords never belong in URLs/storage.
sessionStorage.removeItem('family-admin');
if (location.hash && location.hash !== '#content') {
  history.replaceState(null, '', location.pathname);
}
/** @type {Record<string, [string, string, string]>} */
export const routes = {
  '/': ['', '', ''],
  '/accounts': ['Accounts', '', ''],
  '/groups': ['Groups', '', 'People in the same group can call one another.'],
  '/terminals': ['Terminals', '', 'Manage devices and settings for each terminal.'],
  '/callbacks': ['Callbacks', '', ''],
  '/activity': [
    'Activity',
    'LIVE MONITORING',
    'Registrations, call events and terminal status in one place.',
  ],
};
export const page = Object.hasOwn(routes, location.pathname) ? location.pathname : '/';
export const shellNames = {
  powershell: 'Windows PowerShell',
  pwsh: 'PowerShell 7',
  cmd: 'Command Prompt',
  sh: 'POSIX shell (Linux)',
  bash: 'Bash (Linux)',
};
/** Shared state and refresh hook avoid cycles between page controllers and the entry point. */
/** @type {import('../types/contracts').AdminModel | null} */
let currentModel = null;
/** @type {import('../types/admin').AdminState} */
export const state = {
  get model() {
    if (!currentModel) throw Error('Administration data has not loaded yet.');
    return currentModel;
  },
  set model(value) {
    currentModel = value;
  },
  busy: false,
  initialized: false,
  editingId: '',
  detailsId: '',
  terminalId: '',
  editingGroupId: '',
  groupVersion: undefined,
  accountPhoto: '',
  accountPreviewUrl: undefined,
  accountSearch: '',
  accountFilter: 'all',
  photoUrls: new Map(),
  renderedVersion: undefined,
  renderedLive: '',
  consoleId: '',
  consoleSignature: '',
  consoleFetching: false,
  terminalCards: new Map(),
  refresh: async () => {},
  renderConnection: () => {},
};
