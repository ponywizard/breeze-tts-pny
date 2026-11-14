'use strict';
const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem('breeze-voice-token') || '';
if (token) sessionStorage.setItem('breeze-voice-token', token);
history.replaceState(null, '', location.pathname);
let state, selected, decoded, converted, pending, busy = false;
const audioUrls = new Map();

function status(message, error = false) {
  $('status').textContent = message;
  $('status').className = error ? 'error' : '';
}
async function request(path, data) {
  const options = {headers: {'X-Voice-Library-Token': token}};
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
  document.querySelectorAll('button,input,textarea').forEach(element => { element.disabled = busy; });
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
  $('source').textContent = selected.source.notes || selected.source.source_url || selected.source.episode || '';
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
$('current-preview').onclick = () => perform('Generating preview. The first preview loads Breeze and may take a few minutes…', async () => {
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
$('try').onclick = () => perform('Preparing your reference and generating a preview. The first preview loads Breeze…', async () => {
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
  status('Reference saved. Close the library and restart the companion when you finish.');
});
$('undo').onclick = () => perform('Restoring the previous voice pack…', async () => {
  const identity = selected.id;
  state = await request('/api/undo', {}); select(identity);
  status('Previous voice pack restored.');
});
$('close').onclick = () => perform('Closing…', async () => {
  await request('/api/close', {});
  status('Library closed. You can close this tab and start the companion.');
  document.querySelector('main').hidden = true; $('close').hidden = true;
});
perform('Opening your voice pack…', async () => {
  state = await request('/api/state'); select('derpy_hooves');
  $('utility-version').textContent = 'BREEZE TTS PNY · REFERENCE MANAGER ' + state.utility_version;
  status('Choose a character to listen or replace a reference.');
});
