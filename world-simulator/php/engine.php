<?php
require_once __DIR__ . '/ai.php';
require_once __DIR__ . '/statuses.php';

const WAR_STABILITY_DRAIN = 2.0;
const WAR_MILITARY_DRAIN = 1.5;
const COLLAPSE_STABILITY = 0.0;

const ELECTION_WIN_OPINION_THRESHOLD = 50.0;
const NO_CONFIDENCE_OPINION_THRESHOLD = 15.0;
const NO_CONFIDENCE_STABILITY_THRESHOLD = 25.0;
const NEW_ADMINISTRATION_OPINION = 55.0;

// Equivalent phrasings for the same kind of event, so frequent occurrences
// (an election, a minor event, a rebel fracture) don't always read as the
// identical canned sentence. See orders.php's pick_variant().
const REELECTED_MESSAGES = [
    "{n} holds elections; the incumbent government is re-elected.",
    "{n} goes to the polls; voters return the incumbent government to power.",
    "{n}'s government wins another term in a scheduled election.",
];
const VOTED_OUT_MESSAGES = [
    "{n} holds elections; the incumbent government is voted out of office.",
    "{n} goes to the polls; voters oust the incumbent government.",
    "{n}'s government loses power in a scheduled election.",
];
const NEW_ADMINISTRATION_MESSAGES = [
    "A new administration takes power in {n}.",
    "{n} swears in a new government.",
    "A fresh administration takes the reins in {n}.",
];
const MINOR_EVENT_MESSAGE_TEMPLATES = [
    "{n} experiences {e}.",
    "{n} is affected by {e}.",
    "Reports from {n} describe {e}.",
];
const CIVIL_WAR_MESSAGES = [
    "{n} fractures under the strain: a rebel faction breaks away and declares independence!",
    "Unable to hold together, {n} splinters as a rebel faction declares independence!",
    "{n} descends into civil war as a breakaway faction declares independence!",
];
const COLLAPSE_ANNEX_MESSAGES = [
    "{c} annexes the collapsed {n} amid war.",
    "As {n} collapses, {c} moves in to absorb the wreckage.",
    "{n}'s government falls apart mid-war, and {c} annexes what remains.",
];
const COLLAPSE_MESSAGES = [
    "{n} collapses into instability and exits the world stage.",
    "{n}'s government disintegrates entirely, and the state ceases to function.",
    "{n} implodes under its own instability, its government gone.",
];

const MARKET_PRICE_ADJUST_RATE = 0.1;
const MARKET_PRICE_MIN = 0.5;
const MARKET_PRICE_MAX = 2.0;
const MARKET_ECONOMY_SENSITIVITY = 0.01;
// The "neutral" resource level the market-surplus formula treats as
// neither a windfall nor a squeeze -- also the ceiling resources passively
// regenerate up to (see apply_passive_effects).
const RESOURCE_BASELINE = 50.0;

const SUSTAINED_EMBARGO_THRESHOLD = 10;
const SUSTAINED_EMBARGO_POTENTIAL_DRAIN = 0.05;

const PEACE_OFFER_EXPIRY_TURNS = 5;

const CIVIL_WAR_STABILITY_THRESHOLD = 15.0;
const CIVIL_WAR_OPINION_THRESHOLD = 20.0;
const CIVIL_WAR_CHANCE_PER_TURN = 0.12;
const CIVIL_WAR_SPLIT_FRACTION = 0.3;
const CIVIL_WAR_STABILITY_SHOCK = -10.0;
const CIVIL_WAR_OPINION_SHOCK = -5.0;

