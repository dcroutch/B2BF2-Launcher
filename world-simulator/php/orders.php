<?php
require_once __DIR__ . '/models.php';

// Deterministically pick one of several equivalent phrasings for the same
// event, so the same kind of thing happening over and over (a trade pact,
// a sector investment, an election) doesn't read as the identical canned
// sentence every time -- without needing an RNG threaded through every
// resolver. Stable and order-dependent, unlike PHP's hash functions being
// unnecessary here -- a simple rolling sum is enough and easiest to
// reason about.
function pick_variant(array $options, ...$seedParts): string {
    if (count($options) === 1) return $options[0];
    $total = 0;
    foreach ($seedParts as $part) {
        foreach (str_split((string)$part) as $ch) {
            $total = ($total * 31 + ord($ch)) % 1000003;
        }
    }
    return $options[$total % count($options)];
}

const ORDER_TYPES = [
    'pass', 'build_military', 'invest_economy', 'invest_sector',
    'improve_relations', 'propose_alliance', 'break_alliance', 'trade_pact',
    'impose_embargo', 'declare_war', 'sue_for_peace',
    'accept_peace_offer', 'reject_peace_offer', 'annex',
    'propose_accession', 'invite_accession', 'declare_status',
    'modify_constitution', 'wildcard',
];

const TARGETED_ORDERS = [
    'improve_relations', 'propose_alliance', 'break_alliance', 'trade_pact',
    'impose_embargo', 'declare_war', 'sue_for_peace',
    'accept_peace_offer', 'reject_peace_offer', 'annex', 'propose_accession',
    'invite_accession',
];

const ORDER_PRIORITY = [
    'improve_relations' => 0, 'propose_alliance' => 0, 'break_alliance' => 0,
    'trade_pact' => 0, 'impose_embargo' => 0, 'sue_for_peace' => 0,
    'accept_peace_offer' => 0, 'reject_peace_offer' => 0,
    'propose_accession' => 0, 'invite_accession' => 0, 'declare_status' => 0, 'wildcard' => 0,
    'invest_economy' => 1, 'invest_sector' => 1, 'build_military' => 1,
    'modify_constitution' => 1,
    'declare_war' => 2, 'annex' => 2,
    'pass' => 3,
];

function make_order(string $actorId, string $type, ?string $targetId = null, ?string $detail = null): array {
    if (!in_array($type, ORDER_TYPES, true)) {
        throw new InvalidArgumentException("Unknown order type: $type");
    }
    if (in_array($type, TARGETED_ORDERS, true) && !$targetId) {
        throw new InvalidArgumentException("Order $type requires a target_id");
    }
    if ($targetId !== null && $targetId === $actorId) {
        throw new InvalidArgumentException("Order $type cannot target its own actor");
    }
    if ($type === 'invest_sector' && !in_array($detail, SECTOR_TYPES, true)) {
        throw new InvalidArgumentException('invest_sector requires a valid sector detail');
    }
    if ($type === 'modify_constitution' && !in_array($detail, GOVERNMENT_TYPES, true)) {
        throw new InvalidArgumentException('modify_constitution requires a valid government_type detail');
    }
    return ['actor_id' => $actorId, 'type' => $type, 'target_id' => $targetId, 'detail' => $detail];
}

const ALLIANCE_RELATION_THRESHOLD = 40.0;
const WAR_RELATION_HIT = -60.0;
const EMBARGO_RELATION_HIT = -20.0;
const BREAK_ALLIANCE_RELATION_HIT = -15.0;
const TRUCE_DURATION = 5;

const WAR_OPINION_HIT_JUSTIFIED = -3.0;
const WAR_OPINION_HIT_UNPROVOKED = -10.0;
const RALLY_AROUND_FLAG_OPINION_BOOST = 6.0;
const EMBARGO_RECEIVED_OPINION_HIT = -4.0;
const ALLIANCE_OPINION_BOOST = 3.0;
const PEACE_HUMILIATION_OPINION_HIT = -6.0;
const PEACE_RELIEF_OPINION_BOOST = 2.0;

const ANNEX_MILITARY_FLOOR = 15.0;
const ANNEX_DOMINANCE_RATIO = 3.0;
const ANNEX_MIN_ACTOR_MILITARY = 15.0;
const ACCESSION_RELATION_THRESHOLD = 70.0;

const ANNEX_ECONOMY_TRANSFER = 0.5;
const ANNEX_MILITARY_TRANSFER = 0.3;
const ANNEX_RESOURCE_TRANSFER = 0.5;
const ANNEX_STABILITY_HIT = -10.0;
const ANNEX_OPINION_HIT = -5.0;
const ANNEX_RIVAL_RELATION_HIT = -15.0;

const ACCESSION_ECONOMY_TRANSFER = 0.8;
const ACCESSION_MILITARY_TRANSFER = 0.8;
const ACCESSION_RESOURCE_TRANSFER = 0.8;
const ACCESSION_OPINION_BOOST = 5.0;

const CONSTITUTION_COUP_OPINION_HIT = -25.0;
const CONSTITUTION_COUP_STABILITY_HIT = -15.0;
const CONSTITUTION_COUP_RELATION_HIT = -12.0;
const CONSTITUTION_LIBERALIZATION_OPINION_BOOST = 15.0;
const CONSTITUTION_TRANSITION_STABILITY_HIT = -5.0;
const CONSTITUTION_REFORM_OPINION_DELTA = 3.0;

function is_annex_eligible(array $actor, array $target): bool {
    if ($actor['military'] < ANNEX_MIN_ACTOR_MILITARY) return false;
    return $target['military'] < ANNEX_MILITARY_FLOOR || $actor['military'] > $target['military'] * ANNEX_DOMINANCE_RATIO;
}

