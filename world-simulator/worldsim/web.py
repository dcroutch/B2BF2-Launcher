"""A small stdlib-only web server for Concert of Nations.

No external dependencies (no Flask/Django) and no AI/LLM: this is a thin
JSON API (built on wsgiref, the standard library's WSGI server) in front
of the exact same deterministic worldsim.engine/orders/parser used by the
CLI, plus a single embedded HTML/CSS/JS page. Game state lives server-side
per browser session (an httponly cookie), so multiple people can each
play their own game against the same server process.
"""
from __future__ import annotations

import json
import random
import secrets
import time
from http.cookies import SimpleCookie
from wsgiref.simple_server import make_server

from .engine import TURN_LENGTH_MONTHS, advance_turns, game_status
from .models import World
from .orders import is_engaged, legal_orders
from .parser import parse_commands
from .scenarios import default_world, list_nation_ids

SESSION_COOKIE = "con_sid"

# A browser that starts a game and never quits (closes the tab, walks away)
# would otherwise leak its full World object -- 28+ Nations, a growing
# event log, potentially more nations from civil-war spawns -- for the
# life of the server process. Sessions untouched this long are swept.
SESSION_IDLE_TIMEOUT_SECONDS = 2 * 60 * 60

# sid -> {"world": World, "rng": Random, "player_id": str, "log_cursor": int,
#         "last_active": float}
SESSIONS: dict = {}


def _prune_expired_sessions() -> None:
    cutoff = time.time() - SESSION_IDLE_TIMEOUT_SECONDS
    expired = [sid for sid, s in SESSIONS.items() if s.get("last_active", 0) < cutoff]
    for sid in expired:
        SESSIONS.pop(sid, None)


def _new_session_id() -> str:
    return secrets.token_urlsafe(24)


def _nation_view(world: World, nation_id: str) -> dict:
    n = world.get(nation_id)
    return {
        "id": n.id,
        "name": n.name,
        "is_player": n.is_player,
        "alive": n.alive,
        "in_power": n.in_power,
        "government_type": n.government_type,
        "stability": round(n.stability, 1),
        "military": round(n.military, 1),
        "economy": round(n.economy, 1),
        "public_opinion": round(n.public_opinion, 1),
        "turns_to_election": (
            None if n.government_type == "authoritarian" else max(n.election_due_turn - world.turn, 0)
        ),
        "sectors": {k: round(v, 1) for k, v in n.sectors.items()},
        "resources": {k: round(v, 1) for k, v in n.resources.items()},
        "allies": sorted(world.get(a).name for a in n.alliances if a in world.nations),
        "at_war_with": sorted(world.get(w).name for w in n.at_war_with if w in world.nations),
    }


def _state_payload(session: dict, status=None, ended: bool = False, advance_cursor: bool = True) -> dict:
    """Build the JSON state payload. advance_cursor=False (used by the
    read-only GET /api/state) returns the log lines since the last
    *advancing* call without consuming them -- otherwise two polls in
    quick succession (two tabs on one session, a refresh racing a
    background poll) would each see only half the new log lines, since
    the first poll would have already moved the cursor past them."""
    world = session["world"]
    player_id = session["player_id"]
    player = world.get(player_id)
    others = [
        {"id": n.id, "name": n.name, "stability": round(n.stability, 1),
         "military": round(n.military, 1), "economy": round(n.economy, 1)}
        for n in sorted(world.alive_nations(), key=lambda n: -(n.economy + n.military))
        # Background nations only show up here once actually engaged --
        # otherwise this list would include ~190 mostly-untouched
        # reference states every single turn.
        if n.id != player_id and not (n.is_background and not is_engaged(player, n))
    ]
    cursor = session.get("log_cursor", 0)
    new_log = world.event_log[cursor:]
    if advance_cursor:
        session["log_cursor"] = len(world.event_log)
    return {
        "turn": world.turn,
        "player": _nation_view(world, player_id),
        "others": others,
        "log": new_log,
        "status": status,
        "ended": ended,
    }


def _menu_payload(session: dict) -> dict:
    world = session["world"]
    options = list(legal_orders(world, session["player_id"]))
    items = []
    for i, order in enumerate(options):
        if order.target_id:
            label = f"{order.type} -> {world.get(order.target_id).name}"
        elif order.detail:
            label = f"{order.type} ({order.detail})"
        else:
            label = order.type
        items.append({"index": i, "label": label})
    return {"options": items}


def _sid_from_cookie(environ) -> str:
    cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else ""


def _get_session(environ) -> dict | None:
    sid = _sid_from_cookie(environ)
    return SESSIONS.get(sid) if sid else None