// name => [resource-delta ranges, stability-delta range, opinion-delta range]
const POSITIVE_EVENTS = [
    ['bumper_harvest', ['food' => [5.0, 15.0]], [1.0, 4.0], [1.0, 4.0]],
    ['oil_discovery', ['oil' => [8.0, 20.0]], [0.0, 2.0], [1.0, 4.0]],
    ['rare_metals_strike', ['metals' => [6.0, 16.0]], [0.0, 2.0], [1.0, 3.0]],
    ['tech_breakthrough', ['tech_components' => [6.0, 16.0]], [0.0, 2.0], [1.0, 4.0]],
    ['cultural_festival', [], [1.0, 4.0], [2.0, 5.0]],
];
const NEUTRAL_EVENTS = [
    ['drought', ['food' => [-15.0, -5.0]], [-4.0, -1.0], [-3.0, -1.0]],
];
const UNREST_EVENTS = [
    ['civil_unrest', [], [-9.0, -4.0], [-11.0, -5.0]],
    ['corruption_scandal', [], [-4.0, -1.0], [-10.0, -4.0]],
];
const BASE_EVENT_CHANCE = 0.06;
const STRUGGLING_EVENT_CHANCE_BONUS = 0.05;
const UNREST_STABILITY_THRESHOLD = 40.0;
const UNREST_OPINION_THRESHOLD = 40.0;

function rand_uniform(float $lo, float $hi): float {
    return $lo + (mt_rand() / mt_getrandmax()) * ($hi - $lo);
}

function run_turn(array &$world, array $playerOrders): void {
    $allOrders = $playerOrders;
    foreach (alive_nations($world) as $nation) {
        // Background nations are real, addressable targets but never take
        // their own AI-chosen actions.
        if ($nation['is_player'] || !empty($nation['is_background'])) continue;
        $allOrders[] = choose_order($world, $nation['id']);
    }
    resolve_orders($world, $allOrders);
    apply_passive_effects($world);
    update_market_prices($world);
    resolve_elections($world);
    check_collapses($world);
    react_to_declared_statuses($world);
    expire_stale_peace_offers($world);
    $world['turn'] += 1;
}

function apply_passive_effects(array &$world): void {
    $alive = alive_nations($world);
    $aliveIds = array_column($alive, 'id');
    $embargoersByTarget = [];
    foreach ($alive as $nation) {
        foreach (set_ids($nation['embargoes_against']) as $targetId) {
            $embargoersByTarget[$targetId] = ($embargoersByTarget[$targetId] ?? 0) + 1;
        }
    }

    foreach ($alive as $nationSnapshot) {
        $id = $nationSnapshot['id'];
        if (!isset($world['nations'][$id])) continue;
        $nation = &$world['nations'][$id];

        $warCount = count($nation['at_war_with']);
        if ($warCount > 0) {
            $nation['stability'] -= WAR_STABILITY_DRAIN * $warCount;
            $nation['military'] -= WAR_MILITARY_DRAIN * $warCount;
            $nation['economy'] -= 1.0 * $warCount;
            $nation['public_opinion'] -= 1.5 * $warCount;
        }

        $embargoCount = $embargoersByTarget[$id] ?? 0;
        $nation['economy'] -= 1.5 * $embargoCount;
        $nation['public_opinion'] -= 1.0 * $embargoCount;
        // A sustained embargo leaves lasting damage -- past a threshold
        // of consecutive embargoed turns, start eroding economic_potential
        // itself, not just the day-to-day economy stat (see the matching
        // comment in worldsim/engine.py).
        if ($embargoCount > 0) {
            $nation['turns_embargoed'] += 1;
            if ($nation['turns_embargoed'] > SUSTAINED_EMBARGO_THRESHOLD) {
                $nation['economic_potential'] -= SUSTAINED_EMBARGO_POTENTIAL_DRAIN * $embargoCount;
            }
        } else {
            $nation['turns_embargoed'] = 0;
        }

        $activeTradePacts = array_intersect(set_ids($nation['trade_pacts']), $aliveIds);
        $nation['economy'] += 0.5 * count($activeTradePacts);

        foreach (RESOURCE_TYPES as $r) {
            $surplus = ($nation['resources'][$r] ?? 0.0) - RESOURCE_BASELINE;
            $pricePressure = ($world['market_prices'][$r] ?? 1.0) - 1.0;
            $nation['economy'] += $surplus * $pricePressure * MARKET_ECONOMY_SENSITIVITY;
        }

        $avgSector = array_sum(array_map(fn($s) => $nation['sectors'][$s] ?? 40.0, SECTOR_TYPES)) / count(SECTOR_TYPES);
        $nation['economy'] += ($avgSector - 40.0) * 0.08;

        $nation['economy'] += ($nation['economic_potential'] - $nation['economy']) * 0.05;

        $targetOpinion = 50 + ($nation['stability'] - 50) * 0.3 + ($nation['economy'] - $nation['economic_potential']) * 0.3;
        $nation['public_opinion'] += ($targetOpinion - $nation['public_opinion']) * 0.05;

        $targetStability = 40 + $nation['economy'] * 0.3 + ($nation['public_opinion'] - 50) * 0.15;
        $nation['stability'] += ($targetStability - $nation['stability']) * 0.05;

        foreach (array_keys($nation['relations']) as $otherId) {
            if (set_has($nation['at_war_with'], $otherId)) continue;
            $nation['relations'][$otherId] += (0 - $nation['relations'][$otherId]) * 0.02;
        }

        // Resources regenerate slowly if depleted, only up to the neutral
        // baseline, and only while not embargoed -- see the matching
        // comment in worldsim/engine.py for the runaway-collapse bug this
        // fixes (previously a flat +1.0/turn forever with no ceiling and
        // no embargo check).
        if (($embargoersByTarget[$id] ?? 0) === 0) {
            foreach (RESOURCE_TYPES as $r) {
                $current = $nation['resources'][$r] ?? 0.0;
                if ($current < RESOURCE_BASELINE) {
                    $nation['resources'][$r] = min(RESOURCE_BASELINE, $current + 1.0);
                }
            }
        }

        maybe_trigger_minor_event($world, $id);

        clamp_nation($world['nations'][$id]);
        maybe_trigger_civil_war($world, $id);
    }
}