// Whether $actor already has some real relationship with $other -- an
// alliance, trade pact, war, embargo, or a relation score that isn't still
// at its untouched default. Used to let a background nation surface in
// legal_orders/the menu once the player has actually interacted with it,
// instead of either being permanently invisible there or bloating every
// menu with ~190 mostly irrelevant entries from turn one.
function is_engaged(array $actor, array $other): bool {
    $oid = $other['id'];
    return set_has($actor['alliances'], $oid)
        || set_has($actor['trade_pacts'], $oid)
        || set_has($actor['at_war_with'], $oid)
        || set_has($actor['embargoes_against'], $oid)
        || nation_relation($actor, $oid) !== 0.0;
}

function legal_orders(array $world, string $actorId): array {
    $actor = $world['nations'][$actorId];
    $orders = [];
    $orders[] = make_order($actorId, 'pass');
    $orders[] = make_order($actorId, 'build_military');
    $orders[] = make_order($actorId, 'invest_economy');
    foreach (SECTOR_TYPES as $sector) {
        $orders[] = make_order($actorId, 'invest_sector', null, $sector);
    }
    foreach (GOVERNMENT_TYPES as $gt) {
        if ($gt !== $actor['government_type']) {
            $orders[] = make_order($actorId, 'modify_constitution', null, $gt);
        }
    }
    foreach (alive_nations($world) as $other) {
        if ($other['id'] === $actorId) continue;
        // Background nations are real, addressable targets via free text
        // at any time, but only clutter the AI's decision space and the
        // player's numbered menu once genuinely engaged.
        if (!empty($other['is_background']) && !($actor['is_player'] && is_engaged($actor, $other))) {
            continue;
        }
        $orders[] = make_order($actorId, 'improve_relations', $other['id']);
        if (!set_has($actor['at_war_with'], $other['id'])) {
            $mutual = min(nation_relation($actor, $other['id']), nation_relation($other, $actorId));
            if (!set_has($actor['alliances'], $other['id']) && $mutual >= ALLIANCE_RELATION_THRESHOLD) {
                $orders[] = make_order($actorId, 'propose_alliance', $other['id']);
            }
            if (set_has($actor['alliances'], $other['id'])) {
                $orders[] = make_order($actorId, 'break_alliance', $other['id']);
            }
            if (!set_has($actor['trade_pacts'], $other['id']) && $mutual >= 0) {
                $orders[] = make_order($actorId, 'trade_pact', $other['id']);
            }
            if (!set_has($actor['embargoes_against'], $other['id'])) {
                $orders[] = make_order($actorId, 'impose_embargo', $other['id']);
            }
            if ($world['turn'] >= ($actor['truce_until'][$other['id']] ?? -1)) {
                $orders[] = make_order($actorId, 'declare_war', $other['id']);
            }
            if ($mutual >= ACCESSION_RELATION_THRESHOLD) {
                $orders[] = make_order($actorId, 'propose_accession', $other['id']);
                if ($actor['economy'] > $other['economy'] && $actor['military'] > $other['military']) {
                    $orders[] = make_order($actorId, 'invite_accession', $other['id']);
                }
            }
        } else {
            $orders[] = make_order($actorId, 'sue_for_peace', $other['id']);
            if (is_annex_eligible($actor, $other)) {
                $orders[] = make_order($actorId, 'annex', $other['id']);
            }
        }
    }
    foreach (array_keys($actor['pending_peace_offers']) as $offererId) {
        if (isset($world['nations'][$offererId])) {
            $orders[] = make_order($actorId, 'accept_peace_offer', $offererId);
            $orders[] = make_order($actorId, 'reject_peace_offer', $offererId);
        }
    }
    return $orders;
}

function shift_relations(array &$world, string $aId, string $bId, float $delta): void {
    $a = &$world['nations'][$aId];
    $b = &$world['nations'][$bId];
    $a['relations'][$bId] = nation_relation($a, $bId) + $delta;
    $b['relations'][$aId] = nation_relation($b, $aId) + $delta;
    clamp_nation($a);
    clamp_nation($b);
}

function enter_war(array &$world, string $aId, string $bId): void {
    $a = &$world['nations'][$aId];
    $b = &$world['nations'][$bId];
    if (set_has($a['at_war_with'], $bId)) return;
    set_remove($a['alliances'], $bId);
    set_remove($b['alliances'], $aId);
    set_remove($a['trade_pacts'], $bId);
    set_remove($b['trade_pacts'], $aId);
    set_add($a['at_war_with'], $bId);
    set_add($b['at_war_with'], $aId);
}

const RIVAL_BLOC_THRESHOLD = -30.0;
const RIVAL_BLOC_WARINESS_HIT = -3.0;
const ALLY_SOLIDARITY_RELATION_HIT = -20.0;
const ALLY_BACKING_RELATION_HIT = -15.0;
const EMBARGO_SOLIDARITY_RELATION_HIT = -8.0;

const DEFENSE_PACT_MESSAGES = [
    "{o} invokes its defense pact with {t} and joins the war against {a}.",
    "Honoring its treaty with {t}, {o} enters the war against {a}.",
    "{o} answers the call of its alliance with {t}, declaring war on {a}.",
];
const ALLY_BACKING_MESSAGES = [
    "{o} backs its ally {a} against {t}.",
    "{o} voices support for {a} in the standoff with {t}.",
    "{o} throws its diplomatic weight behind {a} against {t}.",
];

