/* Offline browser regression: NODE_PATH=<playwright node_modules> node tests/web/stream_rendering.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {})});
  const deadline = setTimeout(async () => { console.error('Rendering stalled'); await browser.close(); process.exit(1); }, 30000);
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const html = fs.readFileSync(path.join(__dirname, '../../src/sr_harness/web/static/platform.html'), 'utf8')
      .replace('pollStatus();pollEvents();pollFiles();setInterval(renderActivity,1000);', '');
    await page.route('**/*', route => route.fulfill({status: 200,
      contentType: route.request().url() === 'http://audit.test/' ? 'text/html' : 'application/json',
      body: route.request().url() === 'http://audit.test/' ? html : '{}'}));
    await page.goto('http://audit.test/');
    const result = await page.evaluate(async () => {
      const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const feed = $('data-agent-feed'); feed.hidden = false; feed.replaceChildren();
      session = {state: 'idle', data_state: 'running', data_interaction_state: 'running'};
      const emit = (kind, payload) => renderDataEvent({kind, payload, timestamp: Date.now()/1000});
      const controls = [];
      for (const interaction of ['running', 'pausing', 'interrupting', 'idle']) {
        session.data_interaction_state = interaction; renderDataAgentControl();
        controls.push({interaction, action: dataAgentControlState().action,
          stop: $('data-agent-send').classList.contains('stop'), disabled: $('data-agent-send').disabled});
      }
      // These prefixes used to leave the Markdown parser's input cursor unchanged forever.
      const partial = ['# ', '## ', '- ', '* ', '1. ', 'text\n- ', '> ', '$$', '```python\nprint(1)'];
      for (const text of partial) markdownFragment(text);
      const text = 'This looks like an oscillator, likely a Duffing-type oscillator. '.repeat(24);
      markdownModes.data = false;
      emit('assistant_delta', {response_id: 'r1', type: 'delta', turn: 7, reasoning: text});
      await frame();
      const card = dataAssistantCards.get('r1'), node = card.querySelector('.stream-reasoning');
      const width = node.getBoundingClientRect().width;
      node.scrollTop = 45;
      emit('assistant_delta', {response_id: 'r1', type: 'delta', turn: 7, reasoning: text + ' More.'});
      await frame();
      const stable = card === dataAssistantCards.get('r1') && node === card.querySelector('.stream-reasoning');
      const scrolled = node.scrollTop;
      const details = ['This', ' looks', ' like an', ' oscillator, likely', ' a Duffing-type oscillator.'];
      emit('assistant_completed', {response_id: 'r1', turn: 7, content: '',
        message: {reasoning_details: details.map(text => ({type: 'reasoning.text', text, index: 0}))}});
      await frame();
      const finalNode = feed.querySelector('.reasoning-content');
      const finalText = finalNode.textContent;
      finalNode.parentElement.classList.add('expanded'); layoutPreview(finalNode.parentElement);
      const finalWidth = finalNode.getBoundingClientRect().width;
      const beforeFailure = feed.querySelectorAll('.assistant').length;
      emit('assistant_started', {response_id: 'failed', turn: 8});
      emit('assistant_delta', {response_id: 'failed', type: 'failed', error: 'provider failure'});
      emit('assistant_failed', {response_id: 'failed', error: 'provider failure'});
      emit('execution_failed', {error: 'provider failure'});
      const failureCards = feed.querySelectorAll('.assistant').length - beforeFailure;
      const failureSpinners = feed.querySelectorAll('.stream-progress').length;
      emit('assistant_started', {response_id: 'cut', turn: 9});
      emit('assistant_delta', {response_id: 'cut', type: 'delta', content: 'Partial answer'});
      emit('assistant_completed', {response_id: 'cut', turn: 9, finish_reason: 'length',
        content: 'Partial answer', message: {content: 'Partial answer'}});
      emit('execution_completed', {finish_reason: 'length'});
      session.data_state = 'completed'; session.data_interaction_state = 'idle';
      $('data-agent-input').value = 'Continue'; renderDataAgentControl();
      return {controls, stable, scrolled, width, finalWidth, finalText,
        expectedText: details.join(''), failureSpinners, failureCards,
        spinners: feed.querySelectorAll('.stream-progress').length,
        notices: feed.querySelectorAll('.truncation-notice').length,
        canContinue: !$('data-agent-send').disabled && !$('data-agent-input').disabled};
    });
    assert.deepEqual(result.controls.map(x => x.action), ['pause', 'force_pause', null, null]);
    assert(result.controls[0].stop && result.controls[1].stop);
    assert(result.stable); assert(result.scrolled > 0);
    assert(result.width > 400 && result.finalWidth > 400);
    assert.equal(result.finalText, result.expectedText);
    assert.equal(result.failureSpinners, 0); assert.equal(result.spinners, 0);
    assert.equal(result.failureCards, 1, 'Provider failure and assistant failure duplicated a card');
    assert.equal(result.notices, 1); assert(result.canContinue);
    const lifecycle = await page.evaluate(() => {
      const event = (kind, payload) => ({kind, payload, timestamp: Date.now()/1000});
      const feed = $('feed'); feed.replaceChildren(); assistantCards.clear();
      renderDataEvent(event('assistant_started', {response_id: 'data-still-running', turn: 11}));
      renderEvent(event('assistant_started', {response_id: 'main-failed'}));
      renderEvent(event('execution_failed', {error: 'search failed'}));
      const failedSpinners = feed.querySelectorAll('.stream-progress').length;
      const scoped = dataAssistantCards.has('data-still-running') && assistantStreamStates.has('data-still-running');
      renderEvent(event('assistant_started', {response_id: 'main-completed'}));
      renderEvent(event('execution_completed', {status: 'completed'}));
      const completedSpinners = feed.querySelectorAll('.stream-progress').length;
      renderDataEvent(event('execution_completed', {}));
      return {failedSpinners, completedSpinners, scoped};
    });
    assert.equal(lifecycle.failedSpinners, 0); assert.equal(lifecycle.completedSpinners, 0);
    assert(lifecycle.scoped, "Search completion removed another agent's active stream");
    for (const viewport of [{width:1440,height:1000}, {width:768,height:900}, {width:390,height:800}]) {
      await page.setViewportSize(viewport);
      const sizes = await page.evaluate(async () => {
        markdownModes.data = true;
        const feed = $('data-agent-feed'); feed.replaceChildren(); dataAssistantCards.clear(); assistantStreamStates.clear();
        const formula = '$$\\frac{' + 'x+'.repeat(180) + '1}{1+x^2}$$';
        for (const value of ['# ', '- ', 'Some **reasoning** about $x^2$\n'+formula, '```python\n'+ 'x'.repeat(400)]) {
          renderDataEvent({kind:'assistant_delta',timestamp:Date.now()/1000,payload:{response_id:'math',turn:10,type:'delta',reasoning:value}});
          renderVisibleAgentOutput(feed.querySelector('.stream-reasoning'));
          await new Promise(resolve => requestAnimationFrame(resolve));
        }
        const node = feed.querySelector('.stream-reasoning');
        return {node:node.getBoundingClientRect().width,card:node.parentElement.getBoundingClientRect().width};
      });
      assert(sizes.node >= sizes.card - 40 && sizes.node <= sizes.card, JSON.stringify(sizes));
    }
    console.log('PASS: stop controls, incomplete Markdown, stable streaming, reasoning fragments, terminal cleanup, formula widths');
  } finally { clearTimeout(deadline); await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
