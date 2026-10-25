import { el } from './admin-shared.js';
import { state } from './admin-state.js';

// @llr LLR-SRV-CONFIG-024
/** Decode locally, then send bounded mono PCM rather than a native codec input.
 * @param {File} file */
export async function ringtoneWav(file) {
  if (!file.size || file.size > 12 * 1024 * 1024) throw Error('Choose an audio file up to 12 MB.');
  const decoder = new AudioContext();
  let source;
  try {
    source = await decoder.decodeAudioData(await file.arrayBuffer());
  } finally {
    await decoder.close();
  }
  const frames = Math.min(16000 * 30, Math.floor(source.duration * 16000));
  if (!frames) throw Error('This audio file is empty.');
  const render = new OfflineAudioContext(1, frames, 16000);
  const input = render.createBufferSource();
  input.buffer = source;
  input.connect(render.destination);
  input.start();
  const samples = (await render.startRendering()).getChannelData(0);
  const bytes = new ArrayBuffer(44 + 2 * frames),
    view = new DataView(bytes);
  const text = (/** @type {number} */ offset, /** @type {string} */ value) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, 'RIFF');
  view.setUint32(4, bytes.byteLength - 8, true);
  text(8, 'WAVEfmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i++)
    view.setInt16(44 + 2 * i, Math.round(Math.max(-1, Math.min(1, samples[i])) * 32767), true);
  return bytes;
}

// @llr LLR-SRV-CONFIG-024
/** @param {import('../types/admin-dom').TerminalForm} form @param {string} id */
export function ringtoneField(form, id) {
  const field = el('div'),
    label = el('label', 'Ringtone'),
    select = el('select');
  select.name = 'ringtone';
  select.setAttribute('aria-label', 'Ringtone');
  form.fields.ringtone = select;
  for (const choice of state.model.ringtone_choices) {
    const option = el('option', choice.name);
    option.value = choice.id;
    select.append(option);
  }
  select.value = state.model.profiles[id].ringtone || 'nokia';
  label.append(select);
  field.append(label);
  const audio = el('audio');
  audio.controls = true;
  audio.preload = 'none';
  audio.setAttribute('aria-label', 'Ringtone preview');
  const update = () => {
    audio.pause();
    audio.src = `/api/ringtones/${select.value}.wav`;
  };
  select.onchange = update;
  update();
  field.append(audio);
  /** @type {ReturnType<typeof setInterval> | undefined} */
  let timer;
  audio.onplay = () => {
    clearInterval(timer);
    document.querySelectorAll('audio').forEach((other) => {
      if (other !== audio) other.pause();
    });
    timer = setInterval(() => {
      if (!audio.isConnected || audio.offsetParent === null || audio.currentTime >= 10) {
        audio.pause();
        audio.currentTime = 0;
      }
    }, 100);
  };
  audio.onpause = audio.onended = () => {
    clearInterval(timer);
    timer = undefined;
  };
  const uploadLabel = el('label', 'Add ringtones'),
    upload = el('input'),
    message = el('small');
  upload.type = 'file';
  upload.accept = 'audio/*';
  upload.multiple = true;
  upload.setAttribute('aria-label', 'Add ringtone files');
  uploadLabel.append(upload);
  field.append(uploadLabel, message);
  field.append(
    el(
      'small',
      'Preview plays on this computer. Add your own audio files; the first 30 seconds are kept privately on this server. Nokia remains the default.',
    ),
  );
  upload.onchange = async () => {
    const files = Array.from(upload.files || []);
    upload.disabled = true;
    audio.pause();
    try {
      for (const file of files) {
        message.textContent = 'Adding ' + file.name + '…';
        const name = file.name.replace(/\.[^.]+$/, '').slice(0, 80),
          bytes = await ringtoneWav(file);
        const response = await fetch(
          `/api/ringtones?name=${encodeURIComponent(name)}&version=${form.configurationVersion}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'audio/wav' },
            body: bytes,
          },
        );
        const result = await response.json();
        if (!response.ok) throw Error(result.error || 'Ringtone upload failed.');
        form.configurationVersion = result.configuration_version;
        state.model.configuration_version = result.configuration_version;
        const old = state.model.ringtone_choices.find((choice) => choice.id === result.id);
        if (old) Object.assign(old, result);
        else state.model.ringtone_choices.push(result);
        let option = Array.from(select.options).find((option) => option.value === result.id);
        if (!option) {
          option = el('option');
          option.value = result.id;
          select.append(option);
        }
        option.textContent = result.name;
        select.value = result.id;
        update();
      }
      message.textContent = files.length ? 'Ringtones added. Choose a tone and save changes.' : '';
    } catch (error) {
      message.textContent = error instanceof Error ? error.message : 'Ringtone upload failed.';
    } finally {
      upload.disabled = false;
      upload.value = '';
    }
  };
  return field;
}