function react_third_parties(array &$world, string $actorId, string $targetId, string $event): void {
    foreach (alive_nations($world) as $other) {
        if ($other['id'] === $actorId || $other['id'] === $targetId) continue;
        $oid = $other['id'];
        if ($event === 'war') {
            if (set_has($world['nations'][$oid]['alliances'], $targetId)) {
                shift_relations($world, $oid, $actorId, ALLY_SOLIDARITY_RELATION_HIT);
                enter_war($world, $oid, $actorId);
                $tName = $world['nations'][$targetId]['name'];
                $aName = $world['nations'][$actorId]['name'];
                $oName = $world['nations'][$oid]['name'];
                w_log($world, fill(pick_variant(DEFENSE_PACT_MESSAGES, $world['turn'], $oid, $actorId), ['o' => $oName, 't' => $tName, 'a' => $aName]));
            } elseif (set_has($world['nations'][$oid]['alliances'], $actorId)) {
                shift_relations($world, $oid, $targetId, ALLY_BACKING_RELATION_HIT);
                $aName = $world['nations'][$actorId]['name'];
                $tName = $world['nations'][$targetId]['name'];
                $oName = $world['nations'][$oid]['name'];
                w_log($world, fill(pick_variant(ALLY_BACKING_MESSAGES, $world['turn'], $oid, $targetId), ['o' => $oName, 'a' => $aName, 't' => $tName]));
            }
        } elseif ($event === 'embargo') {
            if (set_has($world['nations'][$oid]['alliances'], $targetId)) {
                shift_relations($world, $oid, $actorId, EMBARGO_SOLIDARITY_RELATION_HIT);
            }
        } elseif ($event === 'alliance') {
            $o = $world['nations'][$oid];
            if (nation_relation($o, $actorId) < RIVAL_BLOC_THRESHOLD || nation_relation($o, $targetId) < RIVAL_BLOC_THRESHOLD) {
                shift_relations($world, $oid, $actorId, RIVAL_BLOC_WARINESS_HIT);
                shift_relations($world, $oid, $targetId, RIVAL_BLOC_WARINESS_HIT);
            }
        }
    }
}

function absorb_nation(array &$world, string $conquerorId, string $absorbedId, bool $peaceful): void {
    $econFrac = $peaceful ? ACCESSION_ECONOMY_TRANSFER : ANNEX_ECONOMY_TRANSFER;
    $milFrac = $peaceful ? ACCESSION_MILITARY_TRANSFER : ANNEX_MILITARY_TRANSFER;
    $resFrac = $peaceful ? ACCESSION_RESOURCE_TRANSFER : ANNEX_RESOURCE_TRANSFER;

    $conqueror = &$world['nations'][$conquerorId];
    $absorbed = $world['nations'][$absorbedId];

    $conqueror['economy'] += $absorbed['economy'] * $econFrac;
    $conqueror['economic_potential'] += $absorbed['economic_potential'] * $econFrac;
    $conqueror['military'] += $absorbed['military'] * $milFrac;
    foreach ($absorbed['resources'] as $r => $v) {
        $conqueror['resources'][$r] = ($conqueror['resources'][$r] ?? 0.0) + $v * $resFrac;
    }

    if ($peaceful) {
        $conqueror['public_opinion'] += ACCESSION_OPINION_BOOST;
    } else {
        $conqueror['stability'] += ANNEX_STABILITY_HIT;
        $conqueror['public_opinion'] += ANNEX_OPINION_HIT;
        $condemners = 0;
        foreach (alive_nations($world) as $other) {
            // Bug fix: this used to include every background nation too --
            // since ~180 of the ~190 background nations default to
            // 'democracy', any forced annexation silently set a real
            // relations entry between the conqueror and nearly every
            // background nation on Earth. is_engaged() (used to gate
            // background nations out of the menu and world-summary
            // display) treats any nonzero relation as "engaged," so this
            // permanently flooded the conqueror's own menu and world
            // summary with ~180 background nations after a single forced
            // annexation.
            if ($other['id'] === $conquerorId || $other['id'] === $absorbedId || !empty($other['is_background'])) continue;
            if (in_array($other['government_type'], ELECTED_GOVERNMENT_TYPES, true)) {
                shift_relations($world, $other['id'], $conquerorId, ANNEX_RIVAL_RELATION_HIT);
                $condemners++;
            }
        }
        if ($condemners > 0) {
            w_log($world, "The world's democracies condemn {$conqueror['name']}'s annexation of {$absorbed['name']}.");
        }
    }

    $world['nations'][$absorbedId]['alive'] = false;
    purge_nation_references($world, $absorbedId);
    clamp_nation($conqueror);
}