function maybe_trigger_minor_event(array &$world, string $nationId): void {
    $nation = $world['nations'][$nationId];
    $struggling = $nation['stability'] < UNREST_STABILITY_THRESHOLD || $nation['public_opinion'] < UNREST_OPINION_THRESHOLD;
    $chance = BASE_EVENT_CHANCE + ($struggling ? STRUGGLING_EVENT_CHANCE_BONUS : 0.0);
    if ((mt_rand() / mt_getrandmax()) >= $chance) return;

    $pool = array_merge(POSITIVE_EVENTS, NEUTRAL_EVENTS);
    if ($struggling) $pool = array_merge($pool, UNREST_EVENTS);
    [$name, $resourceRanges, $stabilityRange, $opinionRange] = $pool[array_rand($pool)];

    $n = &$world['nations'][$nationId];
    $n['stability'] += rand_uniform($stabilityRange[0], $stabilityRange[1]);
    $n['public_opinion'] += rand_uniform($opinionRange[0], $opinionRange[1]);
    foreach ($resourceRanges as $r => [$lo, $hi]) {
        $n['resources'][$r] = ($n['resources'][$r] ?? 0.0) + rand_uniform($lo, $hi);
    }
    $label = str_replace('_', ' ', $name);
    w_log($world, fill(pick_variant(MINOR_EVENT_MESSAGE_TEMPLATES, $world['turn'], $nationId, $name), ['n' => $n['name'], 'e' => $label]));
}

