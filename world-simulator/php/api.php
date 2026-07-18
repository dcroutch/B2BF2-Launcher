<?php
/**
 * Single JSON API entry point. Uses PHP's native session handling
 * ($_SESSION) to persist a player's game state between requests -- no
 * database, no custom cookie/session-store code needed, so this runs
 * unmodified on standard cPanel/shared hosting (mod_php or PHP-FPM),
 * with sessions written to the host's default session save path.
 */
declare(strict_types=1);

require_once __DIR__ . '/engine.php';
require_once __DIR__ . '/scenarios.php';
require_once __DIR__ . '/parser.php';

session_start();
header('Content-Type: application/json');

function json_out($payload, int $status = 200): void {
    http_response_code($status);
    echo json_encode($payload);
    exit;
}

function read_json_body(): array {
    $raw = file_get_contents('php://input');
    if (!$raw) return [];
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function nation_view(array $world, string $nationId): array {
    $n = $world['nations'][$nationId];
    return [
        'id' => $n['id'],
        'name' => $n['name'],
        'is_player' => $n['is_player'],
        'alive' => $n['alive'],
        'in_power' => $n['in_power'],
        'government_type' => $n['government_type'],
        'stability' => round($n['stability'], 1),
        'military' => round($n['military'], 1),
        'economy' => round($n['economy'], 1),
        'public_opinion' => round($n['public_opinion'], 1),
        'turns_to_election' => $n['government_type'] === 'authoritarian'
            ? null
            : max($n['election_due_turn'] - $world['turn'], 0),
        'sectors' => array_map(fn($v) => round($v, 1), $n['sectors']),
        'resources' => array_map(fn($v) => round($v, 1), $n['resources']),
        'allies' => array_values(array_map(
            fn($id) => $world['nations'][$id]['name'] ?? $id,
            array_filter(set_ids($n['alliances']), fn($id) => isset($world['nations'][$id]))
        )),
        'at_war_with' => array_values(array_map(
            fn($id) => $world['nations'][$id]['name'] ?? $id,
            array_filter(set_ids($n['at_war_with']), fn($id) => isset($world['nations'][$id]))
        )),
    ];
}

function state_payload(array &$world, string $playerId, ?string $status = null, bool $ended = false, bool $advanceCursor = true): array {
    $others = [];
    foreach (alive_nations($world) as $n) {
        if ($n['id'] === $playerId) continue;
        $others[] = [
            'id' => $n['id'], 'name' => $n['name'],
            'stability' => round($n['stability'], 1),
            'military' => round($n['military'], 1),
            'economy' => round($n['economy'], 1),
        ];
    }
    usort($others, fn($a, $b) => ($b['economy'] + $b['military']) <=> ($a['economy'] + $a['military']));

    $cursor = $_SESSION['log_cursor'] ?? 0;
    $newLog = array_slice($world['event_log'], $cursor);
    if ($advanceCursor) {
        $_SESSION['log_cursor'] = count($world['event_log']);
    }

    return [
        'turn' => $world['turn'],
        'player' => nation_view($world, $playerId),
        'others' => $others,
        'log' => array_values($newLog),
        'status' => $status,
        'ended' => $ended,
    ];
}

function menu_payload(array $world, string $playerId): array {
    $options = legal_orders($world, $playerId);
    $items = [];
    foreach ($options as $i => $o) {
        if ($o['target_id']) {
            $label = "{$o['type']} -> {$world['nations'][$o['target_id']]['name']}";
        } elseif ($o['detail']) {
            $label = "{$o['type']} ({$o['detail']})";
        } else {
            $label = $o['type'];
        }
        $items[] = ['index' => $i, 'label' => $label];
    }
    return ['options' => $items];
}

$action = $_GET['action'] ?? '';
$method = $_SERVER['REQUEST_METHOD'];

if ($action === 'nations') {
    json_out(['nations' => list_nation_ids()]);
}

if ($action === 'new' && $method === 'POST') {
    $data = read_json_body();
    $playerId = $data['nation'] ?? 'usa';
    if (!in_array($playerId, list_nation_ids(), true)) {
        json_out(['error' => "unknown nation '$playerId'"], 400);
    }
    $world = default_world($playerId);
    $_SESSION['world'] = $world;
    $_SESSION['player_id'] = $playerId;
    $_SESSION['log_cursor'] = 0;
    json_out(state_payload($world, $playerId));
}

if (!isset($_SESSION['world'], $_SESSION['player_id'])) {
    json_out(['error' => 'no active game -- call action=new first'], 400);
}

$world = $_SESSION['world'];
$playerId = $_SESSION['player_id'];

if ($action === 'state' && $method === 'GET') {
    $status = game_status($world, $playerId);
    json_out(state_payload($world, $playerId, $status, false, false));
}

if ($action === 'menu' && $method === 'POST') {
    json_out(menu_payload($world, $playerId));
}

if ($action === 'order' && $method === 'POST') {
    $data = read_json_body();
    $text = trim((string)($data['text'] ?? ''));
    $index = $data['index'] ?? null;

    try {
        if ($index !== null) {
            $options = legal_orders($world, $playerId);
            if (!is_int($index) || $index < 0 || $index >= count($options)) {
                json_out(['error' => 'invalid menu index'], 400);
            }
            $order = $options[$index];
        } elseif ($text !== '') {
            $order = parse_command($world, $playerId, $text);
        } else {
            json_out(['error' => "provide 'text' or 'index'"], 400);
        }

        run_turn($world, [$order]);
    } catch (Throwable $e) {
        json_out(['error' => 'internal error resolving order'], 500);
    }

    $status = game_status($world, $playerId);
    $_SESSION['world'] = $world;
    $payload = state_payload($world, $playerId, $status);
    if ($status !== null) {
        unset($_SESSION['world'], $_SESSION['player_id'], $_SESSION['log_cursor']);
    }
    json_out($payload);
}

if ($action === 'quit' && $method === 'POST') {
    $payload = state_payload($world, $playerId, null, true);
    unset($_SESSION['world'], $_SESSION['player_id'], $_SESSION['log_cursor']);
    json_out($payload);
}

json_out(['error' => 'not found'], 404);
