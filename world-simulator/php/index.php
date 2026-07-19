<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>World Sim</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
  h1 { margin-bottom: 0.2rem; }
  #intro { max-width: 640px; }
  #intro h2 { font-size: 1.05rem; margin-bottom: 0.3rem; }
  #intro p { line-height: 1.5; }
  #intro ul { line-height: 1.5; padding-left: 1.2rem; }
  #setup, #game { display: none; }
  #setup.active, #game.active { display: block; }
  select, input[type=text], button { font-size: 1rem; padding: 0.5rem; }
  button { cursor: pointer; }
  #stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.5rem; margin: 1rem 0; }
  .stat { border: 1px solid #8884; border-radius: 8px; padding: 0.5rem; text-align: center; }
  .stat .label { font-size: 0.75rem; opacity: 0.7; }
  .stat .value { font-size: 1.3rem; font-weight: 600; }
  #log { border: 1px solid #8884; border-radius: 8px; padding: 0.75rem; height: 220px; overflow-y: auto; font-family: monospace; font-size: 0.85rem; margin: 1rem 0; }
  #log div { margin-bottom: 2px; }
  #others { border: 1px solid #8884; border-radius: 8px; padding: 0.75rem; margin: 1rem 0; font-size: 0.85rem; }
  #orderRow { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0; align-items: flex-start; }
  #orderText { flex: 1; min-width: 240px; font-family: inherit; resize: vertical; }
  #skipLabel { font-size: 0.85rem; display: flex; flex-direction: column; gap: 0.2rem; }
  #menuList { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0; }
  #menuList button { font-size: 0.8rem; padding: 0.3rem 0.6rem; }
  #verdict { font-size: 1.4rem; font-weight: 700; text-align: center; padding: 1rem; }
  .win { color: #2a2; } .loss { color: #c33; } .ended { color: #886; }
</style>
</head>
<body>
<h1>World Sim</h1>

<div id="intro">
  <p>World Sim is a turn based strategy game where you run a nation on the world stage. There is no AI text generation behind it. Every reaction comes from a fixed set of rules, so the same choices always lead to the same outcome.</p>
  <p>Pick a nation, then tell it what to do each turn in plain language. The other nations act too, driven by the same rules, so the world keeps moving whether or not you're paying close attention.</p>

  <h2>How a turn works</h2>
  <p>Each turn represents one month. Type an instruction like "invest in technology" or "declare war on Russia" and send it. You can queue up several instructions at once by separating them with a semicolon or a new line. Use the skip option if you'd rather advance a few months without issuing new orders.</p>
  <p>Prefer picking from a list instead of typing? Use the Menu button for a set of ready made actions you can choose by number.</p>

  <h2>Tips</h2>
  <ul>
    <li>You only ever control your own nation. If you write about another country's leader or army, your government reacts to what you said rather than controlling that country.</li>
    <li>Watch stability and public opinion closely. A government that loses too much support can be voted out or collapse outright, and that ends the game.</li>
    <li>War is costly. Declaring one drains your economy and military over time, so make sure you can actually finish what you start.</li>
    <li>Alliances matter. Attacking an allied nation can drag its whole defense pact into the fight against you.</li>
    <li>There's no turn limit. Keep playing as long as you like, or use Quit whenever you're done.</li>
  </ul>
</div>

<div id="setup" class="active">
  <label>Choose your nation:
    <select id="nationSelect"></select>
  </label>
  <button id="startBtn">Start</button>
</div>

<div id="game">
  <h2 id="turnHeader"></h2>
  <div id="stats"></div>
  <div id="others"></div>
  <div id="log"></div>
  <div id="orderRow">
    <textarea id="orderText" rows="2" placeholder="What does your nation do? Separate multiple instructions with ';' or a new line, e.g. 'invest in technology; embargo Russia'"></textarea>
    <label id="skipLabel">Skip ahead
      <select id="skipTurns">
        <option value="1" selected>1 month</option>
        <option value="3">3 months</option>
        <option value="6">6 months</option>
      </select>
    </label>
    <button id="sendBtn">Send</button>
    <button id="menuBtn">Menu</button>
    <button id="quitBtn">Quit</button>
  </div>
  <div id="menuList"></div>
  <div id="verdict"></div>
</div>

<script>
async function api(action, body, method) {
  const opts = { method: method || (body === undefined ? 'GET' : 'POST'), headers: {}, credentials: 'same-origin' };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('api.php?action=' + action, opts);
  return res.json();
}

const setupEl = document.getElementById('setup');
const gameEl = document.getElementById('game');

async function loadNations() {
  const data = await api('nations');
  const sel = document.getElementById('nationSelect');
  sel.innerHTML = data.nations.map(n => `<option value="${n}">${n}</option>`).join('');
  sel.value = 'usa';
}

document.getElementById('startBtn').onclick = async () => {
  const nation = document.getElementById('nationSelect').value;
  const state = await api('new', { nation });
  setupEl.classList.remove('active');
  gameEl.classList.add('active');
  render(state);
};

document.getElementById('sendBtn').onclick = () => sendOrder();
// Enter submits; Shift+Enter inserts a newline (for a second instruction).
document.getElementById('orderText').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendOrder(); }
});