function maybe_trigger_civil_war(array &$world, string $nationId): void {
    $nation = $world['nations'][$nationId];
    if ($nation['stability'] >= CIVIL_WAR_STABILITY_THRESHOLD || $nation['public_opinion'] >= CIVIL_WAR_OPINION_THRESHOLD) return;
    if ((mt_rand() / mt_getrandmax()) >= CIVIL_WAR_CHANCE_PER_TURN) return;

    $rebelId = "{$nationId}_rebels_t{$world['turn']}_" . substr(md5(uniqid('', true)), 0, 6);
    $n = &$world['nations'][$nationId];
    $rebels = new_nation($rebelId, "{$n['name']} Rebel Faction", [
        'stability' => 40.0,
        'military' => $n['military'] * CIVIL_WAR_SPLIT_FRACTION,
        'economy' => $n['economy'] * CIVIL_WAR_SPLIT_FRACTION,
        'public_opinion' => 50.0,
        'government_type' => 'authoritarian',
        'election_due_turn' => $world['turn'] + ELECTION_TERM_LENGTH,
    ]);
    foreach (RESOURCE_TYPES as $r) {
        $rebels['resources'][$r] = ($n['resources'][$r] ?? 0.0) * CIVIL_WAR_SPLIT_FRACTION;
        $n['resources'][$r] = ($n['resources'][$r] ?? 0.0) * (1 - CIVIL_WAR_SPLIT_FRACTION);
    }
    $n['military'] *= (1 - CIVIL_WAR_SPLIT_FRACTION);
    $n['economy'] *= (1 - CIVIL_WAR_SPLIT_FRACTION);
    $n['stability'] += CIVIL_WAR_STABILITY_SHOCK;
    $n['public_opinion'] += CIVIL_WAR_OPINION_SHOCK;

    set_add($rebels['at_war_with'], $nationId);
    set_add($n['at_war_with'], $rebelId);
    clamp_nation($rebels);
    clamp_nation($n);
    spawn_nation($world, $rebels);
    w_log($world, fill(pick_variant(CIVIL_WAR_MESSAGES, $world['turn'], $nationId), ['n' => $n['name']]));
}

function update_market_prices(array &$world): void {
    $alive = alive_nations($world);
    if (!$alive) return;
    $baselineTotal = 50.0 * count($alive);
    foreach (RESOURCE_TYPES as $r) {
        $totalStock = array_sum(array_map(fn($n) => $n['resources'][$r] ?? 0.0, $alive));
        $targetPrice = $totalStock > 0 ? $baselineTotal / $totalStock : MARKET_PRICE_MAX;
        $targetPrice = max(MARKET_PRICE_MIN, min(MARKET_PRICE_MAX, $targetPrice));
        $current = $world['market_prices'][$r] ?? 1.0;
        $world['market_prices'][$r] = $current + ($targetPrice - $current) * MARKET_PRICE_ADJUST_RATE;
    }
}

function resolve_elections(array &$world): void {
    foreach (alive_nations($world) as $nationSnap) {
        $id = $nationSnap['id'];
        $nation = $world['nations'][$id];
        if ($nation['government_type'] === 'authoritarian' || !empty($nation['is_background'])) continue;
        if ($world['turn'] >= $nation['election_due_turn']) {
            hold_election($world, $id);
        } elseif (
            $nation['government_type'] === 'parliamentary'
            && $nation['public_opinion'] < NO_CONFIDENCE_OPINION_THRESHOLD
            && $nation['stability'] < NO_CONFIDENCE_STABILITY_THRESHOLD
        ) {
            w_log($world, "{$nation['name']}'s parliament passes a vote of no confidence, collapsing the government.");
            oust_leader($world, $id);
        }
    }
}

function hold_election(array &$world, string $nationId): void {
    $nation = &$world['nations'][$nationId];
    if ($nation['public_opinion'] >= ELECTION_WIN_OPINION_THRESHOLD) {
        $nation['election_due_turn'] = $world['turn'] + ELECTION_TERM_LENGTH;
        $nation['public_opinion'] = min(100.0, $nation['public_opinion'] + 3.0);
        w_log($world, fill(pick_variant(REELECTED_MESSAGES, $world['turn'], $nationId), ['n' => $nation['name']]));
    } else {
        w_log($world, fill(pick_variant(VOTED_OUT_MESSAGES, $world['turn'], $nationId), ['n' => $nation['name']]));
        oust_leader($world, $nationId);
    }
}

function oust_leader(array &$world, string $nationId): void {
    $nation = &$world['nations'][$nationId];
    if ($nation['is_player']) {
        $nation['in_power'] = false;
    } else {
        $nation['public_opinion'] = NEW_ADMINISTRATION_OPINION;
        $nation['election_due_turn'] = $world['turn'] + ELECTION_TERM_LENGTH;
        w_log($world, fill(pick_variant(NEW_ADMINISTRATION_MESSAGES, $world['turn'], $nationId), ['n' => $nation['name']]));
    }
}

