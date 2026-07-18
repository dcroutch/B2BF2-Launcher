<?php
/**
 * Concert of Nations -- PHP port for shared hosting (cPanel/mod_php).
 *
 * Faithful port of the Python worldsim package's game logic. No AI/LLM,
 * no external services, no long-running process: PHP runs each request
 * on demand via the web server (Apache/LiteSpeed + mod_php or PHP-FPM),
 * which is what standard cPanel shared hosting provides out of the box --
 * no shell access, no custom ports, no Python needed.
 *
 * Nations and the World are plain associative arrays (not classes), so
 * PHP's native session serialization (session_start()/$_SESSION) can
 * persist a player's game between requests with zero extra code.
 */

const RESOURCE_TYPES = ['energy', 'food', 'metals', 'oil', 'tech_components'];
const SECTOR_TYPES = ['agriculture', 'industry', 'energy_sector', 'technology', 'services'];
const SECTOR_COMMODITY = [
    'agriculture' => 'food',
    'industry' => 'metals',
    'energy_sector' => 'energy',
    'technology' => 'tech_components',
    'services' => null,
];
const GOVERNMENT_TYPES = ['democracy', 'parliamentary', 'authoritarian'];
const ELECTED_GOVERNMENT_TYPES = ['democracy', 'parliamentary'];
const ELECTION_TERM_LENGTH = 20;

const STAT_MIN = 0.0;
const STAT_MAX = 100.0;

function clampv(float $value, float $lo = STAT_MIN, float $hi = STAT_MAX): float {
    return max($lo, min($hi, $value));
}

function new_nation(string $id, string $name, array $overrides = []): array {
    $n = [
        'id' => $id,
        'name' => $name,
        'stability' => 60.0,
        'military' => 30.0,
        'economy' => 50.0,
        'economic_potential' => null,
        'public_opinion' => 60.0,
        'sectors' => array_fill_keys(SECTOR_TYPES, 40.0),
        'resources' => array_fill_keys(RESOURCE_TYPES, 50.0),
        'relations' => [],
        'alliances' => [],
        'trade_pacts' => [],
        'embargoes_against' => [],
        'at_war_with' => [],
        'truce_until' => [],
        'government_type' => 'democracy',
        'election_due_turn' => null,
        'in_power' => true,
        'is_player' => false,
        'alive' => true,
    ];
    $n = array_merge($n, $overrides);
    if ($n['economic_potential'] === null) {
        $n['economic_potential'] = $n['economy'];
    }
    if ($n['election_due_turn'] === null) {
        $n['election_due_turn'] = ELECTION_TERM_LENGTH;
    }
    return $n;
}

function nation_relation(array $n, string $otherId): float {
    return $n['relations'][$otherId] ?? 0.0;
}

function clamp_nation(array &$n): void {
    $n['stability'] = clampv($n['stability']);
    $n['military'] = clampv($n['military']);
    $n['public_opinion'] = clampv($n['public_opinion']);
    $n['economic_potential'] = clampv($n['economic_potential']);
    $n['economy'] = clampv($n['economy'], 0.0, $n['economic_potential'] + 15.0);
    foreach (SECTOR_TYPES as $s) {
        $n['sectors'][$s] = clampv($n['sectors'][$s] ?? 0.0);
    }
    foreach (RESOURCE_TYPES as $r) {
        $n['resources'][$r] = clampv($n['resources'][$r] ?? 0.0, 0.0, 200.0);
    }
    foreach ($n['relations'] as $id => $v) {
        $n['relations'][$id] = clampv($v, -100.0, 100.0);
    }
}

// ---- World ----

function new_world(array $nations, int $seed = 0): array {
    return [
        'nations' => $nations, // id => nation array
        'turn' => 0,
        'event_log' => [],
        'market_prices' => array_fill_keys(RESOURCE_TYPES, 1.0),
        'seed' => $seed,
    ];
}

function alive_nations(array $world): array {
    return array_values(array_filter($world['nations'], fn($n) => $n['alive']));
}

function w_get(array &$world, string $id): array {
    return $world['nations'][$id];
}

function w_set(array &$world, array $n): void {
    $world['nations'][$n['id']] = $n;
}

function w_log(array &$world, string $message): void {
    $world['event_log'][] = "[T{$world['turn']}] {$message}";
}

function spawn_nation(array &$world, array $nation): void {
    $world['nations'][$nation['id']] = $nation;
}

function purge_nation_references(array &$world, string $nationId): void {
    // Sets (alliances/trade_pacts/at_war_with/embargoes_against) are
    // represented as assoc arrays keyed by nation id => true, for O(1)
    // membership checks -- see set_add()/set_has()/set_remove() below.
    foreach ($world['nations'] as $id => &$other) {
        unset($other['alliances'][$nationId]);
        unset($other['trade_pacts'][$nationId]);
        unset($other['at_war_with'][$nationId]);
        unset($other['embargoes_against'][$nationId]);
        unset($other['truce_until'][$nationId]);
    }
    unset($other);
}

// ---- Set helpers: sets are assoc arrays keyed by id => true ----

function set_add(array &$set, string $id): void {
    $set[$id] = true;
}

function set_has(array $set, string $id): bool {
    return isset($set[$id]);
}

function set_remove(array &$set, string $id): void {
    unset($set[$id]);
}

function set_ids(array $set): array {
    return array_keys($set);
}
