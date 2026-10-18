// Callback queue and deadline/SMTP dialogs; the server remains authoritative for scheduling.
import { $, state } from './admin-state.js';
import {
  el,
  panel,
  avatar,
  badge,
  setView,
  actionButton,
  registered,
  api,
  submit,
  notice,
  iconButton,
} from './admin-shared.js';

/** @param {string} title @param {string} errorId */
function callbackDialog(title, errorId) {
  const dialog = el('dialog', null, 'modal'),
    form = el('form'),
    heading = el('div', null, 'modal-heading');
  dialog.setAttribute('aria-label', title);
  heading.append(
    el('h2', title),
    iconButton('Close ' + title, 'close', () => dialog.close()),
  );
  const error = el('p', null, 'banner error');
  error.id = errorId;
  error.hidden = true;
  error.setAttribute('role', 'alert');
  form.append(heading, error);
  dialog.append(form);
  document.body.append(dialog);
  dialog.addEventListener('close', () => dialog.remove());
  return { dialog, form };
}
/** @param {HTMLFormElement} form @param {string} label @param {string} key @param {string | number | undefined} value @param {object} [options] */
function callbackField(form, label, key, value, options = {}) {
  const wrapper = el('label', label),
    input = el('input');
  input.name = key;
  input.value = String(value ?? '');
  Object.assign(input, options);
  wrapper.append(input);
  form.append(wrapper);
  return input;
}
/** @param {HTMLFormElement} form @param {HTMLDialogElement} dialog @param {string} text */
function callbackFooter(form, dialog, text) {
  const footer = el('div', null, 'modal-footer'),
    save = el('button', text, 'primary');
  save.type = 'submit';
  footer.append(
    actionButton('Cancel', () => dialog.close()),
    save,
  );
  form.append(footer);
}
// @llr LLR-SRV-CALLBACK-017, LLR-SRV-UI-016
export function openCallbackDeadlines() {
  const { dialog, form } = callbackDialog('Callback deadlines', 'deadline-error');
  const settings = state.model.callback_settings,
    version = state.model.configuration_version;
  form.append(
    el(
      'p',
      'Both deadlines are measured from the request time. Changes apply to pending requests.',
      'info-box',
    ),
  );
  const emailDelay = callbackField(
    form,
    'Email reminder after (hours)',
    'emailDelay',
    settings.email_after_hours,
    { type: 'number', min: 0.01, max: 719.99, step: 'any', required: true },
  );
  const removalDelay = callbackField(
    form,
    'Remove request after (hours)',
    'removalDelay',
    settings.remove_after_hours,
    { type: 'number', min: 0.01, max: 720, step: 'any', required: true },
  );
  form.append(
    el(
      'p',
      'Removal must be later than the email reminder. Fractional hours are supported (0.5 = 30 minutes). Completed and cancelled requests remain in history.',
      'muted',
    ),
  );
  callbackFooter(form, dialog, 'Save deadlines');
  form.onsubmit = (event) => {
    event.preventDefault();
    submit(
      form,
      async () => {
        await api('/api/callback-settings', 'PUT', {
          email_after_hours: Number(emailDelay.value),
          remove_after_hours: Number(removalDelay.value),
          configuration_version: version,
        });
        dialog.close();
        await state.refresh(true);
        notice('Saved callback deadlines.');
      },
      'deadline-error',
    );
  };
  dialog.showModal();
}
// @llr LLR-SRV-CALLBACK-023, LLR-SRV-CALLBACK-024, LLR-SRV-UI-016
export function openCallbackSmtp() {
  const { dialog, form } = callbackDialog('Email server', 'smtp-error');
  const settings = state.model.smtp,
    version = state.model.configuration_version;
  form.append(
    el(
      'p',
      'Use your email provider’s SMTP settings. Save first, then use Check connection. This checks authentication without sending an email.',
      'info-box',
    ),
  );
  const enabled = callbackField(form, 'Enable email reminders', 'enabled', '', {
    type: 'checkbox',
    checked: settings.enabled,
  });
  enabled.parentElement?.classList.add('checkbox-row');
  enabled.parentElement?.prepend(enabled);
  const host = callbackField(form, 'SMTP host', 'host', settings.host, { maxLength: 253 });
  const port = callbackField(form, 'SMTP port', 'port', settings.port, {
    type: 'number',
    min: 1,
    max: 65535,
    required: true,
  });
  const securityLabel = el('label', 'Connection security'),
    security = el('select');
  for (const [value, label] of [
    ['starttls', 'STARTTLS (usually port 587)'],
    ['tls', 'TLS (usually port 465)'],
    ['none', 'Unencrypted (local mail relay only)'],
  ]) {
    const option = el('option', label);
    option.value = value;
    security.append(option);
  }
  security.value = settings.security;
  securityLabel.append(security);
  form.append(securityLabel);
  const username = callbackField(form, 'SMTP username', 'username', settings.username, {
    maxLength: 254,
    autocomplete: 'off',
  });
  const password = callbackField(form, 'SMTP password', 'password', '', {
    type: 'password',
    maxLength: 1024,
    autocomplete: 'new-password',
    placeholder: settings.password_set
      ? 'Leave blank to keep current'
      : 'Provider password or app password',
  });
  const clear = callbackField(form, 'Clear saved password', 'clearPassword', '', {
    type: 'checkbox',
  });
  clear.parentElement?.classList.add('checkbox-row');
  clear.parentElement?.prepend(clear);
  const sender = callbackField(form, 'Sender email address', 'from', settings.from, {
    type: 'email',
    maxLength: 254,
  });
  callbackFooter(form, dialog, 'Save email server');
  form.onsubmit = (event) => {
    event.preventDefault();
    submit(
      form,
      async () => {
        await api('/api/smtp-settings', 'PUT', {
          enabled: enabled.checked,
          host: host.value,
          port: Number(port.value),
          security: security.value,
          username: username.value,
          password: password.value,
          clear_password: clear.checked,
          from: sender.value,
          configuration_version: version,
        });
        dialog.close();
        await state.refresh(true);
        notice('Saved email server settings.');
      },
      'smtp-error',
    );
  };
  dialog.showModal();
}
/** @param {import('../types/contracts').CallbackView} request */
// @llr LLR-SRV-CALLBACK-021
function callbackEmailStatus(request) {
  if (request.status !== 'pending') return '';
  const addresses = state.model.users[request.to]?.emails || [],
    sent = request.email_sent_to || [];
  if (!addresses.length) return 'Email reminder needs an email address on the contact’s account.';
  if (request.email_error) return `${request.email_error} The server will retry until removal.`;
  if (sent.length) {
    const remaining = addresses.filter(
      (address) => !sent.some((item) => item.toLowerCase() === address.toLowerCase()),
    ).length;
    return `Email accepted by SMTP for ${sent.length} address${sent.length === 1 ? '' : 'es'}.${remaining ? ` Waiting for ${remaining} more.` : ''}`;
  }
  if (!state.model.smtp.enabled)
    return 'Email reminders are disabled. Configure the email server to send them.';
  return `Email reminder ${new Date(request.email_due_at).toLocaleString()}.`;
}
// @llr LLR-SRV-CALLBACK-016
export function renderCallbacks() {
  $('page-actions').replaceChildren();
  const settings = state.model.callback_settings,
    policy = panel('Callback deadlines'),
    policyBody = el('div', null, 'callback-policy-body');
  policyBody.append(
    el(
      'p',
      `Email reminder after ${callbackHours(settings.email_after_hours)} · Remove request after ${callbackHours(settings.remove_after_hours)}`,
    ),
  );
  const tools = el('div', null, 'button-row');
  tools.append(
    actionButton('Edit deadlines', openCallbackDeadlines, 'primary', 'edit'),
    actionButton('Email server', openCallbackSmtp, 'secondary', 'settings'),
    actionButton(
      'Check connection',
      async () => {
        await api('/api/smtp-settings/verify', 'POST', {});
        notice('SMTP connection and authentication succeeded.');
      },
      'secondary',
      'check',
    ),
  );
  policyBody.append(
    tools,
    el(
      'p',
      state.model.smtp.enabled ? 'Email reminders enabled.' : 'Email reminders disabled.',
      'muted',
    ),
  );
  policy.append(policyBody);
  const p = panel(
      'Callback requests',
      'Linphone notifications are sent when the contact reconnects. Calls always start manually.',
    ),
    list = el('div', null, 'registration-list');
  for (const request of state.model.callbacks || []) {
    const row = el('div', null, 'list-row'),
      description = el('div'),
      source = state.model.users[request.from] || { name: request.from_name, type: 'terminal' };
    description.append(
      el('strong', `${request.from_name} → ${request.to_name}`),
      el(
        'small',
        `Requested ${new Date(request.created_at).toLocaleString()} · Remove ${new Date(request.expires_at).toLocaleString()}`,
      ),
    );
    if (request.status === 'pending')
      description.append(
        el(
          'small',
          state.model.users[request.to]?.type === 'terminal'
            ? 'Shown on the receiving terminal when both people are available.'
            : request.notified_at
              ? 'Linphone accepted the chat message.'
              : registered(request.to)
                ? 'Waiting for Linphone to accept the chat message.'
                : 'Waiting for the phone to reconnect.',
        ),
        el('small', callbackEmailStatus(request)),
      );
    row.append(
      avatar(source),
      description,
      badge(
        request.status === 'pending' && request.ready ? 'Both online' : request.status,
        request.status === 'completed' || (request.status === 'pending' && request.ready)
          ? 'success'
          : 'neutral',
      ),
    );
    if (request.status === 'pending')
      row.append(
        actionButton('Cancel', async () => {
          await api(`/api/callbacks/${request.id}`, 'DELETE');
          await state.refresh(true);
        }),
      );
    list.append(row);
  }
  if (!list.children.length)
    list.append(
      el(
        'p',
        'No callback requests yet. On a terminal, choose an offline person and press green twice to request a callback.',
        'muted',
      ),
    );
  p.append(list);
  setView(policy, p);
}
/** @param {number} hours */
function callbackHours(hours) {
  return (
    new Intl.NumberFormat('en', { maximumFractionDigits: 4 }).format(hours) +
    (hours === 1 ? ' hour' : ' hours')
  );
}
