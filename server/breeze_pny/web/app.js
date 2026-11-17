'use strict';
const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('breeze-companion-token') || '';
if (token) sessionStorage.setItem('breeze-companion-token', token);
history.replaceState(null, '', location.pathname);
let state, selected, decoded, converted, pending, busy = false;
const audioUrls = new Map();

function status(message, error = false) {
  $('status').textContent = message;
  $('status').className = error ? 'error' : '';
}
async function request(path, data) {
  const options = {headers: {'X-Breeze-Token': token}};
  if (data !== undefined) {
    options.method = 'POST';
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    const result = await response.json();
    throw new Error(result.error || 'The voice operation failed');
  }
  return response.headers.get('Content-Type').startsWith('audio/') ? response.blob() : response.json();
}
function controls() {
  document.querySelectorAll('#tab-voices button,#tab-voices input,#tab-voices textarea').forEach(element => { element.disabled = busy; });
  $('convert').disabled = busy || !decoded;
  $('try').disabled = busy || !converted || !$('new-transcript').value.trim();
  $('apply').disabled = busy || !pending;
  $('undo').disabled = busy || !state?.can_undo;
  $('reference').disabled = busy || !selected?.reference_available;
  document.body.classList.toggle('busy', busy);
}
async function perform(message, operation) {
  if (busy) return;
  busy = true; controls(); status(message);
  try { await operation(); }
  catch (error) { status(error.message, true); }
  finally { busy = false; controls(); }
}
function clearAudio(id) {
  const element = $(id);
  element.pause(); element.removeAttribute('src'); element.hidden = true;
  if (audioUrls.has(id)) URL.revokeObjectURL(audioUrls.get(id));
  audioUrls.delete(id);
}
function showAudio(id, blob) {
  clearAudio(id);
  const url = URL.createObjectURL(blob);
  audioUrls.set(id, url); $(id).src = url; $(id).hidden = false;
}
function referenceSource(value) {
  const episode = /^(?:fim_)?s(\d+)e(\d+)$/i.exec(value);
  if (episode) return `Friendship Is Magic · Season ${Number(episode[1])}, episode ${Number(episode[2])}`;
  const labels = {eqg: 'Equestria Girls', eqg_friendship_games: 'Equestria Girls: Friendship Games',
    mlp_movie_2017: 'My Little Pony: The Movie (2017)', breeze_voice_design: 'Breeze voice design',
    fan_nowacking_vinyl: 'Nowacking fan voice · Vinyl Scratch'};
  return Object.hasOwn(labels, value) ? labels[value] : value;
}
function processingNotes(value) {
  if (typeof value !== 'string') return value;
  // Omit historical exclusion notes, preserving actual processing and source claims.
  return value.replace(/no trimming, pitch, timing, or Kokoro audio/g, 'no trimming, pitch, or timing')
    .replace(/no effects or Kokoro (?:source|audio)/g, 'no effects')
    .replace(/[;,] no Kokoro(?:-derived source)? audio/g, '');
}
function renderProvenance(id, character) {
  const container = $(id), signature = JSON.stringify([character?.id, character?.source]);
  if (container.dataset.signature === signature) return;
  container.dataset.signature = signature;
  const source = character?.source || {}, list = document.createElement('dl');
  const field = (label, value, link = false) => {
    if (typeof value !== 'string' || !value.trim()) return;
    value = value.trim();
    const term = document.createElement('dt'), detail = document.createElement('dd');
    term.textContent = label; detail.textContent = value;
    if (link) {
      try {
        const url = new URL(value);
        if (url.protocol === 'https:' || url.protocol === 'http:') {
          const anchor = document.createElement('a');
          anchor.href = url.href; anchor.textContent = url.hostname;
          anchor.target = '_blank'; anchor.rel = 'noopener noreferrer';
          detail.replaceChildren(anchor);
        }
      } catch (_) { /* Keep malformed URLs as plain source text. */ }
    }
    list.append(term, detail);
  };
  if (typeof source.episode === 'string') field('Source', referenceSource(source.episode.trim()));
  field('Recording', source.source_url, true);
  field('Annotations', source.annotation_url, true);
  field('Notes', source.notes);
  if (!list.childElementCount) field('Source', 'No source information was included for this reference.');
  field('Audio processing', processingNotes(source.processing));
  container.replaceChildren(list);
}
function renderGenerateProvenance() {
  const character = state.characters.find(row => row.id === $('voice').value);
  $('generate-provenance').hidden = !character;
  if (character) renderProvenance('generate-source', character);
}
function invalidate() {
  pending = null; clearAudio('new-speech-audio'); controls();
}
function renderList() {
  const query = $('search').value.toLocaleLowerCase();
  const rows = state.characters.filter(row => `${row.name} ${row.id}`.toLocaleLowerCase().includes(query));
  $('count').textContent = `${rows.length} of ${state.characters.length} characters`;
  $('characters').replaceChildren(...rows.map(row => {
    const button = document.createElement('button');
    button.textContent = row.name + (row.custom ? ' ·' : '');
    button.className = row.id === selected?.id ? 'active' : '';
    button.disabled = busy;
    button.onclick = () => select(row.id);
    return button;
  }));
}
function select(id) {
  selected = state.characters.find(row => row.id === id) || state.characters[0];
  $('detail').hidden = false; $('name').textContent = selected.name;
  $('transcript').textContent = selected.transcript;
  renderProvenance('source', selected);
  $('custom').hidden = !selected.custom;
  $('reference').hidden = !selected.reference_available;
  $('missing').hidden = selected.reference_available;
  decoded = converted = pending = null;
  $('file').value = ''; $('new-transcript').value = ''; $('new-source').value = '';
  $('start').value = '0'; $('end').value = '';
  $('file-info').textContent = 'Audio formats depend on your browser. WAV is the most portable choice.';
  for (const id of ['current-audio', 'speech-audio', 'replacement-audio', 'new-speech-audio']) clearAudio(id);
  renderList(); controls();
}
function wavBlob(samples) {
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const string = (at, value) => { for (let i = 0; i < value.length; i++) view.setUint8(at + i, value.charCodeAt(i)); };
  string(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); string(8, 'WAVE');
  string(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, 24000, true); view.setUint32(28, 48000, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); string(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    if (!Number.isFinite(sample)) throw new Error('The recording contains invalid audio samples');
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
  return new Blob([buffer], {type: 'audio/wav'});
}
async function convertSelection() {
  const start = Number($('start').value), end = Number($('end').value);
  if (!decoded || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > decoded.duration || end - start < .25 || end - start > 30) {
    throw new Error('Select between 0.25 and 30 seconds within the recording');
  }
  const frames = Math.max(1, Math.round((end - start) * 24000));
  const offline = new OfflineAudioContext(1, frames, 24000);
  const mono = offline.createBuffer(1, decoded.length, decoded.sampleRate);
  const samples = mono.getChannelData(0);
  for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
    const input = decoded.getChannelData(channel);
    for (let i = 0; i < samples.length; i++) samples[i] += input[i] / decoded.numberOfChannels;
  }
  const source = offline.createBufferSource(); source.buffer = mono;
  source.connect(offline.destination); source.start(0, start, end - start);
  const result = await offline.startRendering();
  converted = wavBlob(result.getChannelData(0));
  invalidate(); showAudio('replacement-audio', converted);
  status(`Selection prepared: ${(frames / 24000).toFixed(2)} seconds. Listen and enter its exact words.`);
}
async function base64(blob) {
  const raw = new Uint8Array(await blob.arrayBuffer());
  let value = '';
  for (let at = 0; at < raw.length; at += 8192) value += String.fromCharCode(...raw.subarray(at, at + 8192));
  return btoa(value);
}
$('search').oninput = renderList;
$('reference').onclick = () => perform('Loading reference…', async () => {
  showAudio('current-audio', await request('/api/reference?voice=' + encodeURIComponent(selected.voice_id)));
  status('Reference ready to play.');
});
$('current-preview').onclick = () => perform('Generating preview…', async () => {
  showAudio('speech-audio', await request('/api/audition', {character: selected.id, text: $('preview-text').value}));
  status('Current voice preview ready.');
});
$('file').onchange = () => perform('Reading the recording locally…', async () => {
  decoded = converted = pending = null;
  clearAudio('replacement-audio'); clearAudio('new-speech-audio');
  const file = $('file').files[0];
  if (!file) return;
  if (file.size > 64 * 1024 * 1024) throw new Error('Choose an audio file smaller than 64 MiB; trim longer recordings first');
  try {
    const decoder = new OfflineAudioContext(1, 1, 24000);
    decoded = await decoder.decodeAudioData(await file.arrayBuffer());
  } catch (_) { throw new Error('Your browser could not decode this format. Export a WAV or try another browser.'); }
  if (decoded.duration > 300) { decoded = null; throw new Error('Trim recordings longer than five minutes before importing'); }
  $('start').value = '0'; $('end').value = String(Math.floor(Math.min(decoded.duration, 10) * 1000) / 1000);
  $('file-info').textContent = `${file.name} · ${decoded.duration.toFixed(2)} seconds · choose the section to use`;
  await convertSelection();
});
for (const id of ['start', 'end']) $(id).oninput = () => { converted = null; invalidate(); clearAudio('replacement-audio'); };
$('convert').onclick = () => perform('Preparing selection…', convertSelection);
for (const id of ['new-transcript', 'new-source', 'preview-text']) $(id).oninput = invalidate;
$('try').onclick = () => perform('Preparing your reference and generating a preview…', async () => {
  pending = null;
  const proposal = await request('/api/prepare', {character: selected.id, transcript: $('new-transcript').value,
    source: $('new-source').value, wav: await base64(converted)});
  showAudio('new-speech-audio', await request('/api/audition', {character: selected.id, text: $('preview-text').value, pending_id: proposal.id}));
  pending = proposal.id;
  status('Replacement preview ready. Listen before saving.');
});
$('apply').onclick = () => perform('Saving your reference and keeping the previous voice pack…', async () => {
  const identity = selected.id;
  state = await request('/api/apply', {pending_id: pending});
  select(identity);
  status('Reference saved. Generation and the API now use this voice.');
});
$('undo').onclick = () => perform('Restoring the previous voice pack…', async () => {
  const identity = selected.id;
  state = await request('/api/undo', {}); select(identity);
  status('Previous voice pack restored.');
});

