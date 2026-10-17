// Password-only UI. Session credentials are HttpOnly cookies, never JS storage.
import { state, $ } from './admin-state.js';
import { api, el, icon, setView, message } from './admin-shared.js';

/** @param {string} text @param {boolean} [fresh] */
function passwordField(text, fresh = false) {
  const input = el('input');
  input.type = 'password';
  input.required = true;
  input.autocomplete = fresh ? 'new-password' : 'current-password';
  input.maxLength = 256;
  if (fresh) input.minLength = 12;
  const label = el('label', text);
  label.append(input);
  return { input, label };
}

export async function signIn() {
  if (document.querySelector('.signin-card')) return;
  const status = await api('/api/auth/status');
  state.initialized = false;
  document.querySelectorAll('dialog[open]').forEach((dialog) => {
    if (dialog instanceof HTMLDialogElement) dialog.close();
  });
  $('page-actions').replaceChildren();
  document.getElementById('admin-auth-controls')?.remove();
  message('error', '');
  const form = el('form', null, 'signin-card');
  form.append(icon('server'), el('h2', status.setup_required ? 'Set admin password' : 'Sign in'));
  const password = passwordField('Admin password', status.setup_required);
  form.append(password.label);
  const confirmation = passwordField('Confirm admin password', true);
  if (status.setup_required) {
    form.append(
      el(
        'p',
        'Use at least 12 characters. This password gives access to all administration controls.',
        'muted',
      ),
      confirmation.label,
    );
  }
  const error = el('p', '', 'banner error');
  error.setAttribute('role', 'alert');
  error.hidden = true;
  const button = el('button', status.setup_required ? 'Set password' : 'Sign in', 'primary');
  form.append(error, button);
  form.onsubmit = async (event) => {
    event.preventDefault();
    error.hidden = true;
    button.disabled = true;
    try {
      if (status.setup_required && password.input.value !== confirmation.input.value)
        throw Error('Passwords do not match.');
      await api(status.setup_required ? '/api/auth/setup' : '/api/auth/login', 'POST', {
        password: password.input.value,
      });
      password.input.value = confirmation.input.value = '';
      location.reload();
    } catch (failure) {
      error.textContent = failure instanceof Error ? failure.message : 'Sign-in failed.';
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  };
  setView(form);
}

export function authControls() {
  if (document.getElementById('admin-auth-controls')) return;
  const controls = el('div', null, 'admin-auth-controls');
  controls.id = 'admin-auth-controls';
  const change = el('button', 'Change password', 'secondary');
  const logout = el('button', 'Sign out', 'secondary');
  logout.onclick = async () => {
    try {
      await api('/api/auth/logout', 'POST');
      location.reload();
    } catch (failure) {
      message('error', failure instanceof Error ? failure.message : 'Sign-out failed.');
    }
  };
  change.onclick = () => {
    const dialog = el('dialog', null, 'modal');
    dialog.setAttribute('aria-label', 'Change admin password');
    const form = el('form');
    const current = passwordField('Current admin password');
    const password = passwordField('New admin password', true);
    const confirmation = passwordField('Confirm new password', true);
    const error = el('p', '', 'banner error');
    error.hidden = true;
    error.setAttribute('role', 'alert');
    const save = el('button', 'Change password', 'primary');
    const cancel = el('button', 'Cancel', 'secondary');
    cancel.type = 'button';
    cancel.onclick = () => dialog.close();
    const footer = el('div', null, 'modal-footer');
    footer.append(cancel, save);
    form.append(
      el('h2', 'Change admin password'),
      current.label,
      password.label,
      confirmation.label,
      error,
      footer,
    );
    form.onsubmit = async (event) => {
      event.preventDefault();
      save.disabled = true;
      try {
        if (password.input.value !== confirmation.input.value)
          throw Error('Passwords do not match.');
        await api('/api/auth/password', 'POST', {
          current_password: current.input.value,
          password: password.input.value,
        });
        dialog.close();
        message('notice', 'Admin password changed. Other sessions have been signed out.');
      } catch (failure) {
        error.textContent = failure instanceof Error ? failure.message : 'Password change failed.';
        error.hidden = false;
      } finally {
        save.disabled = false;
      }
    };
    dialog.onclose = () => dialog.remove();
    dialog.append(form);
    document.body.append(dialog);
    dialog.showModal();
  };
  controls.append(change, logout);
  document.querySelector('.sidebar')?.append(controls);
}
