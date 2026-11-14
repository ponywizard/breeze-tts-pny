// Optional browser integration: node tests/voice_library_browser.cjs [chromium]
// Uses Node's built-in CDP WebSocket client; no npm packages are needed.
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function firstLine(stream) {
  return new Promise((resolve, reject) => {
    let raw = '';
    const timeout = setTimeout(() => reject(Error('Fixture did not start')), 10000);
    stream.on('data', chunk => {
      raw += chunk;
      if (raw.includes('\n')) { clearTimeout(timeout); resolve(raw.split('\n')[0]); }
    });
  });
}

(async () => {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'voice-library-chromium-'));
  const fixture = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'voice_library_fixture.py')], {stdio: ['ignore', 'pipe', 'inherit']});
  let browser, socket;
  try {
    const info = JSON.parse(await firstLine(fixture.stdout));
    browser = spawn(process.argv[2] || 'chromium', ['--headless', '--no-sandbox', '--disable-gpu',
      '--disable-background-networking', '--no-first-run', '--remote-debugging-port=0',
      '--user-data-dir=' + profile, 'about:blank'], {stdio: ['ignore', 'ignore', 'ignore']});
    let port;
    for (let i = 0; i < 100; i++) {
      if (fs.existsSync(path.join(profile, 'DevToolsActivePort'))) {
        port = Number(fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]); break;
      }
      await delay(100);
    }
    assert.ok(port, 'Chromium did not start');
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    socket = new WebSocket(targets.find(item => item.type === 'page').webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let next = 1;
    const requests = new Map(), errors = [];
    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.id && requests.has(message.id)) {
        const {resolve, reject} = requests.get(message.id); requests.delete(message.id);
        message.error ? reject(Error(JSON.stringify(message.error))) : resolve(message.result);
      }
      if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
      if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') errors.push(message.params.entry.text);
    };
    const command = (method, params = {}) => new Promise((resolve, reject) => {
      const id = next++; requests.set(id, {resolve, reject}); socket.send(JSON.stringify({id, method, params}));
    });
    const evaluate = async expression => {
      const result = await command('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
      if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
      return result.result.value;
    };
    const waitFor = async expression => {
      for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await delay(100); }
      throw Error('Browser timed out: ' + expression + ' | ' + await evaluate('document.body.innerText'));
    };
    await command('Runtime.enable'); await command('Log.enable');
    await command('Emulation.setDeviceMetricsOverride', {width: 1200, height: 1300, deviceScaleFactor: 1, mobile: false});
    await command('Page.navigate', {url: info.url});
    await waitFor("document.getElementById('name')?.textContent === 'Derpy Hooves'");
    assert.equal(await evaluate("document.querySelectorAll('#characters button').length"), 2);
    await evaluate("document.getElementById('reference').click()");
    await waitFor("!document.getElementById('current-audio').hidden");
    await evaluate("document.getElementById('current-preview').click()");
    await waitFor("!document.getElementById('speech-audio').hidden && !busy");
    const document = await command('DOM.getDocument');
    const input = await command('DOM.querySelector', {nodeId: document.root.nodeId, selector: '#file'});
    await command('DOM.setFileInputFiles', {nodeId: input.nodeId, files: [info.recording]});
    await waitFor("!document.getElementById('replacement-audio').hidden && !busy");
    if (process.env.VOICE_LIBRARY_SCREENSHOT) {
      const capture = await command('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
      fs.mkdirSync(path.dirname(process.env.VOICE_LIBRARY_SCREENSHOT), {recursive: true});
      fs.writeFileSync(process.env.VOICE_LIBRARY_SCREENSHOT, Buffer.from(capture.data, 'base64'));
    }
    const details = await evaluate(`(async () => {
      const view = new DataView(await converted.arrayBuffer());
      return {channels:view.getUint16(22,true),rate:view.getUint32(24,true),bits:view.getUint16(34,true),frames:view.getUint32(40,true)/2,sample:view.getInt16(44+12000*2,true)};
    })()`);
    assert.deepEqual(details, {channels: 1, rate: 24000, bits: 16, frames: 24000, sample: 3000});
    await evaluate("document.getElementById('new-transcript').value = 'Replacement words.'; document.getElementById('new-transcript').dispatchEvent(new Event('input')); document.getElementById('try').click()");
    await waitFor("!document.getElementById('apply').disabled && !busy");
    await evaluate("document.getElementById('apply').click()");
    await waitFor("!busy && !document.getElementById('custom').hidden");
    const config = JSON.parse(fs.readFileSync(info.config, 'utf8'));
    assert.ok(config.voice_pack.includes('custom-'));
    const bank = JSON.parse(fs.readFileSync(path.join(path.dirname(info.config), config.voice_pack, 'voice-pack.json'), 'utf8'));
    assert.equal(bank.characters.find(row => row.id === 'spike').voice_id, 'shared');
    assert.equal(bank.voices[bank.custom_voices.derpy_hooves].ref_text, 'Replacement words.');
    await evaluate("document.getElementById('undo').click()");
    await waitFor("!busy && document.getElementById('custom').hidden");
    for (const recording of info.compressed) {
      await command('DOM.setFileInputFiles', {nodeId: input.nodeId, files: [recording]});
      await waitFor("!document.getElementById('replacement-audio').hidden && !busy");
      assert.ok(await evaluate('converted.size > 24000'), 'Compressed input was not decoded');
    }
    await command('Emulation.setDeviceMetricsOverride', {width: 400, height: 900, deviceScaleFactor: 1, mobile: true});
    assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile layout overflows');
    await command('Page.reload');
    await waitFor("document.getElementById('name')?.textContent === 'Derpy Hooves'");
    assert.deepEqual(errors, [], 'Browser console errors');
    await evaluate("document.getElementById('close').click()");
    await waitFor("document.getElementById('status').textContent.includes('Library closed')");
    console.log('PASS: reference playback, current preview, 48 kHz stereo conversion, replacement preview, save, undo, compressed input, mobile layout, reload, close');
  } finally {
    if (socket) socket.close();
    if (browser) { browser.kill(); await new Promise(resolve => browser.once('exit', resolve)); }
    fixture.kill();
    if (fixture.exitCode === null) await new Promise(resolve => fixture.once('exit', resolve));
    fs.rmSync(profile, {recursive: true, force: true});
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
