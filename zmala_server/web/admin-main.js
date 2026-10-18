// Admin entry point: route rendering and polling share state without overwriting active edits.
import { renderOverview, renderActivity } from './admin-pages.js';
import { renderCallbacks } from './admin-callbacks.js';
import { renderAccounts, accountRows, renderConnection } from './admin-accounts.js';
import { renderGroups } from './admin-groups.js';
import { renderTerminals, terminalCardState } from './admin-terminals.js';
import { page, state } from './admin-state.js';
import { liveSignature, api, message } from './admin-shared.js';
import { signIn, authControls } from './admin-auth.js';
// @llr LLR-SRV-UI-012
export function render() {
  const renderers = /** @type {Record<string, () => void>} */ ({
    '/': renderOverview,
    '/accounts': renderAccounts,
    '/groups': renderGroups,
    '/terminals': renderTerminals,
    '/callbacks': renderCallbacks,
    '/activity': renderActivity,
  });
  renderers[page]();
  state.renderedVersion = state.model.configuration_version;
  state.renderedLive = liveSignature();
}
/** @type {Promise<void> | null} */
let inFlight = null;
/** @param {boolean} [force] @returns {Promise<void>} */
export function refresh(force = false) {
  // Slow requests must not overlap interval polls or overwrite a newer edit.
  if (inFlight) return force ? inFlight.then(() => refresh(true)) : inFlight;
  inFlight = performRefresh(force).finally(() => {
    inFlight = null;
  });
  return inFlight;
}
// @llr LLR-SRV-UI-016
/** @param {boolean} force */
async function performRefresh(force) {
  if (state.restoring) return;
  try {
    if (force || !state.initialized) state.model = await api('/api/admin');
    else {
      const live = await api('/api/admin/live');
      state.model =
        live.configuration_version === state.model.configuration_version
          ? { ...state.model, ...live }
          : await api('/api/admin');
    }
    authControls();
    const changed = state.renderedVersion !== state.model.configuration_version,
      liveChanged = state.renderedLive !== liveSignature();
    // Account polls replace rows only; typing in the search field can continue.
    // Other pages replace the view, so retain any focused control until it blurs.
    const refreshRegion = document.getElementById(page === '/accounts' ? 'account-rows' : 'view');
    if (page === '/terminals')
      for (const [id, card] of state.terminalCards)
        if (state.model.profiles[id]) terminalCardState(card, id);
    if (force || !state.initialized) {
      render();
      state.initialized = true;
      message('error', '');
      // Polls update live badges, but a full redraw must not discard a dialog or focused form.
    } else if (
      !document.querySelector('dialog[open]') &&
      !state.busy &&
      !refreshRegion?.contains(document.activeElement) &&
      (changed || (liveChanged && page !== '/groups'))
    ) {
      if (page === '/accounts') {
        accountRows();
        state.renderedVersion = state.model.configuration_version;
        state.renderedLive = liveSignature();
      } else render();
    }
  } catch (e) {
    if (state.restoring) return;
    if (e instanceof Error && 'status' in e && e.status === 401) await signIn();
    else message('error', e instanceof Error ? e.message : 'Request failed.');
  }
}
state.refresh = refresh;
state.renderConnection = renderConnection;
refresh(true);
setInterval(() => state.refresh(), 4000);
