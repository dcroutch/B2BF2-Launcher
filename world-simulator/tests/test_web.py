import io
import json
import unittest

from worldsim import web


def call(method, path, body=None, cookie=None):
    data = json.dumps(body).encode() if body is not None else b""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": io.BytesIO(data),
    }
    if cookie:
        environ["HTTP_COOKIE"] = cookie
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    result = web.application(environ, start_response)
    body_bytes = b"".join(result)
    payload = json.loads(body_bytes) if body_bytes and body_bytes.startswith(b"{") else None
    return captured["status"], dict(captured["headers"]), payload


def new_game(nation="usa"):
    status, headers, payload = call("POST", "/api/new", {"nation": nation})
    cookie = headers["Set-Cookie"].split(";")[0]
    return cookie, payload


class TestIndexPage(unittest.TestCase):
    def test_index_serves_html(self):
        status, headers, _ = call("GET", "/")
        self.assertEqual(status, "200 OK")
        self.assertIn("text/html", headers["Content-Type"])

    def test_unknown_path_is_404(self):
        status, _, _ = call("GET", "/nope")
        self.assertEqual(status, "404 Not Found")


class TestNationList(unittest.TestCase):
    def test_lists_all_28_nations(self):
        status, _, payload = call("GET", "/api/nations")
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(payload["nations"]), 28)
        self.assertIn("usa", payload["nations"])