const PASS_MESSAGES = [
    "{a} holds steady, making no major moves this month.",
    "{a}'s government stays the course, taking no significant action.",
    "{a} spends the month on routine governance, nothing eventful.",
];
const BUILD_MILITARY_MESSAGES = [
    "{a} expands its armed forces.",
    "{a} ramps up military production.",
    "{a} funnels fresh spending into its armed forces.",
];
const BUILD_MILITARY_FULL_MESSAGES = [
    "{a}'s military is already at full strength; the buildup has nowhere to go.",
    "{a}'s armed forces are already at their peak; further spending would be wasted.",
];
const INVEST_ECONOMY_MESSAGES = [
    "{a} rolls out an economic stimulus package.",
    "{a} pours investment into its economy.",
    "{a}'s government moves to shore up its economy.",
];
const INVEST_SECTOR_MESSAGES = [
    "{a} invests in its {s} sector.",
    "{a} pours resources into developing its {s} sector.",
    "{a} announces a push to modernize its {s} sector.",
];
const IMPROVE_RELATIONS_MESSAGES = [
    "{a} extends a diplomatic overture toward {t}.",
    "{a} works to warm relations with {t}.",
    "{a} sends a goodwill delegation to {t}.",
];
const ALLIANCE_MESSAGES = [
    "{a} and {t} form an alliance.",
    "{a} and {t} sign a mutual defense pact.",
    "{a} and {t} formally align, pledging to defend one another.",
];
const ALLIANCE_REJECTED_MESSAGES = [
    "{t} isn't ready to formalize an alliance with {a} yet; relations aren't warm enough.",
    "{a}'s alliance proposal to {t} goes nowhere; trust between them still runs too thin.",
];
const BREAK_ALLIANCE_MESSAGES = [
    "{a} breaks its alliance with {t}.",
    "{a} renounces its treaty with {t}.",
    "{a} walks away from its alliance with {t}, straining ties.",
];
const TRADE_PACT_MESSAGES = [
    "{a} and {t} sign a trade pact.",
    "{a} and {t} open new trade channels.",
    "{a} and {t} strike a fresh trade agreement.",
];
const TRADE_PACT_REJECTED_MESSAGES = [
    "{t} declines {a}'s trade overture; relations are too strained for a deal right now.",
    "{a}'s trade proposal to {t} falls through amid frosty relations.",
];
const EMBARGO_MESSAGES = [
    "{a} imposes an embargo on {t}.",
    "{a} moves to economically isolate {t}.",
    "{a} cuts off trade with {t} in a new embargo.",
];
const DECLARE_WAR_MESSAGES = [
    "{a} declares war on {t}!",
    "{a} launches an offensive against {t}!",
    "War breaks out as {a} attacks {t}!",
];
const CEASEFIRE_MESSAGES = [
    "{a} and {t} agree to a ceasefire.",
    "{a} and {t} reach a truce, ending the fighting for now.",
    "Exhausted, {a} and {t} lay down arms in a ceasefire.",
];
const PEACE_REJECTED_MESSAGES = [
    "{t} presses its advantage and rejects {a}'s peace offer.",
    "{t} refuses {a}'s peace overture, sensing victory within reach.",
    "{t} presses on, spurning {a}'s bid for peace.",
];
const COUP_MESSAGES = [
    "{a} abolishes its {old} constitution and imposes {new} rule.",
    "In a sudden power grab, {a} scraps its {old} constitution for {new} rule.",
];
const LIBERALIZATION_MESSAGES = [
    "{a} adopts a {new} constitution and schedules elections.",
    "{a} turns toward {new} governance, announcing a new constitution and elections.",
];
const CONSTITUTION_REFORM_MESSAGES = [
    "{a} reforms its constitution from {old} to {new}.",
    "{a} restructures its government, moving from {old} to {new}.",
];
const ANNEX_MESSAGES = [
    "{a} annexes {t} outright, absorbing its territory and population.",
    "{a} formally annexes the defeated {t}, folding it into its own territory.",
];
const ANNEX_FAILED_MESSAGES = [
    "{a} attempts to annex {t}, but its forces haven't been crushed decisively enough.",
    "{a} presses for annexation of {t}, but the war hasn't been decided yet.",
];
const ACCESSION_REJECTED_MESSAGES = [
    "{a}'s population votes against joining {t}; ties remain close but sovereign.",
    "{a} narrowly rejects union with {t} at the ballot box, remaining independent.",
];
const ACCESSION_MESSAGES = [
    "{a} votes to join {t} in a peaceful union.",
    "{a}'s population votes to dissolve into {t} in a peaceful union.",
];
const INVITE_ACCESSION_REJECTED_MESSAGES = [
    "{t} appreciates {a}'s invitation but its population votes to remain independent.",
    "{t} declines {a}'s offer of union at the ballot box; ties stay close but sovereign.",
];
const INVITE_ACCESSION_MESSAGES = [
    "{t}'s population votes to join {a}, drawn by its prosperity and stability.",
    "{t} accepts {a}'s invitation and peacefully joins the union.",
];

function fill(string $template, array $vars): string {
    return strtr($template, array_combine(
        array_map(fn($k) => '{' . $k . '}', array_keys($vars)),
        array_values($vars)
    ));
}

function resolve_pass(array &$world, array $order): void {
    // Bug fix: this used to produce zero log output at all -- the most
    // common possible order (an empty turn, or the implicit pass used by
    // advance_turns while skipping ahead) left no trace whatsoever that
    // anything had happened, which read as the game simply ignoring the
    // player.
    $actor = &$world['nations'][$order['actor_id']];
    $actor['stability'] += 1.0;
    w_log($world, fill(pick_variant(PASS_MESSAGES, $world['turn'], $actor['id']), ['a' => $actor['name']]));
}

function resolve_build_military(array &$world, array $order): void {
    $actor = &$world['nations'][$order['actor_id']];
    $room = max(0.0, STAT_MAX - $actor['military']);
    if ($room <= 0.0) {
        w_log($world, fill(pick_variant(BUILD_MILITARY_FULL_MESSAGES, $world['turn'], $actor['id']), ['a' => $actor['name']]));
        return;
    }
    $spend = min(15.0, $actor['economy'] * 0.2, $room / 1.2);
    $actor['economy'] -= $spend;
    $actor['military'] += $spend * 1.2;
    // Bug fix: the normal (not-already-at-cap) case used to produce zero
    // log output at all, unlike every other order type.
    w_log($world, fill(pick_variant(BUILD_MILITARY_MESSAGES, $world['turn'], $actor['id']), ['a' => $actor['name']]));
}