async function sendOrder() {
  const text = document.getElementById('orderText').value.trim();
  if (!text) return;
  const turns = parseInt(document.getElementById('skipTurns').value, 10);
  document.getElementById('orderText').value = '';
  document.getElementById('menuList').innerHTML = '';
  const state = await api('order', { text, turns });
  render(state);
}

document.getElementById('menuBtn').onclick = async () => {
  const data = await api('menu', {});
  const list = document.getElementById('menuList');
  list.innerHTML = data.options.map(o => `<button data-i="${o.index}">${o.label}</button>`).join('');
  list.querySelectorAll('button').forEach(btn => {
    btn.onclick = async () => {
      list.innerHTML = '';
      const turns = parseInt(document.getElementById('skipTurns').value, 10);
      const state = await api('order', { index: parseInt(btn.dataset.i, 10), turns });
      render(state);
    };
  });
};

document.getElementById('quitBtn').onclick = async () => {
  const state = await api('quit', {});
  render(state);
  document.getElementById('orderRow').style.display = 'none';
  document.getElementById('menuBtn').style.display = 'none';
};

function render(state) {
  if (state.error) { alert(state.error); return; }
  const p = state.player;
  document.getElementById('turnHeader').textContent =
    `Month ${state.turn}: ${p.name} (${p.government_type})`;

  const electionText = p.turns_to_election === null ? 'no elections (authoritarian)'
    : `next election in ${p.turns_to_election} month(s)`;

  document.getElementById('stats').innerHTML = `
    <div class="stat"><div class="label">Stability</div><div class="value">${p.stability}</div></div>
    <div class="stat"><div class="label">Military</div><div class="value">${p.military}</div></div>
    <div class="stat"><div class="label">Economy</div><div class="value">${p.economy}</div></div>
    <div class="stat"><div class="label">Public opinion</div><div class="value">${p.public_opinion}</div></div>
    <div class="stat"><div class="label">Election</div><div class="value" style="font-size:0.9rem">${electionText}</div></div>
    <div class="stat"><div class="label">Allies</div><div class="value" style="font-size:0.9rem">${p.allies.length}</div></div>
    <div class="stat"><div class="label">At war</div><div class="value" style="font-size:0.9rem">${p.at_war_with.length}</div></div>
  `;

  document.getElementById('others').innerHTML = '<strong>World:</strong> ' +
    state.others.map(n => `${n.name} (stab ${n.stability}/mil ${n.military}/econ ${n.economy})`).join(', ');

  const log = document.getElementById('log');
  state.log.forEach(line => {
    const div = document.createElement('div');
    div.textContent = line;
    log.appendChild(div);
  });
  log.scrollTop = log.scrollHeight;

  const verdict = document.getElementById('verdict');
  if (state.status === 'win') { verdict.textContent = 'VICTORY'; verdict.className = 'win'; }
  else if (state.status === 'loss') { verdict.textContent = 'DEFEAT'; verdict.className = 'loss'; }
  else if (state.ended) { verdict.textContent = 'GAME ENDED'; verdict.className = 'ended'; }
  else { verdict.textContent = ''; verdict.className = ''; }

  if (state.status || state.ended) {
    document.getElementById('orderRow').style.display = 'none';
    document.getElementById('menuBtn').style.display = 'none';
  }
}

loadNations();
</script>
</body>
</html>