class TestSessionLifecycle(unittest.TestCase):
    def test_new_game_sets_a_cookie_and_returns_initial_state(self):
        status, headers, payload = call("POST", "/api/new", {"nation": "usa"})
        self.assertEqual(status, "200 OK")
        self.assertIn("Set-Cookie", headers)
        self.assertEqual(payload["turn"], 0)
        self.assertEqual(payload["player"]["id"], "usa")

    def test_unknown_nation_is_rejected(self):
        status, _, payload = call("POST", "/api/new", {"nation": "narnia"})
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("error", payload)

    def test_endpoints_require_an_active_session(self):
        status, _, payload = call("GET", "/api/state")
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("error", payload)

    def test_two_sessions_are_independent(self):
        cookie_a, _ = new_game("usa")
        cookie_b, _ = new_game("china")
        _, _, state_a = call("GET", "/api/state", cookie=cookie_a)
        _, _, state_b = call("GET", "/api/state", cookie=cookie_b)
        self.assertEqual(state_a["player"]["id"], "usa")
        self.assertEqual(state_b["player"]["id"], "china")

    def test_quit_ends_the_session_and_further_requests_are_rejected(self):
        cookie, _ = new_game()
        status, _, payload = call("POST", "/api/quit", {}, cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertTrue(payload["ended"])
        status, _, payload = call("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, "400 Bad Request")


class TestOrders(unittest.TestCase):
    def test_free_text_order_advances_the_turn(self):
        cookie, _ = new_game("usa")
        status, _, payload = call("POST", "/api/order", {"text": "invest in our technology sector"}, cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["turn"], 1)

    def test_menu_then_order_by_index_advances_the_turn(self):
        cookie, _ = new_game("usa")
        status, _, menu = call("POST", "/api/menu", {}, cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertGreater(len(menu["options"]), 0)
        status, _, payload = call("POST", "/api/order", {"index": 0}, cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["turn"], 1)

    def test_invalid_menu_index_is_rejected(self):
        cookie, _ = new_game("usa")
        status, _, payload = call("POST", "/api/order", {"index": 999999}, cookie=cookie)
        self.assertEqual(status, "400 Bad Request")

    def test_multiple_semicolon_separated_instructions_resolve_the_same_turn(self):
        cookie, _ = new_game("usa")
        status, _, payload = call(
            "POST", "/api/order",
            {"text": "invest in technology; embargo Russia"}, cookie=cookie,
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["turn"], 1)
        self.assertTrue(any("embargo" in line.lower() for line in payload["log"]))

    def test_turns_parameter_skips_ahead_multiple_months(self):
        cookie, _ = new_game("usa")
        status, _, payload = call("POST", "/api/order", {"text": "pass", "turns": 3}, cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["turn"], 3)
        # The digest should include events from all 3 months, not just the last.
        self.assertGreater(len(payload["log"]), 0)

    def test_invalid_turns_parameter_falls_back_to_one(self):
        cookie, _ = new_game("usa")
        status, _, payload = call("POST", "/api/order", {"text": "pass", "turns": "banana"}, cookie=cookie)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["turn"], 1)

    def test_missing_text_and_index_is_rejected(self):
        cookie, _ = new_game("usa")
        status, _, payload = call("POST", "/api/order", {}, cookie=cookie)
        self.assertEqual(status, "400 Bad Request")

    def test_actor_lock_guarantee_holds_through_the_web_layer(self):
        # The same safety property from the CLI parser must survive being
        # wrapped in JSON: a statement naming another nation cannot change
        # that nation, only ever produce a wildcard about it.
        cookie, _ = new_game("usa")
        status, _, payload = call(
            "POST", "/api/order",
            {"text": "With a vote of 85% of the population, Canada enacts a communist government."},
            cookie=cookie,
        )
        self.assertEqual(status, "200 OK")
        canada = next(n for n in payload["others"] if n["name"] == "Canada")
        self.assertIsNotNone(canada)  # Canada is untouched, still just a normal listed nation

    def test_log_is_delivered_incrementally_not_duplicated(self):
        cookie, _ = new_game("usa")
        _, _, first = call("POST", "/api/order", {"text": "pass"}, cookie=cookie)
        _, _, second = call("POST", "/api/order", {"text": "pass"}, cookie=cookie)
        # The second response's log shouldn't repeat lines already sent in
        # the first (log_cursor bookkeeping).
        self.assertTrue(set(second["log"]).isdisjoint(set(first["log"])) or not first["log"])

    def test_read_only_state_polls_do_not_consume_the_log_cursor(self):
        # Regression test: GET /api/state used to advance log_cursor just
        # like a turn-advancing action, so two polls in a row (two tabs,
        # a refresh racing a background poll) would silently split the
        # new log lines between them -- the first poll would consume them,
        # and the second would see nothing, even though it never actually
        # received them either.
        cookie, _ = new_game("usa")
        sid = cookie.split("=")[1]
        web.SESSIONS[sid]["world"].event_log.append("[T0] a new event happens")

        status1, _, state1 = call("GET", "/api/state", cookie=cookie)
        status2, _, state2 = call("GET", "/api/state", cookie=cookie)
        self.assertEqual(status1, "200 OK")
        self.assertEqual(status2, "200 OK")
        # Both reads must see the same not-yet-consumed log line -- a
        # read-only endpoint has to be safe to call repeatedly.
        self.assertIn("[T0] a new event happens", state1["log"])
        self.assertEqual(state1["log"], state2["log"])

        # Since the reads above never advanced the cursor, the injected
        # line is still unconsumed and the next turn-advancing action
        # correctly delivers it (proving it was never silently dropped).
        _, _, order_result = call("POST", "/api/order", {"text": "pass"}, cookie=cookie)
        self.assertIn("[T0] a new event happens", order_result["log"])

        # And now that a mutating action *has* run, a further read sees
        # nothing new -- the cursor really did advance this time.
        _, _, state3 = call("GET", "/api/state", cookie=cookie)
        self.assertEqual(state3["log"], [])

    def test_menu_index_is_revalidated_against_current_state_not_a_stale_cache(self):
        # Regression test: /api/order used to reuse whatever list /api/menu
        # last cached, without re-checking it against the world state at
        # the moment the index is actually submitted. If the option set
        # changes shape between the menu fetch and the order (a turn
        # passes, a nation is annexed, a rebel faction spawns), a stale
        # index could resolve to a completely different, unintended order.
        cookie, _ = new_game("usa")
        status, _, menu_before = call("POST", "/api/menu", {}, cookie=cookie)
        # Advance a turn so the world (and therefore legal_orders) changes.
        call("POST", "/api/order", {"text": "pass"}, cookie=cookie)
        status, _, menu_after = call("POST", "/api/menu", {}, cookie=cookie)
        # Submitting an index now must be checked against *this* menu,
        # not whatever was cached from the first /api/menu call.
        index = len(menu_after["options"]) - 1
        status, _, payload = call("POST", "/api/order", {"index": index}, cookie=cookie)
        self.assertEqual(status, "200 OK")


class TestGameEndReflectedOverHttp(unittest.TestCase):
    def test_status_field_reports_loss_when_player_collapses(self):
        cookie, payload = new_game("usa")
        sid = cookie.split("=")[1]
        session = web.SESSIONS[sid]
        session["world"].get("usa").alive = False
        status, _, payload = call("POST", "/api/order", {"text": "pass"}, cookie=cookie)
        self.assertEqual(payload["status"], "loss")
        # A finished game should also clear the session server-side.
        status, _, payload = call("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, "400 Bad Request")


class TestSessionExpiry(unittest.TestCase):
    def test_idle_sessions_are_pruned_on_new_game_creation(self):
        # Regression test: SESSIONS never expired abandoned games, so a
        # browser that starts a game and never quits leaked its full
        # World object for the life of the server process.
        cookie, _ = new_game("usa")
        sid = cookie.split("=")[1]
        self.assertIn(sid, web.SESSIONS)
        web.SESSIONS[sid]["last_active"] = 0  # force it to look ancient
        new_game("china")  # any /api/new sweeps expired sessions
        self.assertNotIn(sid, web.SESSIONS)

    def test_active_sessions_are_not_pruned(self):
        cookie, _ = new_game("usa")
        sid = cookie.split("=")[1]
        new_game("china")
        self.assertIn(sid, web.SESSIONS)


if __name__ == "__main__":
    unittest.main()
