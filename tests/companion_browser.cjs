// Optional browser integration: node tests/companion_browser.cjs [chromium]
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
  const fixture = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, 'companion_fixture.py')], {stdio: ['ignore', 'pipe', 'inherit']});
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
    const evaluate = async (expression, userGesture = false) => {
      const result = await command('Runtime.evaluate', {expression, userGesture, awaitPromise: true, returnByValue: true});
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
    await evaluate("document.querySelector('[data-tab=voices]').click()");
    assert.equal(await evaluate("document.querySelectorAll('#characters button').length"), 2);
    assert.ok(await evaluate("document.getElementById('source').textContent.includes('Season 2, episode 14')"));
    assert.equal(await evaluate("document.querySelector('#source a').href"), 'https://example.org/recording#clip');
    assert.equal(await evaluate("document.querySelector('#source a').rel"), 'noopener noreferrer');
    assert.equal(await evaluate("document.querySelectorAll('#source a').length"), 2);
    assert.ok(await evaluate("document.getElementById('source').textContent.includes('Cut to dialogue')"));
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
    await evaluate("document.getElementById('new-transcript').value = 'Replacement words.'; document.getElementById('new-source').value = 'My own recording <img src=x onerror=alert(1)>'; document.getElementById('new-transcript').dispatchEvent(new Event('input')); document.getElementById('try').click()");
    await waitFor("!document.getElementById('apply').disabled && !busy");
    await evaluate("document.getElementById('apply').click()");
    await waitFor("!busy && !document.getElementById('custom').hidden");
    assert.ok(await evaluate("document.getElementById('source').textContent.includes('My own recording <img src=x onerror=alert(1)>')"));
    assert.equal(await evaluate("document.querySelectorAll('#source img, #source a').length"), 0);
    await waitFor("document.getElementById('generate-source').textContent.includes('My own recording')");
    await evaluate("document.getElementById('voice').value = 'spike'; document.getElementById('voice').dispatchEvent(new Event('change'))");
    assert.ok(await evaluate("document.getElementById('generate-source').textContent.includes('Season 2, episode 14')"));
    await evaluate("document.getElementById('voice').value = 'derpy_hooves'; document.getElementById('voice').dispatchEvent(new Event('change'))");
    assert.ok(await evaluate("document.getElementById('generate-source').textContent.includes('My own recording')"));
    // Generate identical text across two references, using keyboard selection as a user would.
    await evaluate("document.querySelector('[data-tab=generate]').click()");
    await evaluate("window.testAudioBlobs = new Map(); const fixtureCreateObjectURL = URL.createObjectURL.bind(URL); URL.createObjectURL = blob => { const url = fixtureCreateObjectURL(blob); window.testAudioBlobs.set(url, blob); return url; }");
    await evaluate(`window.testSpeechRequests = []; const fixtureFetch = window.fetch.bind(window);
      window.fetch = async (url, options) => {
        const response = await fixtureFetch(url, options);
        if (url === '/tts') window.testSpeechRequests.push({body: JSON.parse(options.body), seed: response.headers.get('X-Breeze-Seed')});
        return response;
      };`);
    assert.equal(await evaluate("document.getElementById('randomize-seed').checked"), true);
    const unchangedText = await evaluate("document.getElementById('text').value");
    const generateSample = async (identity, sample) => {
      const previous = await evaluate("document.getElementById('generated-audio').src");
      if (previous) {
        await evaluate("document.getElementById('generated-audio').currentTime = 0; document.getElementById('generated-audio').play()", true);
        assert.equal(await evaluate("document.getElementById('generated-audio').paused"), false);
      }
      assert.equal(await evaluate("document.getElementById('generate').click(); document.getElementById('generated-audio').paused", true), true,
        'Previous speech kept playing while generating another voice');
      await waitFor("!generation && document.getElementById('status').textContent.includes('Speech ready')");
      assert.equal(await evaluate("document.getElementById('download').download"), identity + '.wav');
      const current = await evaluate("document.getElementById('generated-audio').currentSrc");
      assert.notEqual(current, previous, 'The player kept the previous clip');
      assert.equal(await evaluate("document.getElementById('download').href"), current);
      assert.equal(await evaluate("(async () => new DataView(await window.testAudioBlobs.get(document.getElementById('download').href).arrayBuffer()).getInt16(44, true))()"), sample);
      assert.equal(await evaluate("document.getElementById('text').value"), unchangedText);
      const request = await evaluate('window.testSpeechRequests.at(-1)');
      assert.ok(Number.isInteger(request.body.seed) && request.body.seed >= 0 && request.body.seed <= 2147483647);
      assert.equal(request.seed, String(request.body.seed));
      assert.equal(request.body.direction, await evaluate("document.getElementById('direction').value.trim()"));
      assert.equal(await evaluate("document.getElementById('seed').valueAsNumber"), request.body.seed);
      assert.ok(await evaluate(`document.getElementById('result-label').textContent.includes('Seed ${request.body.seed} ·')`));
      return request.body.seed;
    };
    const selectNext = async (key, code) => {
      await evaluate("document.getElementById('voice').focus()");
      await command('Input.dispatchKeyEvent', {type: 'keyDown', key, code: key, windowsVirtualKeyCode: code});
      await command('Input.dispatchKeyEvent', {type: 'keyUp', key, code: key, windowsVirtualKeyCode: code});
    };
    const firstSeed = await generateSample('derpy_hooves', 3000);
    await selectNext('ArrowDown', 40);
    assert.equal(await evaluate("document.getElementById('voice').value"), 'spike');
    const secondSeed = await generateSample('spike', 1500);
    assert.notEqual(secondSeed, firstSeed, 'Random mode reused the previous seed');
    await evaluate("document.getElementById('randomize-seed').click()");
    await selectNext('ArrowUp', 38);
    assert.equal(await generateSample('derpy_hooves', 3000), secondSeed, 'Unchecking randomization did not keep the last seed');
    await evaluate("document.getElementById('randomize-seed').click(); document.getElementById('seed').value = '0'; document.getElementById('seed').dispatchEvent(new Event('input'))");
    assert.equal(await evaluate("document.getElementById('randomize-seed').checked"), false, 'Typing a seed did not select fixed mode');
    assert.equal(await generateSample('derpy_hooves', 3000), 0);
    assert.equal(await generateSample('derpy_hooves', 3000), 0, 'Fixed seed changed on the next generation');
    const requestCount = await evaluate('window.testSpeechRequests.length');
    for (const invalid of ['', '-1', '1.5', '2147483648']) {
      await evaluate(`document.getElementById('seed').value = '${invalid}'; document.getElementById('seed').dispatchEvent(new Event('input')); document.getElementById('generate').click()`);
      assert.equal(await evaluate("document.getElementById('seed').validity.valid"), false);
      assert.equal(await evaluate('generation'), null);
    }
    assert.equal(await evaluate('window.testSpeechRequests.length'), requestCount, 'Invalid seed submitted speech');
    await evaluate("document.getElementById('seed').value = '2147483647'; document.getElementById('seed').dispatchEvent(new Event('input'))");
    assert.equal(await generateSample('derpy_hooves', 3000), 2147483647);
    const direction = 'Speak softly & slowly. <em>Sad, hesitant.</em>';
    await evaluate(`document.getElementById('direction').value = ${JSON.stringify('  ' + direction + '  ')}`);
    assert.equal(await generateSample('derpy_hooves', 3000), 2147483647);
    assert.equal(await evaluate("document.getElementById('result-direction').textContent"), 'Direction: ' + direction);
    assert.equal(await evaluate("document.querySelectorAll('#result-direction em').length"), 0);
    assert.equal(await evaluate("document.getElementById('result-direction').hidden"), false);
    await evaluate("document.getElementById('direction').value = ''");
    assert.equal(await evaluate("document.getElementById('result-direction').textContent"), 'Direction: ' + direction, 'Editing direction changed the previous take’s label');
    assert.equal(await generateSample('derpy_hooves', 3000), 2147483647);
    assert.equal(await evaluate("document.getElementById('result-direction').hidden"), true);
    await evaluate("document.querySelector('[data-tab=voices]').click()");
    const config = JSON.parse(fs.readFileSync(info.config, 'utf8'));
    assert.ok(config.voice_pack.includes('custom-'));
    const bank = JSON.parse(fs.readFileSync(path.join(path.dirname(info.config), config.voice_pack, 'voice-pack.json'), 'utf8'));
    assert.equal(bank.characters.find(row => row.id === 'spike').voice_id, 'shared');
    assert.equal(bank.voices[bank.custom_voices.derpy_hooves].ref_text, 'Replacement words.');
    await evaluate("document.getElementById('undo').click()");
    await waitFor("!busy && document.getElementById('custom').hidden");
    assert.ok(await evaluate("document.getElementById('source').textContent.includes('Season 2, episode 14')"));
    await waitFor("document.getElementById('generate-source').textContent.includes('Season 2, episode 14')");
    for (const recording of info.compressed) {
      await command('DOM.setFileInputFiles', {nodeId: input.nodeId, files: [recording]});
      await waitFor("!document.getElementById('replacement-audio').hidden && !busy");
      assert.ok(await evaluate('converted.size > 24000'), 'Compressed input was not decoded');
    }
    await command('Emulation.setDeviceMetricsOverride', {width: 400, height: 900, deviceScaleFactor: 1, mobile: true});
    assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile layout overflows');
    await evaluate("document.querySelector('[data-tab=generate]').click()");
    assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile seed controls overflow');
    await command('Page.reload');
    await waitFor("document.getElementById('name')?.textContent === 'Derpy Hooves'");
    assert.equal(await evaluate("document.getElementById('seed').valueAsNumber"), 2147483647);
    assert.equal(await evaluate("document.getElementById('randomize-seed').checked"), false);
    await evaluate("document.querySelector('[data-tab=voices]').click()");
    assert.deepEqual(errors, [], 'Browser console errors');
    await evaluate("window.generatedPlaybackStarted = false; document.getElementById('generated-audio').addEventListener('playing', () => { window.generatedPlaybackStarted = true; }, {once: true}); document.querySelector('[data-tab=generate]').click(); document.getElementById('generate').click()", true);
    await waitFor("!document.getElementById('result').hidden && !generation");
    assert.ok(await evaluate("document.getElementById('download').href.startsWith('blob:')"));
    assert.equal(await evaluate("document.getElementById('generated-audio').readyState >= 1"), true);
    await waitFor('window.generatedPlaybackStarted');
    await evaluate("document.getElementById('text').value = '__cancel__'; document.getElementById('generate').click()");
    await waitFor("generation !== null");
    await evaluate('refresh()');
    await waitFor('state.speech_busy');
    assert.equal(await evaluate("document.getElementById('seed').disabled && document.getElementById('randomize-seed').disabled"), true);
    assert.equal(await evaluate("document.getElementById('direction').disabled"), true);
    await evaluate("document.getElementById('cancel').click()");
    await waitFor("generation === null && document.getElementById('status').textContent.includes('cancelled')");
    await waitFor("!state.speech_busy");
    assert.equal(await evaluate("document.getElementById('seed').disabled || document.getElementById('randomize-seed').disabled"), false);
    assert.equal(await evaluate("document.getElementById('direction').disabled"), false);
    await evaluate("document.getElementById('text').value = 'Hello again.'");
    await evaluate("document.querySelector('[data-tab=models]').click()");
    await waitFor("!document.querySelector('[data-action=unload]').disabled");
    await evaluate("document.querySelector('[data-action=unload]').click()");
    await waitFor("state.phase === 'unloaded' && state.job.status === 'complete'");
    assert.equal(await evaluate("document.getElementById('generate').disabled"), true);
    await evaluate("document.querySelector('[data-action=load][data-model=q4_k]').click()");
    await waitFor("state.models.some(m => m.id === 'q4_k' && m.loaded) && state.job.status === 'complete'");
    await evaluate("document.querySelector('[data-tab=generate]').click(); document.getElementById('direction').value = 'Speak softly, with a sad, hesitant tone.'; document.getElementById('generate').click()");
    await waitFor("!generation && document.getElementById('status').textContent.includes('Speech ready')");
    if (process.env.COMPANION_SCREENSHOTS) {
      fs.mkdirSync(process.env.COMPANION_SCREENSHOTS, {recursive: true});
      await command('Emulation.setDeviceMetricsOverride', {width: 1200, height: 950, deviceScaleFactor: 1, mobile: false});
      for (const tab of ['generate', 'models']) {
        await evaluate(`document.querySelector('[data-tab=${tab}]').click()`);
        if (tab === 'generate') await evaluate("document.getElementById('generate-provenance').open = true");
        const capture = await command('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
        fs.writeFileSync(path.join(process.env.COMPANION_SCREENSHOTS, tab + '.png'), Buffer.from(capture.data, 'base64'));
      }
    }
    assert.deepEqual(errors.filter(error => !error.includes('ERR_ABORTED')), [], 'Browser console errors');
    console.log('PASS: reference workflow and provenance, same-text voice switching, randomized/fixed seeds and persistence, delivery direction, Generate/autoplay/download, cancellation/recovery, shared model unload/load, mobile layout, reload');
  } finally {
    if (socket) socket.close();
    if (browser) { browser.kill(); await new Promise(resolve => browser.once('exit', resolve)); }
    fixture.kill();
    if (fixture.exitCode === null) await new Promise(resolve => fixture.once('exit', resolve));
    fs.rmSync(profile, {recursive: true, force: true});
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
