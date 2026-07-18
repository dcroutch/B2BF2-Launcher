<?php
require_once __DIR__ . '/orders.php';

/**
 * Deterministic free-text command parser -- no AI/LLM involved.
 *
 * Hard safety guarantee: every Order this returns has actor_id ===
 * $playerId. There is no code path here that can construct an Order for
 * a different nation, no matter what the input text says. If the text's
 * apparent subject is a nation other than the player, the whole
 * statement is downgraded to a wildcard rhetorical gesture *by the
 * player* about that nation, never an order carried out *by* that nation.
 */

const VERB_RULES = [
    ['annex', ['annex', 'absorb', 'annexation']],
    ['propose_accession', ['vote to join', 'accede to', 'join the union', 'unite with', 'merge into', 'petition to join']],
    ['sue_for_peace', ['sue for peace', 'cease fire', 'ceasefire', 'end the war', 'make peace', 'stop the war', 'surrender']],
    ['declare_war', ['declare war', 'invade', 'attack', 'wage war', 'go to war', 'bomb', 'conquer']],
    ['impose_embargo', ['embargo', 'sanction', 'blockade', 'boycott']],
    ['break_alliance', ['break alliance', 'break our alliance', 'betray', 'abandon our alliance', 'end alliance', 'end our alliance']],
    ['propose_alliance', ['alliance', 'ally with', 'mutual defense', 'defense pact']],
    ['trade_pact', ['trade deal', 'trade pact', 'trade agreement', 'free trade']],
    ['improve_relations', ['improve relations', 'diplomacy', 'reach out', 'extend friendship', 'make friends', 'apologize']],
    ['build_military', ['build military', 'build up the military', 'rearm', 'mobilize', 'increase defense spending', 'build army']],
    ['modify_constitution', [
        'new constitution', 'rewrite the constitution', 'constitution',
        'abolish democracy', 'impose authoritarian rule', 'declare martial law',
        'coup', 'one-party rule', 'seize absolute power', 'become a dictatorship',
        'restore democracy', 'restore parliament', 'restore parliamentary',
        'become a democracy', 'transition to democracy', 'hold free elections',
        'enacts a', 'establishes a', 'installs a', 'institutes a',
        'declares itself a', 'becomes a',
    ]],
    ['invest_sector', ['invest in', 'boost', 'develop', 'fund', 'grow the', 'subsidize']],
    ['invest_economy', ['invest', 'stimulate', 'economic stimulus', 'grow the economy']],
    ['pass', ['do nothing', 'wait', 'hold position', 'stand down']],
];

const GOVERNMENT_ALIASES = [
    'communist' => 'authoritarian', 'communism' => 'authoritarian',
    'fascist' => 'authoritarian', 'fascism' => 'authoritarian',
    'dictatorship' => 'authoritarian', 'dictator' => 'authoritarian',
    'authoritarian' => 'authoritarian', 'one-party' => 'authoritarian',
    'one party' => 'authoritarian', 'autocracy' => 'authoritarian',
    'martial law' => 'authoritarian', 'junta' => 'authoritarian',
    'democracy' => 'democracy', 'democratic' => 'democracy', 'republic' => 'democracy',
    'parliament' => 'parliamentary', 'parliamentary' => 'parliamentary',
];

const SECTOR_ALIASES = [
    'agriculture' => 'agriculture', 'farm' => 'agriculture', 'farming' => 'agriculture',
    'industry' => 'industry', 'manufacturing' => 'industry', 'factories' => 'industry',
    'energy' => 'energy_sector', 'power' => 'energy_sector', 'energy sector' => 'energy_sector',
    'technology' => 'technology', 'tech' => 'technology', 'innovation' => 'technology',
    'services' => 'services', 'finance' => 'services', 'banking' => 'services',
];

const NATION_ALIASES = [
    'usa' => ['usa', 'united states', 'america', 'u.s.', 'us'],
    'uk' => ['uk', 'united kingdom', 'britain', 'england', 'u.k.'],
    'south_korea' => ['south korea', 'korea'],
    'saudi_arabia' => ['saudi arabia', 'saudis', 'saudi'],
    'south_africa' => ['south africa'],
];