def _read_json_body(environ) -> dict:
    try:
        length = int(environ.get("CONTENT_LENGTH", 0) or 0)
    except ValueError:
        length = 0
    if length == 0:
        return {}
    raw = environ["wsgi.input"].read(length)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _json_response(start_response, payload: dict, status: str = "200 OK", set_cookie: str | None = None):
    body = json.dumps(payload).encode("utf-8")
    headers = [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
    if set_cookie:
        headers.append(("Set-Cookie", f"{SESSION_COOKIE}={set_cookie}; HttpOnly; Path=/; SameSite=Lax"))
    start_response(status, headers)
    return [body]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    if method == "GET" and path == "/":
        body = INDEX_HTML.encode("utf-8")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    if method == "GET" and path == "/api/nations":
        return _json_response(start_response, {"nations": list_nation_ids()})

    if method == "POST" and path == "/api/new":
        _prune_expired_sessions()
        data = _read_json_body(environ)
        player_id = data.get("nation", "usa")
        if player_id not in list_nation_ids():
            return _json_response(start_response, {"error": f"unknown nation '{player_id}'"}, "400 Bad Request")
        sid = _new_session_id()
        seed = secrets.randbelow(1_000_000)
        world = default_world(player_id=player_id, seed=seed)
        SESSIONS[sid] = {
            "world": world,
            "rng": random.Random(seed),
            "player_id": player_id,
            "log_cursor": 0,
            "last_active": time.time(),
        }
        payload = _state_payload(SESSIONS[sid])
        return _json_response(start_response, payload, set_cookie=sid)

    session_required_routes = {
        ("GET", "/api/state"),
        ("POST", "/api/menu"),
        ("POST", "/api/order"),
        ("POST", "/api/quit"),
    }
    if (method, path) not in session_required_routes:
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]

    session = _get_session(environ)
    if session is None:
        return _json_response(start_response, {"error": "no active game -- call /api/new first"}, "400 Bad Request")
    session["last_active"] = time.time()

    if method == "GET" and path == "/api/state":
        world = session["world"]
        status = game_status(world, session["player_id"])
        return _json_response(start_response, _state_payload(session, status=status, advance_cursor=False))

    if method == "POST" and path == "/api/menu":
        return _json_response(start_response, _menu_payload(session))

    if method == "POST" and path == "/api/order":
        data = _read_json_body(environ)
        world, player_id, rng = session["world"], session["player_id"], session["rng"]
        text = str(data.get("text", "")).strip()
        index = data.get("index")
        turns = data.get("turns", 1)
        if not isinstance(turns, int) or turns < 1:
            turns = 1
        if index is not None:
            # Always recompute fresh against the current world state --
            # caching this across requests risks resolving a stale index
            # against a roster that's since changed (a nation annexed, a
            # civil-war rebel spawned), silently applying the wrong order.
            options = list(legal_orders(world, player_id))
            if not isinstance(index, int) or not (0 <= index < len(options)):
                return _json_response(start_response, {"error": "invalid menu index"}, "400 Bad Request")
            orders = [options[index]]
        elif text:
            # A single submission can hold several instructions for the
            # same turn ("invest in energy; embargo Russia").
            orders = parse_commands(world, player_id, text)
        else:
            return _json_response(start_response, {"error": "provide 'text' or 'index'"}, "400 Bad Request")

        advance_turns(world, player_id, orders, turns, rng)
        status = game_status(world, player_id)
        payload = _state_payload(session, status=status)
        if status is not None:
            SESSIONS.pop(_sid_from_cookie(environ), None)
        return _json_response(start_response, payload)

    if method == "POST" and path == "/api/quit":
        payload = _state_payload(session, ended=True)
        SESSIONS.pop(_sid_from_cookie(environ), None)
        return _json_response(start_response, payload)

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"not found"]


INDEX_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Concert of Nations</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
  h1 { margin-bottom: 0.2rem; }
  .sub { opacity: 0.7; margin-top: 0; }
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
<h1>Concert of Nations</h1>
<p class="sub">A deterministic, offline geopolitical strategy sim — no AI/LLM. No turn cap: play until you win, lose, or quit. Each turn represents one month.</p>

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
async function api(path, body) {
  const opts = { method: body === undefined ? 'GET' : 'POST', headers: {}, credentials: 'same-origin' };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  return res.json();
}

const setupEl = document.getElementById('setup');
const gameEl = document.getElementById('game');

async function loadNations() {
  const data = await api('/api/nations');
  const sel = document.getElementById('nationSelect');
  sel.innerHTML = data.nations.map(n => `<option value="${n}">${n}</option>`).join('');
  sel.value = 'usa';
}

document.getElementById('startBtn').onclick = async () => {
  const nation = document.getElementById('nationSelect').value;
  const state = await api('/api/new', { nation });
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
  const state = await api('/api/order', { text, turns });
  render(state);
}

document.getElementById('menuBtn').onclick = async () => {
  const data = await api('/api/menu', {});
  const list = document.getElementById('menuList');
  list.innerHTML = data.options.map(o => `<button data-i="${o.index}">${o.label}</button>`).join('');
  list.querySelectorAll('button').forEach(btn => {
    btn.onclick = async () => {
      list.innerHTML = '';
      const turns = parseInt(document.getElementById('skipTurns').value, 10);
      const state = await api('/api/order', { index: parseInt(btn.dataset.i, 10), turns });
      render(state);
    };
  });
};

document.getElementById('quitBtn').onclick = async () => {
  const state = await api('/api/quit', {});
  render(state);
  document.getElementById('orderRow').style.display = 'none';
  document.getElementById('menuBtn').style.display = 'none';
};

function render(state) {
  if (state.error) { alert(state.error); return; }
  const p = state.player;
  document.getElementById('turnHeader').textContent =
    `Month ${state.turn} — ${p.name} (${p.government_type})`;

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
"""


def main() -> None:
    port = 8000
    print(f"Concert of Nations web server running at http://127.0.0.1:{port}/")
    print("No AI/LLM involved -- pure deterministic Python, served over stdlib wsgiref.")
    with make_server("127.0.0.1", port, application) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