let generation = null, refreshTimer, modelSignature = '', jobSignature = '';
function renderVoices() {
  const current = $('voice').value;
  const query = $('voice-search').value.toLocaleLowerCase();
  const rows = state.characters.filter(row => `${row.name} ${row.id}`.toLocaleLowerCase().includes(query));
  $('voice').replaceChildren(...rows.map(row => new Option(row.name, row.id)));
  $('voice').value = rows.some(row => row.id === current) ? current : (rows[0]?.id || '');
  $('generate').disabled = Boolean(generation) || !state.ready || !rows.length || !$('text').value.trim();
  renderGenerateProvenance();
}
function renderModels() {
  const signature = JSON.stringify([state.models, state.job?.status, state.ready, state.speech_busy]);
  if (signature === modelSignature) return;
  modelSignature = signature;
  const running = state.job?.status === 'running';
  for (const [id, experimental] of [['model-list', false], ['experimental-models', true]]) {
    $(id).replaceChildren(...state.models.filter(item => item.experimental === experimental).map(item => {
      const row = document.createElement('div'); row.className = 'model-row';
      const info = document.createElement('div'); info.className = 'model-info';
      const name = document.createElement('strong'); name.textContent = item.name;
      const size = document.createElement('span'); size.className = 'model-size'; size.textContent = `${(item.bytes / 1e9).toFixed(2)} GB`;
      const label = document.createElement('span'); label.className = 'model-state';
      label.textContent = item.loaded ? 'Loaded' : item.installed ? (item.selected ? 'Installed · selected' : 'Installed') : 'Not downloaded';
      const note = document.createElement('p'); note.className = 'muted'; note.textContent = item.note;
      info.append(name, size, label, note);
      const actions = document.createElement('div'); actions.className = 'model-actions';
      const add = (action, title, disabled) => {
        const button = document.createElement('button'); button.textContent = title;
        button.dataset.action = action; button.dataset.model = item.id;
        button.disabled = running || disabled;
        button.onclick = async () => {
          if (action === 'delete' && !confirm(`Delete the ${item.name} download (${(item.bytes / 1e9).toFixed(2)} GB)? Your voices are kept. You can download this model again.`)) return;
          try {
            await request('/api/models', {action, model: item.id});
            status(`${title}: ${item.name}…`); await refresh();
          } catch (error) { status(error.message, true); }
        };
        actions.append(button);
      };
      if (!item.installed) add('download', 'Download', !item.compatible);
      else {
        add(item.loaded ? 'unload' : 'load', item.loaded ? 'Unload' : 'Load', !item.compatible || state.speech_busy);
        add('delete', 'Delete', item.loaded || state.speech_busy);
      }
      row.append(info, actions); return row;
    }));
  }
}
async function refresh() {
  try {
    const next = await request('/api/state');
    const first = !state;
    state = next;
    $('version').textContent = state.version;
    $('pack').textContent = state.characters.length + ' voices · ' + state.voice_pack;
    $('api-address').textContent = 'TTS API: http://127.0.0.1:' + state.api_port + '/tts';
    const loaded = state.models.find(item => item.loaded);
    $('engine').textContent = state.ready ? `${loaded?.name || 'Model'} ready` : state.phase === 'loading' ? 'Loading model…' : state.phase === 'error' ? 'Renderer stopped' : 'Model unloaded';
    if (first) { select('derpy_hooves'); renderVoices(); }
    else $('generate').disabled = Boolean(generation) || !state.ready || !$('voice').value || !$('text').value.trim();
    renderGenerateProvenance();
    renderModels();
    const job = state.job;
    $('model-job').hidden = !job;
    if (job) {
      const detail = job.total ? ` · ${(job.done / 1e9).toFixed(2)} / ${(job.total / 1e9).toFixed(2)} GB` : '';
      $('job-text').textContent = `${job.action} ${job.model || ''}: ${job.status === 'running' ? job.phase : job.status}${detail}${job.error ? ' · ' + job.error : ''}`;
      if (job.total) { $('job-progress').max = job.total; $('job-progress').value = job.done; }
      else $('job-progress').removeAttribute('value');
      $('job-progress').hidden = job.status !== 'running';
      $('cancel-download').hidden = !(job.action === 'download' && job.status === 'running');
      const signature = JSON.stringify([job.action, job.model, job.status, job.error]);
      if (signature !== jobSignature && job.status === 'failed') status(job.error, true);
      jobSignature = signature;
    }
  } catch (error) {
    $('engine').textContent = 'Disconnected'; $('generate').disabled = true;
    status(error.message || 'Could not reach the companion. Check its terminal.', true);
  }
}
for (const tab of document.querySelectorAll('[data-tab]')) tab.onclick = () => {
  for (const button of document.querySelectorAll('[data-tab]')) {
    const active = button === tab;
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    $('tab-' + button.dataset.tab).hidden = !active;
  }
};
$('voice-search').oninput = renderVoices;
$('voice').onchange = renderGenerateProvenance;
$('text').oninput = () => { $('text-count').textContent = [...$('text').value].length; renderVoices(); };
$('generate').onclick = async () => {
  if (generation) return;
  $('generated-audio').pause();
  generation = new AbortController();
  const character = $('voice').value, text = $('text').value;
  const name = state.characters.find(row => row.id === character)?.name || character;
  $('generate').disabled = true; $('cancel').hidden = false;
  $('generation-note').textContent = 'Generating…'; status('Generating ' + name + '…');
  const started = performance.now();
  try {
    const response = await fetch('/tts', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Breeze-Token': token},
      body: JSON.stringify({character_id: character, text}), signal: generation.signal});
    if (!response.ok) throw new Error((await response.json()).error || 'Generation failed');
    showAudio('generated-audio', await response.blob());
    $('result').hidden = false;
    $('download').href = audioUrls.get('generated-audio'); $('download').download = character + '.wav';
    $('result-label').textContent = `${name} · ${((performance.now() - started) / 1000).toFixed(1)} seconds to generate`;
    status('Speech ready.');
    const audio = $('generated-audio'), source = audio.src;
    audio.play().catch(() => {
      if (audio.src === source && !generation) status('Speech ready. Press Play below to listen, or download the WAV.');
    });
  } catch (error) {
    status(error.name === 'AbortError' ? 'Generation cancelled.' : error.message, error.name !== 'AbortError');
  } finally {
    generation = null; $('cancel').hidden = true; $('generation-note').textContent = '';
    await refresh();
  }
};
$('cancel').onclick = () => generation?.abort();
$('cancel-download').onclick = async () => {
  try { await request('/api/download/cancel', {}); status('Cancelling download…'); }
  catch (error) { status(error.message, true); }
};
$('text-count').textContent = [...$('text').value].length;
refresh().then(() => { if (state) status('Choose a voice and enter your text.'); });
refreshTimer = setInterval(refresh, 1500);
window.addEventListener('pagehide', () => { clearInterval(refreshTimer); generation?.abort(); });