function find_phrase(string $lowered, string $phrase): int {
    if (preg_match('/\b' . preg_quote($phrase, '/') . '\b/u', $lowered, $m, PREG_OFFSET_CAPTURE)) {
        return $m[0][1];
    }
    return -1;
}

function nation_lookup(array $world): array {
    $lookup = [];
    foreach (alive_nations($world) as $n) {
        $lookup[mb_strtolower($n['name'])] = $n['id'];
        $lookup[str_replace('_', ' ', $n['id'])] = $n['id'];
        foreach (NATION_ALIASES[$n['id']] ?? [] as $alias) {
            $lookup[$alias] = $n['id'];
        }
    }
    return $lookup;
}

function find_sector(string $lowered): ?string {
    foreach (SECTOR_ALIASES as $alias => $sector) {
        if (find_phrase($lowered, $alias) !== -1) return $sector;
    }
    return null;
}

function find_government(string $lowered): ?string {
    foreach (GOVERNMENT_ALIASES as $alias => $gov) {
        if (find_phrase($lowered, $alias) !== -1) return $gov;
    }
    return null;
}

function parse_command(array $world, string $playerId, string $text): array {
    $lowered = mb_strtolower($text);
    $lookup = nation_lookup($world);

    $earliestId = null; $earliestPos = null;
    $targetId = null; $targetPos = null;
    foreach ($lookup as $alias => $nid) {
        $idx = find_phrase($lowered, $alias);
        if ($idx === -1) continue;
        // A possessive mention ("Germany's collapse") is a modifier, not
        // the sentence's subject or its intended target.
        $after = mb_substr($lowered, $idx + mb_strlen($alias), 2);
        if ($after === "'s" || $after === "\u{2019}s") continue;

        if ($earliestPos === null || $idx < $earliestPos) {
            $earliestId = $nid; $earliestPos = $idx;
        }
        if ($nid !== $playerId && ($targetPos === null || $idx < $targetPos)) {
            $targetId = $nid; $targetPos = $idx;
        }
    }

    $matchedType = null; $verbPos = null;
    foreach (VERB_RULES as [$orderType, $keywords]) {
        foreach ($keywords as $kw) {
            $idx = find_phrase($lowered, $kw);
            if ($idx !== -1) {
                $matchedType = $orderType; $verbPos = $idx;
                break;
            }
        }
        if ($matchedType !== null) break;
    }

    // Guard rail: the text's apparent subject is a nation other than the
    // player, mentioned before any recognized verb -- can never become a
    // real order for that nation; downgrade to a wildcard about it.
    if ($earliestId !== null && $earliestId !== $playerId && ($verbPos === null || $earliestPos < $verbPos)) {
        $wildcardTarget = ($targetId !== null && $targetId !== $earliestId) ? $targetId : $earliestId;
        return make_order($playerId, 'wildcard', $wildcardTarget, $text);
    }

    if ($matchedType === 'invest_sector') {
        $sector = find_sector($lowered);
        if ($sector === null) $matchedType = 'invest_economy';
    }

    if ($matchedType === 'modify_constitution') {
        $gov = find_government($lowered);
        if ($gov === null) {
            return make_order($playerId, 'wildcard', $targetId, $text);
        }
        return make_order($playerId, 'modify_constitution', null, $gov);
    }

    if ($matchedType === null) {
        return make_order($playerId, 'wildcard', $targetId, $text);
    }

    if ($matchedType === 'invest_sector') {
        return make_order($playerId, 'invest_sector', null, find_sector($lowered));
    }

    if (in_array($matchedType, TARGETED_ORDERS, true)) {
        if ($targetId === null) {
            return make_order($playerId, 'wildcard', null, $text);
        }
        return make_order($playerId, $matchedType, $targetId);
    }

    return make_order($playerId, $matchedType);
}