function resolve_invest_economy(array &$world, array $order): void {
    // Bug fix: this used to produce zero log output at all -- one of the
    // most commonly issued orders left no confirmation whatsoever that it
    // had happened.
    $actor = &$world['nations'][$order['actor_id']];
    $actor['economy'] += 5.0 + ($actor['resources']['energy'] ?? 0.0) * 0.02;
    $actor['stability'] += 0.5;
    $actor['economic_potential'] += 0.6;
    w_log($world, fill(pick_variant(INVEST_ECONOMY_MESSAGES, $world['turn'], $actor['id']), ['a' => $actor['name']]));
}

function resolve_invest_sector(array &$world, array $order): void {
    $actor = &$world['nations'][$order['actor_id']];
    $sector = $order['detail'];
    // Rebalance: this used to cost up to 15% of economy per turn while
    // feeding back through a weak, heavily diluted passive drift (see
    // apply_passive_effects' avgSector term), so several turns of sector
    // investment visibly drained economy with no offsetting payoff. Also
    // raise economic_potential a little, same as invest_economy does, so
    // the passive drift-toward-potential pulls economy back up afterward.
    $cost = min(6.0, $actor['economy'] * 0.1);
    $actor['economy'] -= $cost;
    $actor['sectors'][$sector] = ($actor['sectors'][$sector] ?? 0.0) + $cost * 1.3;
    $actor['economic_potential'] += $cost * 0.4;
    $commodity = SECTOR_COMMODITY[$sector] ?? null;
    if ($commodity) {
        $actor['resources'][$commodity] = ($actor['resources'][$commodity] ?? 0.0) + 5.0;
    }
    $label = str_replace(['_sector', '_'], ['', ' '], $sector);
    w_log($world, fill(pick_variant(INVEST_SECTOR_MESSAGES, $world['turn'], $actor['id'], $sector), ['a' => $actor['name'], 's' => $label]));
}

function resolve_modify_constitution(array &$world, array $order): void {
    $actor = &$world['nations'][$order['actor_id']];
    $oldType = $actor['government_type'];
    $newType = $order['detail'];
    if ($newType === $oldType) {
        w_log($world, "{$actor['name']} reaffirms its existing $oldType constitution.");
        return;
    }
    $wasElected = in_array($oldType, ELECTED_GOVERNMENT_TYPES, true);
    $becomesElected = in_array($newType, ELECTED_GOVERNMENT_TYPES, true);

    if ($wasElected && !$becomesElected) {
        $actor['public_opinion'] += CONSTITUTION_COUP_OPINION_HIT;
        $actor['stability'] += CONSTITUTION_COUP_STABILITY_HIT;
        w_log($world, fill(pick_variant(COUP_MESSAGES, $world['turn'], $actor['id']), ['a' => $actor['name'], 'old' => $oldType, 'new' => $newType]));
        $condemners = 0;
        foreach (alive_nations($world) as $other) {
            // Bug fix: see the matching comment in absorb_nation -- this
            // used to include every background nation too, silently
            // engaging the actor with ~180 of them on every coup.
            if ($other['id'] === $actor['id'] || !empty($other['is_background'])) continue;
            if (in_array($other['government_type'], ELECTED_GOVERNMENT_TYPES, true)) {
                shift_relations($world, $other['id'], $actor['id'], CONSTITUTION_COUP_RELATION_HIT);
                $condemners++;
            }
        }
        if ($condemners > 0) {
            w_log($world, "The world's democracies condemn {$actor['name']}'s power grab.");
        }
    } elseif (!$wasElected && $becomesElected) {
        $actor['public_opinion'] += CONSTITUTION_LIBERALIZATION_OPINION_BOOST;
        $actor['stability'] += CONSTITUTION_TRANSITION_STABILITY_HIT;
        $actor['election_due_turn'] = $world['turn'] + ELECTION_TERM_LENGTH;
        w_log($world, fill(pick_variant(LIBERALIZATION_MESSAGES, $world['turn'], $actor['id']), ['a' => $actor['name'], 'new' => $newType]));
    } else {
        $actor['public_opinion'] += CONSTITUTION_REFORM_OPINION_DELTA;
        w_log($world, fill(pick_variant(CONSTITUTION_REFORM_MESSAGES, $world['turn'], $actor['id']), ['a' => $actor['name'], 'old' => $oldType, 'new' => $newType]));
    }
    $actor['government_type'] = $newType;
}

function resolve_improve_relations(array &$world, array $order): void {
    // Bug fix: this used to produce zero log output at all -- a targeted,
    // deliberate diplomatic order left no confirmation it had happened.
    $a = $order['actor_id']; $t = $order['target_id'];
    shift_relations($world, $a, $t, 8.0);
    $actorName = $world['nations'][$a]['name']; $targetName = $world['nations'][$t]['name'];
    w_log($world, fill(pick_variant(IMPROVE_RELATIONS_MESSAGES, $world['turn'], $a, $t), ['a' => $actorName, 't' => $targetName]));
}

