// Remote command submission and result polling; command execution stays in the terminal agent.
import { state, $, shellNames } from './admin-state.js';
import { api, online, el, badge, iconButton, message, submit, notice } from './admin-shared.js';
let consoleGeneration = 0;
let consoleVersion = 0;
$('console-dialog').addEventListener('close', () => {
  consoleGeneration++;
  state.consoleId = '';
});
export async function refreshConsole() {
  if (!state.consoleId || !$('console-dialog').open || state.consoleFetching) return;
  const id = state.consoleId,
    generation = consoleGeneration;
  state.consoleFetching = true;
  try {
    const data = await api(`/api/terminals/${id}/console`);
    if (generation !== consoleGeneration || !$('console-dialog').open) return;
    $('console-state').textContent =
      `${online(state.consoleId) ? 'Terminal online' : 'Terminal offline'} · ${shellNames[state.model.profiles[state.consoleId]?.command_shell || 'powershell']} · queued commands wait for this terminal`;
    const signature = JSON.stringify(data.jobs);
    if (signature !== state.consoleSignature) {
      state.consoleSignature = signature;
      const history = $('console-history'),
        nearBottom = history.scrollTop + history.clientHeight >= history.scrollHeight - 60;
      history.replaceChildren();
      if (!data.jobs.length)
        history.append(
          el('p', 'No commands yet. Run a command to inspect or maintain this terminal.', 'muted'),
        );
      for (const job of data.jobs) {
        const entry = el('section', null, 'console-entry'),
          heading = el('div', null, 'console-entry-heading');
        heading.append(
          el('time', new Date(job.created_at).toLocaleString()),
          badge(
            job.status,
            job.status === 'completed'
              ? 'success'
              : job.status === 'failed' || job.status === 'timed_out'
                ? 'danger'
                : 'neutral',
          ),
        );
        if (job.exit_code !== null) heading.append(el('span', `Exit ${job.exit_code}`, 'muted'));
        if (job.status === 'queued')
          heading.append(
            iconButton('Remove queued command', 'trash', async () => {
              await api(`/api/terminals/${id}/console/${job.id}`, 'DELETE');
              state.consoleSignature = '';
              await refreshConsole();
            }),
          );
        heading.append(badge(shellNames[job.shell || 'powershell'], 'neutral'));
        entry.append(
          heading,
          el(
            'pre',
            (job.shell === 'cmd' ? 'CMD> ' : ['sh', 'bash'].includes(job.shell) ? '$ ' : 'PS> ') +
              job.command,
            'console-input',
          ),
        );
        if (job.stdout) entry.append(el('pre', job.stdout, 'console-output'));
        if (job.stderr) entry.append(el('pre', job.stderr, 'console-stderr'));
        if (job.truncated) entry.append(el('p', 'Output truncated at 64 KiB.', 'muted'));
        history.append(entry);
      }
      if (nearBottom) history.scrollTop = history.scrollHeight;
    }
  } catch (e) {
    if (generation === consoleGeneration && $('console-dialog').open)
      message('console-error', e instanceof Error ? e.message : 'Request failed.');
  } finally {
    state.consoleFetching = false;
    // Switching consoles while a request was pending must load the new one promptly.
    if (generation !== consoleGeneration && $('console-dialog').open) void refreshConsole();
  }
}
/** @param {string} id */
export function openConsole(id) {
  consoleGeneration++;
  consoleVersion = state.model.configuration_version;
  state.consoleId = id;
  state.consoleSignature = '';
  $('console-state').textContent = 'Loading terminal status…';
  $('console-history').replaceChildren(el('p', 'Loading commands…', 'muted'));
  $('console-title').textContent = `${state.model.users[id].name} · ${id}`;
  $('console-command').value = '';
  const shell = $('console-shell');
  shell.replaceChildren();
  for (const [value, name] of Object.entries(shellNames)) {
    const option = el('option', name);
    option.value = value;
    shell.append(option);
  }
  shell.value = state.model.profiles[id].command_shell || 'powershell';
  message('console-shell-error', '');
  message('console-error', '');
  $('console-dialog').showModal();
  refreshConsole();
}
// Shell preferences belong to maintenance, while media preferences stay on Terminals.
$('console-shell-form').onsubmit = (event) => {
  event.preventDefault();
  return submit(
    $('console-shell-form'),
    async () => {
      const id = state.consoleId,
        generation = consoleGeneration;
      const profile = state.model.profiles[id];
      const saved = await api('/api/settings', 'PUT', {
        terminal_id: id,
        configuration_version: consoleVersion,
        display_name: profile.display_name,
        language: profile.language,
        audio_profile: profile.audio_profile,
        video_resolution: profile.video_resolution,
        video_fps: profile.video_fps,
        ...profile.terminal_settings,
        command_shell: $('console-shell').value,
      });
      // A later opening owns its own draft and revision. Use the server's saved
      // revision, never a newer polling snapshot that this editor did not display.
      if (generation !== consoleGeneration) return;
      if (typeof saved.configuration_version === 'number')
        consoleVersion = saved.configuration_version;
      await state.refresh(true);
      await refreshConsole();
      notice('Command shell saved.');
    },
    'console-shell-error',
  );
};
$('console-form').onsubmit = (e) => {
  e.preventDefault();
  submit(
    $('console-form'),
    async () => {
      await api(`/api/terminals/${state.consoleId}/console`, 'POST', {
        command: $('console-command').value,
        timeout_seconds: Number($('console-timeout').value),
      });
      $('console-command').value = '';
      state.consoleSignature = '';
      await refreshConsole();
    },
    'console-error',
  );
};
setInterval(refreshConsole, 2000);
