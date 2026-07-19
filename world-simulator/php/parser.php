<?php
require_once __DIR__ . '/orders.php';
require_once __DIR__ . '/scenarios.php';

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
    ['sue_for_peace', ['sue for peace', 'cease fire', 'ceasefire', 'end the war', 'make peace', 'stop the war', 'surrender', 'surrenders', 'surrendered']],
    ['declare_war', ['declare war', 'invade', 'attack', 'wage war', 'go to war', 'bomb', 'conquer']],
    ['impose_embargo', ['embargo', 'sanction', 'blockade', 'boycott', 'surround', 'encircle']],
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
        'enact a', 'establish a', 'install a', 'institute a',
        'declare itself a', 'become a',
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
] + BACKGROUND_NATION_ALIASES;

function find_phrase(string $lowered, string $phrase): int {
    if (preg_match('/\b' . preg_quote($phrase, '/') . '\b/u', $lowered, $m, PREG_OFFSET_CAPTURE)) {
        return $m[0][1];
    }
    return -1;
}

const IRREGULAR_INFLECTIONS = [
    'go' => ['go', 'goes', 'went', 'going'],
    'become' => ['become', 'becomes', 'became', 'becoming'],
    'hold' => ['hold', 'holds', 'held', 'holding'],
];

// All the inflected forms of $word a player might plausibly type
// ("embargo" -> "embargoes"/"embargoed"/"embargoing", etc.), so a keyword
// list built around bare infinitives still matches ordinary conjugated
// phrasing ("China embargoes Russia") instead of silently falling through
// to a vague wildcard just because the player used a normal tense.
function inflections(string $word): array {
    if (isset(IRREGULAR_INFLECTIONS[$word])) {
        return IRREGULAR_INFLECTIONS[$word];
    }
    $variants = [$word, $word . 's', $word . 'es'];
    if (str_ends_with($word, 'e')) {
        $variants[] = $word . 'd';
        $variants[] = mb_substr($word, 0, -1) . 'ing';
    } else {
        $variants[] = $word . 'ed';
        $variants[] = $word . 'ing';
    }
    if (str_ends_with($word, 'y') && mb_strlen($word) > 1 && !str_contains('aeiou', mb_substr($word, -2, 1))) {
        $variants[] = mb_substr($word, 0, -1) . 'ies';
        $variants[] = mb_substr($word, 0, -1) . 'ied';
    }
    return array_unique($variants);
}

// Like find_phrase, but tolerant of the phrase's leading verb being
// conjugated -- "embargo Russia" still recognizes "embargoes Russia" /
// "embargoed Russia" / "embargoing Russia".
function find_verb(string $lowered, string $phrase): int {
    $parts = explode(' ', $phrase, 2);
    $head = $parts[0];
    $rest = isset($parts[1]) ? ' ' . $parts[1] : '';
    $best = -1;
    foreach (inflections($head) as $variant) {
        $idx = find_phrase($lowered, $variant . $rest);
        if ($idx !== -1 && ($best === -1 || $idx < $best)) {
            $best = $idx;
        }
    }
    return $best;
}

// Like find_phrase, but returns the earliest occurrence of $phrase that
// isn't a possessive mention ("Germany's collapse"). A plain first-match
// find_phrase would stop at that possessive occurrence and never see a
// later, legitimate one -- e.g. "Following France's defeat, France
// surrenders" names France twice; only the second is the real subject.
function find_phrase_non_possessive(string $lowered, string $phrase): int {
    if (!preg_match_all('/\b' . preg_quote($phrase, '/') . '\b/u', $lowered, $m, PREG_OFFSET_CAPTURE)) {
        return -1;
    }
    foreach ($m[0] as [$match, $idx]) {
        $after = mb_substr($lowered, $idx + mb_strlen($match), 2);
        if ($after === "'s" || $after === "\u{2019}s") continue;
        return $idx;
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
        $idx = find_phrase_non_possessive($lowered, $alias);
        if ($idx === -1) continue;

        if ($earliestPos === null || $idx < $earliestPos) {
            $earliestId = $nid; $earliestPos = $idx;
        }
        if ($nid !== $playerId && ($targetPos === null || $idx < $targetPos)) {
            $targetId = $nid; $targetPos = $idx;
        }
    }

    $matchedType = null; $verbPos = null;
    foreach (VERB_RULES as [$orderType, $keywords]) {
        // Take the earliest-occurring keyword in the text, not just
        // whichever one happens to be listed first -- otherwise a later
        // keyword can win even when an earlier one sits right next to the
        // actual target, wrongly placing the verb after the nation
        // mention and tripping the actor-lock guard.
        $bestIdx = null;
        foreach ($keywords as $kw) {
            $idx = find_verb($lowered, $kw);
            if ($idx !== -1 && ($bestIdx === null || $idx < $bestIdx)) {
                $bestIdx = $idx;
            }
        }
        if ($bestIdx !== null) {
            $matchedType = $orderType; $verbPos = $bestIdx;
            break;
        }
    }

    // Guard rail: the text's apparent subject is a nation other than the
    // player, mentioned before any recognized verb -- can never become a
    // real order for that nation; downgrade to a wildcard about it.
    if ($earliestId !== null && $earliestId !== $playerId && ($verbPos === null || $earliestPos < $verbPos)) {
        // $earliestId is already guaranteed to be the same nation $targetId
        // holds here: $targetId tracks the earliest non-player mention, and
        // $earliestId (non-player, per the condition above) is by
        // definition the earliest mention overall -- so it's always also
        // the earliest non-player one.
        return make_order($playerId, 'wildcard', $earliestId, $text);
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