function check_collapses(array &$world): void {
    foreach (alive_nations($world) as $nationSnap) {
        $id = $nationSnap['id'];
        if (!isset($world['nations'][$id]) || !$world['nations'][$id]['alive']) continue;
        $nation = $world['nations'][$id];
        if ($nation['stability'] > COLLAPSE_STABILITY) continue;

        if (count($nation['at_war_with']) > 0) {
            $conquerorId = null; $bestMil = -1.0;
            foreach (set_ids($nation['at_war_with']) as $eid) {
                if (!isset($world['nations'][$eid])) continue;
                $mil = $world['nations'][$eid]['military'];
                if ($mil > $bestMil || ($mil === $bestMil && ($conquerorId === null || $eid < $conquerorId))) {
                    $bestMil = $mil; $conquerorId = $eid;
                }
            }
            if ($conquerorId !== null && $world['nations'][$conquerorId]['alive']) {
                $collapsedName = $nation['name'];
                $conquerorName = $world['nations'][$conquerorId]['name'];
                absorb_nation($world, $conquerorId, $id, false);
                w_log($world, fill(pick_variant(COLLAPSE_ANNEX_MESSAGES, $world['turn'], $conquerorId, $id), ['c' => $conquerorName, 'n' => $collapsedName]));
                continue;
            }
        }

        $world['nations'][$id]['alive'] = false;
        purge_nation_references($world, $id);
        w_log($world, fill(pick_variant(COLLAPSE_MESSAGES, $world['turn'], $id), ['n' => $nation['name']]));
    }
}

function expire_stale_peace_offers(array &$world): void {
    foreach (alive_nations($world) as $nationSnapshot) {
        $id = $nationSnapshot['id'];
        if (empty($world['nations'][$id]['pending_peace_offers'])) continue;
        foreach ($world['nations'][$id]['pending_peace_offers'] as $offererId => $offeredTurn) {
            if ($world['turn'] - $offeredTurn <= PEACE_OFFER_EXPIRY_TURNS) continue;
            unset($world['nations'][$id]['pending_peace_offers'][$offererId]);
            $offerer = $world['nations'][$offererId] ?? null;
            if ($offerer !== null && $offerer['alive']) {
                w_log($world, "{$offerer['name']}'s offer of peace with {$world['nations'][$id]['name']} goes unanswered and expires; the war continues.");
            }
        }
    }
}

function game_status(array $world, string $playerId): ?string {
    $player = $world['nations'][$playerId];
    if (!$player['alive']) return 'loss';
    if (!$player['in_power']) return 'loss';
    // Domination only requires eliminating the other nations the game
    // actually simulates as active rivals -- background reference states
    // never act and were never part of "every other nation" in spirit;
    // counting all ~190 of them would make domination unreachable.
    $aliveMain = array_values(array_filter($world['nations'], fn($n) => $n['alive'] && empty($n['is_background'])));
    if (count($aliveMain) === 1 && $aliveMain[0]['id'] === $playerId) return 'win';
    return null;
}

// One turn represents one month. Purely a labeling/UI concept -- nothing
// in the engine's math depends on it.
const TURN_LENGTH_MONTHS = 1;

// Resolve $playerOrders (the player may submit several at once, e.g.
// "invest in energy" + "embargo Russia" in the same turn) on the first
// turn, then run $numTurns - 1 further turns with no further player
// input -- an implicit pass -- so the player can skip ahead several
// months at once instead of being stopped for input every single turn.
// Returns every event_log line produced across all the turns advanced;
// stops early the moment game_status stops being null, since there's no
// point simulating further turns once the game has ended.
function advance_turns(array &$world, string $playerId, array $playerOrders, int $numTurns): array {
    $startCursor = count($world['event_log']);
    run_turn($world, $playerOrders);
    for ($i = 0; $i < max(0, $numTurns - 1); $i++) {
        if (game_status($world, $playerId) !== null) break;
        run_turn($world, [make_order($playerId, 'pass')]);
    }
    return array_slice($world['event_log'], $startCursor);
}