function resolve_propose_alliance(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    $actor = $world['nations'][$a]; $target = $world['nations'][$t];
    if (nation_relation($actor, $t) >= ALLIANCE_RELATION_THRESHOLD && nation_relation($target, $a) >= ALLIANCE_RELATION_THRESHOLD) {
        set_add($world['nations'][$a]['alliances'], $t);
        set_add($world['nations'][$t]['alliances'], $a);
        $world['nations'][$a]['public_opinion'] += ALLIANCE_OPINION_BOOST;
        $world['nations'][$t]['public_opinion'] += ALLIANCE_OPINION_BOOST;
        w_log($world, fill(pick_variant(ALLIANCE_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
        react_third_parties($world, $a, $t, 'alliance');
    } else {
        w_log($world, fill(pick_variant(ALLIANCE_REJECTED_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
    }
}

function resolve_break_alliance(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    if (set_has($world['nations'][$a]['alliances'], $t)) {
        set_remove($world['nations'][$a]['alliances'], $t);
        set_remove($world['nations'][$t]['alliances'], $a);
        shift_relations($world, $a, $t, BREAK_ALLIANCE_RELATION_HIT);
        w_log($world, fill(pick_variant(BREAK_ALLIANCE_MESSAGES, $world['turn'], $a, $t), ['a' => $world['nations'][$a]['name'], 't' => $world['nations'][$t]['name']]));
    }
}

function resolve_trade_pact(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    $actor = $world['nations'][$a]; $target = $world['nations'][$t];
    if (nation_relation($actor, $t) >= 0 && nation_relation($target, $a) >= 0) {
        set_add($world['nations'][$a]['trade_pacts'], $t);
        set_add($world['nations'][$t]['trade_pacts'], $a);
        w_log($world, fill(pick_variant(TRADE_PACT_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
    } else {
        w_log($world, fill(pick_variant(TRADE_PACT_REJECTED_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
    }
}

function resolve_impose_embargo(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    set_add($world['nations'][$a]['embargoes_against'], $t);
    set_remove($world['nations'][$a]['trade_pacts'], $t);
    set_remove($world['nations'][$t]['trade_pacts'], $a);
    shift_relations($world, $a, $t, EMBARGO_RELATION_HIT);
    $world['nations'][$t]['public_opinion'] += EMBARGO_RECEIVED_OPINION_HIT;
    w_log($world, fill(pick_variant(EMBARGO_MESSAGES, $world['turn'], $a, $t), ['a' => $world['nations'][$a]['name'], 't' => $world['nations'][$t]['name']]));
    react_third_parties($world, $a, $t, 'embargo');
}

function resolve_declare_war(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    if (set_has($world['nations'][$a]['at_war_with'], $t)) return;
    $preWarHostility = nation_relation($world['nations'][$a], $t);
    enter_war($world, $a, $t);
    shift_relations($world, $a, $t, WAR_RELATION_HIT);
    $world['nations'][$a]['public_opinion'] += $preWarHostility <= -50.0 ? WAR_OPINION_HIT_JUSTIFIED : WAR_OPINION_HIT_UNPROVOKED;
    $world['nations'][$t]['public_opinion'] += RALLY_AROUND_FLAG_OPINION_BOOST;
    w_log($world, fill(pick_variant(DECLARE_WAR_MESSAGES, $world['turn'], $a, $t), ['a' => $world['nations'][$a]['name'], 't' => $world['nations'][$t]['name']]));
    react_third_parties($world, $a, $t, 'war');
}

const PEACE_OFFER_MESSAGES = [
    "{a} offers {t} a ceasefire, awaiting a response.",
    "{a} extends a bid for peace to {t}, awaiting a response.",
    "{a} signals it is ready to end the war with {t}, awaiting a response.",
];
const PEACE_ACCEPTED_BY_PLAYER_MESSAGES = [
    "{t} accepts {a}'s offer of peace; the war is over.",
    "{t} agrees to {a}'s ceasefire, ending the fighting.",
];
const PEACE_DECLINED_BY_PLAYER_MESSAGES = [
    "{t} rejects {a}'s offer of peace; the war continues.",
    "{t} declines {a}'s ceasefire and presses on with the war.",
];

function resolve_sue_for_peace(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    if (!set_has($world['nations'][$a]['at_war_with'], $t)) return;
    $actor = $world['nations'][$a]; $target = $world['nations'][$t];
    // An AI nation asking the player for peace becomes a pending offer
    // instead of an instantly auto-resolved coin flip -- see
    // resolve_accept_peace_offer/resolve_reject_peace_offer below.
    // AI-vs-AI peace, and the player's own outgoing sue_for_peace, are
    // unaffected and still resolve immediately below.
    if (!empty($target['is_player']) && empty($actor['is_player'])) {
        if (isset($world['nations'][$t]['pending_peace_offers'][$a])) return;
        $world['nations'][$t]['pending_peace_offers'][$a] = $world['turn'];
        w_log($world, fill(pick_variant(PEACE_OFFER_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
        return;
    }
    $targetDominant = $target['military'] > $actor['military'] * 1.3;
    $mutuallyExhausted = $actor['military'] < 15.0 && $target['military'] < 15.0;
    if (!$targetDominant || $mutuallyExhausted) {
        set_remove($world['nations'][$a]['at_war_with'], $t);
        set_remove($world['nations'][$t]['at_war_with'], $a);
        $world['nations'][$a]['truce_until'][$t] = $world['turn'] + TRUCE_DURATION;
        $world['nations'][$t]['truce_until'][$a] = $world['turn'] + TRUCE_DURATION;
        $losing = $actor['military'] < $target['military'] * 0.8;
        $world['nations'][$a]['public_opinion'] += $losing ? PEACE_HUMILIATION_OPINION_HIT : PEACE_RELIEF_OPINION_BOOST;
        $world['nations'][$t]['public_opinion'] += PEACE_RELIEF_OPINION_BOOST;
        w_log($world, fill(pick_variant(CEASEFIRE_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
    } else {
        w_log($world, fill(pick_variant(PEACE_REJECTED_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
    }
}

function resolve_accept_peace_offer(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id']; // a: player responding, t: offerer
    if (!isset($world['nations'][$a]['pending_peace_offers'][$t])) return;
    unset($world['nations'][$a]['pending_peace_offers'][$t]);
    if (!set_has($world['nations'][$a]['at_war_with'], $t)) return;
    set_remove($world['nations'][$a]['at_war_with'], $t);
    set_remove($world['nations'][$t]['at_war_with'], $a);
    $world['nations'][$a]['truce_until'][$t] = $world['turn'] + TRUCE_DURATION;
    $world['nations'][$t]['truce_until'][$a] = $world['turn'] + TRUCE_DURATION;
    $world['nations'][$a]['public_opinion'] += PEACE_RELIEF_OPINION_BOOST;
    $world['nations'][$t]['public_opinion'] += PEACE_RELIEF_OPINION_BOOST;
    w_log($world, fill(pick_variant(PEACE_ACCEPTED_BY_PLAYER_MESSAGES, $world['turn'], $a, $t), ['a' => $world['nations'][$t]['name'], 't' => $world['nations'][$a]['name']]));
}

function resolve_reject_peace_offer(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id']; // a: player responding, t: offerer
    if (!isset($world['nations'][$a]['pending_peace_offers'][$t])) return;
    unset($world['nations'][$a]['pending_peace_offers'][$t]);
    w_log($world, fill(pick_variant(PEACE_DECLINED_BY_PLAYER_MESSAGES, $world['turn'], $a, $t), ['a' => $world['nations'][$t]['name'], 't' => $world['nations'][$a]['name']]));
}

function resolve_annex(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    if (!set_has($world['nations'][$a]['at_war_with'], $t)) return;
    if (!is_annex_eligible($world['nations'][$a], $world['nations'][$t])) {
        w_log($world, fill(pick_variant(ANNEX_FAILED_MESSAGES, $world['turn'], $a, $t), ['a' => $world['nations'][$a]['name'], 't' => $world['nations'][$t]['name']]));
        return;
    }
    $aName = $world['nations'][$a]['name']; $tName = $world['nations'][$t]['name'];
    absorb_nation($world, $a, $t, false);
    w_log($world, fill(pick_variant(ANNEX_MESSAGES, $world['turn'], $a, $t), ['a' => $aName, 't' => $tName]));
}

function resolve_propose_accession(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    $actor = $world['nations'][$a]; $target = $world['nations'][$t];
    $mutual = min(nation_relation($actor, $t), nation_relation($target, $a));
    if ($mutual < ACCESSION_RELATION_THRESHOLD) {
        w_log($world, fill(pick_variant(ACCESSION_REJECTED_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
        return;
    }
    $aName = $actor['name']; $tName = $target['name'];
    absorb_nation($world, $t, $a, true);
    w_log($world, fill(pick_variant(ACCESSION_MESSAGES, $world['turn'], $a, $t), ['a' => $aName, 't' => $tName]));
}

const STATUS_ANNOUNCE_MESSAGES = [
    "{n} announces {s} to a stunned world.",
    "In a historic address, {n} unveils {s}.",
    "{n} formally declares {s}, and the rest of the world takes notice.",
];
const STATUS_REPEAT_MESSAGES = [
    "{n} reaffirms its position in {s} -- already old news to the rest of the world.",
];

function resolve_declare_status(array &$world, array $order): void {
    // Lazy require: statuses.php requires this file at its own top (for
    // absorb_nation/shift_relations/enter_war/ACCESSION_RELATION_THRESHOLD),
    // so requiring it back at this file's top would be circular and could
    // run into constants not defined yet depending on which file a caller
    // loads first. A function-local require sidesteps that entirely --
    // by the time this actually runs, everything is loaded either way.
    require_once __DIR__ . '/statuses.php';

    $actorId = $order['actor_id'];
    $statusId = $order['detail'];
    if (!isset(STATUS_CATALOG[$statusId])) return;
    $status = STATUS_CATALOG[$statusId];
    $actor = $world['nations'][$actorId];
    if (set_has($actor['declared_statuses'], $statusId)) {
        w_log($world, fill(pick_variant(STATUS_REPEAT_MESSAGES, $world['turn'], $actorId, $statusId), ['n' => $actor['name'], 's' => $status['name']]));
        return;
    }
    apply_declared_status($world, $actorId, $statusId);
    $actor = $world['nations'][$actorId];
    w_log($world, fill(pick_variant(STATUS_ANNOUNCE_MESSAGES, $world['turn'], $actorId, $statusId), ['n' => $actor['name'], 's' => $status['name']]));
}

function resolve_invite_accession(array &$world, array $order): void {
    $a = $order['actor_id']; $t = $order['target_id'];
    $actor = $world['nations'][$a]; $target = $world['nations'][$t];
    $mutual = min(nation_relation($actor, $t), nation_relation($target, $a));
    if ($mutual < ACCESSION_RELATION_THRESHOLD || !($actor['economy'] > $target['economy'] && $actor['military'] > $target['military'])) {
        w_log($world, fill(pick_variant(INVITE_ACCESSION_REJECTED_MESSAGES, $world['turn'], $a, $t), ['a' => $actor['name'], 't' => $target['name']]));
        return;
    }
    $aName = $actor['name']; $tName = $target['name'];
    absorb_nation($world, $a, $t, true);
    w_log($world, fill(pick_variant(INVITE_ACCESSION_MESSAGES, $world['turn'], $a, $t), ['a' => $aName, 't' => $tName]));
}

const HOSTILE_WORDS = ['demand', 'threat', 'ultimatum', 'attack', 'seize', 'annex', 'invade', 'destroy', 'refund', 'reparation', 'punish', 'conquer', 'strike', 'bomb', 'sanction', 'humiliate', 'dominate', 'reject', 'insult'];
// Regression fix: a naive alliance-seeking sentence like "let's team up
// with the UK in case anyone attacks us" used to score as an
// *extraordinary demand* (worsening relations with the exact nation the
// player wanted to befriend), purely because "attack" is a hostile word
// and nothing offset it.
const FRIENDLY_WORDS = ['gift', 'apolog', 'support', 'help', 'praise', 'honor', 'celebrate', 'thank', 'donate', 'forgive', 'welcome', 'invite', 'gratitude', 'friendship', 'congratulat', 'team up', 'join forces', 'protect', 'defend', 'partner', 'ally'];
const WILDCARD_RELATION_SCALE = -6.0;
const WILDCARD_DOMESTIC_SCALE = 1.5;
const WILDCARD_PROVOCATION_THRESHOLD = 2;

function sentiment_magnitude(string $text): int {
    $lowered = mb_strtolower($text);
    $hostile = 0; $friendly = 0;
    foreach (HOSTILE_WORDS as $w) if (str_contains($lowered, $w)) $hostile++;
    foreach (FRIENDLY_WORDS as $w) if (str_contains($lowered, $w)) $friendly++;
    return max(-3, min(3, $hostile - $friendly));
}

function resolve_wildcard(array &$world, array $order): void {
    $actor = &$world['nations'][$order['actor_id']];
    $text = trim((string)($order['detail'] ?? ''));
    $snippet = mb_strlen($text) <= 70 ? $text : mb_substr($text, 0, 67) . '...';
    $magnitude = sentiment_magnitude($text);
    $targetId = $order['target_id'];

    if ($targetId === null) {
        $actor['public_opinion'] += $magnitude * WILDCARD_DOMESTIC_SCALE;
        clamp_nation($actor);
        w_log($world, "{$actor['name']}'s government makes an unusual public statement: \"$snippet\"");
        return;
    }

    shift_relations($world, $order['actor_id'], $targetId, $magnitude * WILDCARD_RELATION_SCALE);
    $target = $world['nations'][$targetId];
    if ($magnitude > 0) {
        w_log($world, "{$actor['name']} makes an extraordinary demand of {$target['name']}: \"$snippet\"");
        w_log($world, "{$target['name']} rebuffs the demand and relations sour.");
        if ($magnitude >= WILDCARD_PROVOCATION_THRESHOLD) {
            react_third_parties($world, $order['actor_id'], $targetId, 'embargo');
            w_log($world, "{$target['name']}'s allies take note of {$actor['name']}'s provocation.");
        }
    } elseif ($magnitude < 0) {
        w_log($world, "{$actor['name']} extends an unusual goodwill gesture to {$target['name']}: \"$snippet\"");
        w_log($world, "{$target['name']} is pleasantly surprised; relations warm slightly.");
    } else {
        w_log($world, "{$actor['name']} makes a puzzling statement toward {$target['name']}: \"$snippet\"");
        w_log($world, "{$target['name']} isn't sure what to make of it.");
    }
}

const ORDER_RESOLVERS = [
    'pass' => 'resolve_pass',
    'build_military' => 'resolve_build_military',
    'invest_economy' => 'resolve_invest_economy',
    'invest_sector' => 'resolve_invest_sector',
    'modify_constitution' => 'resolve_modify_constitution',
    'improve_relations' => 'resolve_improve_relations',
    'propose_alliance' => 'resolve_propose_alliance',
    'break_alliance' => 'resolve_break_alliance',
    'trade_pact' => 'resolve_trade_pact',
    'impose_embargo' => 'resolve_impose_embargo',
    'declare_war' => 'resolve_declare_war',
    'sue_for_peace' => 'resolve_sue_for_peace',
    'accept_peace_offer' => 'resolve_accept_peace_offer',
    'reject_peace_offer' => 'resolve_reject_peace_offer',
    'annex' => 'resolve_annex',
    'propose_accession' => 'resolve_propose_accession',
    'invite_accession' => 'resolve_invite_accession',
    'declare_status' => 'resolve_declare_status',
    'wildcard' => 'resolve_wildcard',
];

function resolve_orders(array &$world, array $orders): void {
    // usort() only guarantees stability on PHP >= 8.0; tag each order with
    // its original index and break priority ties on it explicitly so
    // resolution order is deterministic on older PHP hosts too.
    $indexed = array_values($orders);
    $keyed = array_map(fn($o, $i) => [$o, $i], $indexed, array_keys($indexed));
    usort($keyed, function ($a, $b) {
        return [ORDER_PRIORITY[$a[0]['type']], $a[1]] <=> [ORDER_PRIORITY[$b[0]['type']], $b[1]];
    });
    $orders = array_map(fn($pair) => $pair[0], $keyed);
    foreach ($orders as $order) {
        $actorId = $order['actor_id'];
        if (!isset($world['nations'][$actorId]) || !$world['nations'][$actorId]['alive']) continue;
        if ($order['target_id'] !== null) {
            $t = $order['target_id'];
            if (!isset($world['nations'][$t]) || !$world['nations'][$t]['alive']) continue;
        }
        $fn = ORDER_RESOLVERS[$order['type']];
        $fn($world, $order);
        if (isset($world['nations'][$actorId])) clamp_nation($world['nations'][$actorId]);
        if ($order['target_id'] !== null && isset($world['nations'][$order['target_id']])) {
            clamp_nation($world['nations'][$order['target_id']]);
        }
    }
}
