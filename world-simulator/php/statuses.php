<?php
/**
 * Declared statuses: player-announced national achievements ("Canadian
 * scientists unveil matter synthesis technology") and the varied, seeded-
 * random world reaction to them. Faithful port of worldsim/statuses.py --
 * see that file for the full design rationale (fully deterministic given
 * a fixed RNG seed, no AI/LLM call; category x personality x current
 * relation state x RNG jitter drives the reaction, so the same trigger
 * doesn't always produce the same outcome).
 */
require_once __DIR__ . '/orders.php';

const PERSONALITY_TYPES = ['opportunistic', 'envious', 'cautious', 'idealistic', 'isolationist', 'aggressive'];

const STATUS_CATALOG = [
    'post_scarcity_economy' => [
        'name' => 'a post-scarcity economy', 'category' => 'economic',
        'keywords' => ['post-scarcity', 'post scarcity', 'abundance economy', 'eliminate scarcity', 'end scarcity'],
        'economy' => 10, 'stability' => 4, 'opinion' => 8, 'military' => 0,
    ],
    'universal_basic_income' => [
        'name' => 'universal basic income', 'category' => 'economic',
        'keywords' => ['universal basic income', 'guaranteed income for everyone', 'basic income for all'],
        'economy' => 4, 'stability' => 5, 'opinion' => 9, 'military' => 0,
    ],
    'resource_monopoly' => [
        'name' => "a global resource monopoly", 'category' => 'economic',
        'keywords' => ['resource monopoly', 'corner the market', "control the world's resources", 'monopolize global resources'],
        'economy' => 9, 'stability' => 2, 'opinion' => 3, 'military' => 0,
    ],
    'trade_dominance' => [
        'name' => 'global trade dominance', 'category' => 'economic',
        'keywords' => ['trade dominance', 'dominate world trade', "become the world's trading hub", 'global trade empire'],
        'economy' => 8, 'stability' => 3, 'opinion' => 4, 'military' => 0,
    ],
    'currency_hegemony' => [
        'name' => 'global currency hegemony', 'category' => 'economic',
        'keywords' => ['global reserve currency', 'currency hegemony', "our currency becomes the world standard"],
        'economy' => 8, 'stability' => 2, 'opinion' => 3, 'military' => 0,
    ],
    'fusion_breakthrough' => [
        'name' => 'commercial fusion power', 'category' => 'scientific',
        'keywords' => ['fusion breakthrough', 'commercial fusion', 'fusion power online', 'cracked fusion'],
        'economy' => 7, 'stability' => 3, 'opinion' => 6, 'military' => 1,
    ],
    'ai_singularity' => [
        'name' => 'a self-improving artificial general intelligence', 'category' => 'scientific',
        'keywords' => ['ai singularity', 'artificial general intelligence', 'self-improving ai', 'the singularity'],
        'economy' => 7, 'stability' => -2, 'opinion' => 3, 'military' => 2,
    ],
    'space_program' => [
        'name' => 'a mature independent space program', 'category' => 'scientific',
        'keywords' => ['space program', 'moon landing', 'orbital colony', 'put a colony in orbit', 'reach mars'],
        'economy' => 4, 'stability' => 2, 'opinion' => 9, 'military' => 1,
    ],
    'quantum_computing_breakthrough' => [
        'name' => 'a working quantum computer', 'category' => 'scientific',
        'keywords' => ['quantum computing breakthrough', 'working quantum computer', 'quantum supremacy'],
        'economy' => 5, 'stability' => 1, 'opinion' => 4, 'military' => 1,
    ],
    'matter_synthesis' => [
        'name' => 'matter synthesis technology', 'category' => 'scientific',
        'keywords' => ['matter synthesis', 'synthesize matter', 'molecular assembler', 'replicator technology'],
        'economy' => 9, 'stability' => 3, 'opinion' => 7, 'military' => 0,
    ],
    'military_supremacy' => [
        'name' => 'overwhelming conventional military supremacy', 'category' => 'military',
        'keywords' => ['military supremacy', 'unmatched military', 'strongest military on earth', 'military dominance'],
        'economy' => 0, 'stability' => 3, 'opinion' => 2, 'military' => 10,
    ],
    'nuclear_deterrent' => [
        'name' => 'a credible nuclear deterrent', 'category' => 'military',
        'keywords' => ['nuclear deterrent', 'nuclear weapons program', 'successful nuclear test', 'go nuclear'],
        'economy' => -2, 'stability' => 4, 'opinion' => -1, 'military' => 12,
    ],
    'orbital_weapons_platform' => [
        'name' => 'an orbital weapons platform', 'category' => 'military',
        'keywords' => ['orbital weapons platform', 'weapons in orbit', 'space-based weapons', 'orbital strike capability'],
        'economy' => -1, 'stability' => 1, 'opinion' => -3, 'military' => 11,
    ],
    'elite_special_forces' => [
        'name' => 'a world-renowned special forces corps', 'category' => 'military',
        'keywords' => ['elite special forces', 'world class special forces', 'best commandos in the world'],
        'economy' => 0, 'stability' => 2, 'opinion' => 3, 'military' => 6,
    ],
    'missile_defense_shield' => [
        'name' => 'a comprehensive missile defense shield', 'category' => 'military',
        'keywords' => ['missile defense shield', 'missile shield', 'intercept any missile'],
        'economy' => -1, 'stability' => 3, 'opinion' => 4, 'military' => 8,
    ],
    'cultural_golden_age' => [
        'name' => 'a cultural golden age', 'category' => 'cultural',
        'keywords' => ['cultural golden age', 'golden age of culture', 'cultural renaissance'],
        'economy' => 3, 'stability' => 3, 'opinion' => 10, 'military' => 0,
    ],
    'global_media_dominance' => [
        'name' => 'global media and entertainment dominance', 'category' => 'cultural',
        'keywords' => ['global media dominance', 'dominate world entertainment', 'our films conquer the world'],
        'economy' => 4, 'stability' => 1, 'opinion' => 6, 'military' => 0,
    ],
    'education_revolution' => [
        'name' => 'a world-leading education system', 'category' => 'cultural',
        'keywords' => ['education revolution', 'best schools in the world', 'world leading education'],
        'economy' => 3, 'stability' => 4, 'opinion' => 8, 'military' => 0,
    ],
    'olympic_glory' => [
        'name' => 'unprecedented Olympic success', 'category' => 'cultural',
        'keywords' => ['olympic glory', 'dominate the olympics', 'sweep the olympics'],
        'economy' => 1, 'stability' => 1, 'opinion' => 9, 'military' => 0,
    ],
    'architectural_wonder' => [
        'name' => 'a new architectural wonder of the world', 'category' => 'cultural',
        'keywords' => ['architectural wonder', 'build a wonder of the world', 'tallest building in the world'],
        'economy' => 2, 'stability' => 2, 'opinion' => 7, 'military' => 0,
    ],
    'democratic_beacon' => [
        'name' => 'status as a beacon of democracy', 'category' => 'ideological',
        'keywords' => ['beacon of democracy', 'model democracy for the world', 'shining example of democracy'],
        'economy' => 1, 'stability' => 3, 'opinion' => 8, 'military' => 0,
    ],
    'revolutionary_vanguard' => [
        'name' => 'leadership of a global revolutionary movement', 'category' => 'ideological',
        'keywords' => ['revolutionary vanguard', 'export the revolution', 'lead the world revolution'],
        'economy' => -1, 'stability' => -2, 'opinion' => 7, 'military' => 2,
    ],
    'religious_awakening' => [
        'name' => 'a national religious awakening', 'category' => 'ideological',
        'keywords' => ['religious awakening', 'spiritual revival', 'national religious revival'],
        'economy' => 0, 'stability' => 4, 'opinion' => 6, 'military' => 0,
    ],
    'technocratic_utopia' => [
        'name' => 'a technocratic model society', 'category' => 'ideological',
        'keywords' => ['technocratic utopia', 'rule by technocrats', 'government run by algorithms'],
        'economy' => 3, 'stability' => -1, 'opinion' => 2, 'military' => 0,
    ],
    'disease_cure' => [
        'name' => 'a cure for a major global disease', 'category' => 'environmental',
        'keywords' => ['cure for cancer', 'cure a global disease', 'eradicate the disease', 'medical breakthrough cures'],
        'economy' => 3, 'stability' => 3, 'opinion' => 11, 'military' => 0,
    ],
    'climate_solution' => [
        'name' => 'a working large-scale climate solution', 'category' => 'environmental',
        'keywords' => ['climate solution', 'reverse climate change', 'solve global warming', 'carbon capture breakthrough'],
        'economy' => 2, 'stability' => 3, 'opinion' => 9, 'military' => 0,
    ],
    'renewable_energy_transition' => [
        'name' => 'a complete renewable energy transition', 'category' => 'environmental',
        'keywords' => ['renewable energy transition', 'fully renewable grid', '100% renewable energy'],
        'economy' => 5, 'stability' => 3, 'opinion' => 8, 'military' => 0,
    ],
    'genetic_engineering_breakthrough' => [
        'name' => 'a landmark genetic engineering breakthrough', 'category' => 'environmental',
        'keywords' => ['genetic engineering breakthrough', 'gene editing breakthrough', 'engineer the human genome'],
        'economy' => 4, 'stability' => -1, 'opinion' => 2, 'military' => 0,
    ],
];

const REACTION_TYPES = ['petition_to_join', 'attack_for_access', 'pressure_for_access', 'propose_alliance', 'propose_trade_pact', 'imitate_race', 'condemn', 'ignore'];

const CATEGORY_REACTION_AFFINITY = [
    'economic' => ['petition_to_join' => 3.0, 'pressure_for_access' => 2.5, 'propose_trade_pact' => 3.0, 'imitate_race' => 1.5, 'attack_for_access' => 1.0, 'propose_alliance' => 1.5, 'condemn' => 0.5, 'ignore' => 2.0],
    'scientific' => ['petition_to_join' => 2.5, 'pressure_for_access' => 2.5, 'propose_trade_pact' => 2.0, 'imitate_race' => 3.0, 'attack_for_access' => 1.5, 'propose_alliance' => 1.5, 'condemn' => 0.5, 'ignore' => 2.0],
    'military' => ['petition_to_join' => 1.0, 'pressure_for_access' => 1.0, 'propose_trade_pact' => 0.5, 'imitate_race' => 3.0, 'attack_for_access' => 2.0, 'propose_alliance' => 2.5, 'condemn' => 2.0, 'ignore' => 2.0],
    'cultural' => ['petition_to_join' => 2.0, 'pressure_for_access' => 0.5, 'propose_trade_pact' => 2.0, 'imitate_race' => 1.0, 'attack_for_access' => 0.3, 'propose_alliance' => 2.0, 'condemn' => 0.5, 'ignore' => 3.0],
    'ideological' => ['petition_to_join' => 1.5, 'pressure_for_access' => 0.5, 'propose_trade_pact' => 1.0, 'imitate_race' => 1.0, 'attack_for_access' => 1.0, 'propose_alliance' => 2.5, 'condemn' => 3.0, 'ignore' => 2.0],
    'environmental' => ['petition_to_join' => 2.0, 'pressure_for_access' => 1.5, 'propose_trade_pact' => 2.5, 'imitate_race' => 2.0, 'attack_for_access' => 0.5, 'propose_alliance' => 2.0, 'condemn' => 0.5, 'ignore' => 2.5],
];

const PERSONALITY_REACTION_AFFINITY = [
    'opportunistic' => ['petition_to_join' => 2.5, 'pressure_for_access' => 1.5, 'propose_trade_pact' => 2.0, 'propose_alliance' => 2.0, 'imitate_race' => 1.0, 'attack_for_access' => 1.0, 'condemn' => 0.5, 'ignore' => 0.8],
    'envious' => ['attack_for_access' => 2.5, 'pressure_for_access' => 2.0, 'condemn' => 2.0, 'petition_to_join' => 0.5, 'imitate_race' => 1.5, 'propose_trade_pact' => 0.7, 'propose_alliance' => 0.7, 'ignore' => 1.0],
    'cautious' => ['ignore' => 2.5, 'propose_trade_pact' => 1.5, 'pressure_for_access' => 1.2, 'petition_to_join' => 0.8, 'imitate_race' => 1.0, 'attack_for_access' => 0.3, 'propose_alliance' => 1.0, 'condemn' => 0.8],
    'idealistic' => ['petition_to_join' => 2.5, 'propose_alliance' => 2.5, 'condemn' => 1.5, 'propose_trade_pact' => 1.5, 'imitate_race' => 1.0, 'attack_for_access' => 0.5, 'pressure_for_access' => 0.7, 'ignore' => 0.8],
    'isolationist' => ['ignore' => 3.5, 'propose_trade_pact' => 0.7, 'pressure_for_access' => 0.5, 'petition_to_join' => 0.5, 'imitate_race' => 0.8, 'attack_for_access' => 0.4, 'propose_alliance' => 0.4, 'condemn' => 0.6],
    'aggressive' => ['attack_for_access' => 2.5, 'imitate_race' => 2.0, 'condemn' => 1.5, 'pressure_for_access' => 1.2, 'petition_to_join' => 0.4, 'propose_trade_pact' => 0.6, 'propose_alliance' => 0.8, 'ignore' => 0.8],
];

const REACTION_ROLL_CHANCE = 0.12;
const ACCESS_CONCESSION_CHANCE = 0.06;

// A rival voting to dissolve into the nation that just declared a status
// needs the same very-high mutual trust the rest of the game requires for
// any voluntary union (see propose_accession/invite_accession) -- a plain
// alliance (relation ~45) is nowhere near enough, or every NATO-bloc
// status declaration would instantly steamroll several allies.
const PETITION_RELATION_THRESHOLD = ACCESSION_RELATION_THRESHOLD;
const ATTACK_RELATION_THRESHOLD = -20.0;

const REACTION_MESSAGES = [
    'petition_to_join' => [
        "Drawn by {n}'s achievement, {r} petitions to join {n} outright.",
        "{r}'s population votes to dissolve into {n}, hoping to share in {s}.",
    ],
    'attack_for_access' => [
        "{r} declares war on {n}, determined to seize {s} by force.",
        "Unwilling to be left behind, {r} attacks {n} to claim {s} for itself.",
    ],
    'pressure_for_access' => [
        "{r} pressures {n} for access to {s}, short of a full trade embargo.",
        "{r} demands {n} share {s}, applying diplomatic pressure without cutting off trade.",
    ],
    'propose_alliance' => [
        "{r} seeks closer ties with {n}, hoping alliance brings access to {s}.",
        "{r} proposes an alliance with {n} in {s}'s wake.",
    ],
    'propose_trade_pact' => [
        "{r} opens trade talks with {n}, eager for a share of {s}.",
        "{r} proposes a trade pact with {n}, hoping to benefit from {s}.",
    ],
    'imitate_race' => [
        "{r} launches its own crash program, racing to match {n}'s {s}.",
        "Determined not to fall behind, {r} pours resources into matching {s}.",
    ],
    'condemn' => [
        "{r} publicly condemns {n} over {s}.",
        "{r}'s government denounces {n}'s {s} as a threat to the world order.",
    ],
    'ignore' => [],
];

const IMITATE_SECTOR_BY_CATEGORY = [
    'scientific' => 'technology',
    'military' => 'industry',
    'economic' => 'services',
    'environmental' => 'energy_sector',
    'cultural' => 'services',
    'ideological' => null,
];

function apply_declared_status(array &$world, string $nationId, string $statusId): void {
    $status = STATUS_CATALOG[$statusId];
    $n = &$world['nations'][$nationId];
    $n['economy'] += $status['economy'];
    $n['stability'] += $status['stability'];
    $n['public_opinion'] += $status['opinion'];
    $n['military'] += $status['military'];
    clamp_nation($n);
    set_add($n['declared_statuses'], $statusId);
}

function weighted_choice(array $weights): string {
    $total = array_sum($weights);
    $roll = (mt_rand() / mt_getrandmax()) * $total;
    $upto = 0.0;
    foreach ($weights as $k => $w) {
        $upto += $w;
        if ($roll <= $upto) return $k;
    }
    $keys = array_keys($weights);
    return $keys[count($keys) - 1];
}

function react_to_declared_statuses(array &$world): void {
    $holders = array_filter(alive_nations($world), fn($n) => !empty($n['declared_statuses']));
    foreach ($holders as $holderSnapshot) {
        $holderId = $holderSnapshot['id'];
        $statusIds = array_keys($world['nations'][$holderId]['declared_statuses']);
        foreach ($statusIds as $statusId) {
            $status = STATUS_CATALOG[$statusId];
            foreach (alive_nations($world) as $reactorSnapshot) {
                $reactorId = $reactorSnapshot['id'];
                if ($reactorId === $holderId || !empty($reactorSnapshot['is_background'])) continue;
                $key = "$statusId:$reactorId";
                if (set_has($world['nations'][$holderId]['status_reactions_done'], $key)) continue;
                if ((mt_rand() / mt_getrandmax()) >= REACTION_ROLL_CHANCE) continue;

                $holder = $world['nations'][$holderId];
                $reactor = $world['nations'][$reactorId];
                $relation = nation_relation($reactor, $holderId);

                $weights = CATEGORY_REACTION_AFFINITY[$status['category']];
                $personalityWeights = PERSONALITY_REACTION_AFFINITY[$reactor['personality']] ?? [];
                foreach ($weights as $k => $w) {
                    $weights[$k] = $w * ($personalityWeights[$k] ?? 1.0);
                }

                if ($relation < PETITION_RELATION_THRESHOLD) {
                    $weights['petition_to_join'] = 0.0;
                }
                if ($relation > ATTACK_RELATION_THRESHOLD) {
                    $weights['attack_for_access'] *= 0.15;
                }
                if ($reactor['economy'] >= $holder['economy'] && $reactor['military'] >= $holder['military']) {
                    $weights['petition_to_join'] = 0.0;
                    $weights['attack_for_access'] *= 0.2;
                }

                foreach ($weights as $k => $w) {
                    $jitter = 0.6 + (mt_rand() / mt_getrandmax()) * 0.8;
                    $weights[$k] = $w * $jitter;
                }

                $reaction = weighted_choice($weights);
                set_add($world['nations'][$holderId]['status_reactions_done'], $key);
                apply_reaction($world, $holderId, $reactorId, $statusId, $status, $reaction);
            }
        }
    }

    foreach (alive_nations($world) as $reactorSnapshot) {
        $reactorId = $reactorSnapshot['id'];
        if (empty($world['nations'][$reactorId]['access_pressure_against'])) continue;
        foreach (array_keys($world['nations'][$reactorId]['access_pressure_against']) as $holderId) {
            if (!isset($world['nations'][$holderId]) || !$world['nations'][$holderId]['alive']) {
                set_remove($world['nations'][$reactorId]['access_pressure_against'], $holderId);
                continue;
            }
            if ((mt_rand() / mt_getrandmax()) >= ACCESS_CONCESSION_CHANCE) continue;
            $holder = &$world['nations'][$holderId];
            $reactor = &$world['nations'][$reactorId];
            $transfer = min(6.0, $holder['economy'] * 0.05);
            $holder['economy'] -= $transfer;
            $reactor['economy'] += $transfer;
            clamp_nation($holder);
            clamp_nation($reactor);
            set_remove($reactor['access_pressure_against'], $holderId);
            w_log($world, "{$holder['name']} grants {$reactor['name']} limited access under sustained pressure.");
        }
    }
}

function apply_reaction(array &$world, string $holderId, string $reactorId, string $statusId, array $status, string $reaction): void {
    if ($reaction === 'ignore') return;

    $holder = $world['nations'][$holderId];
    $reactor = $world['nations'][$reactorId];
    $sname = $status['name'];
    $templates = REACTION_MESSAGES[$reaction];
    $message = fill($templates[array_rand($templates)], ['n' => $holder['name'], 'r' => $reactor['name'], 's' => $sname]);

    if ($reaction === 'petition_to_join') {
        w_log($world, $message);
        absorb_nation($world, $holderId, $reactorId, true);
        return;
    }
    if ($reaction === 'attack_for_access') {
        shift_relations($world, $reactorId, $holderId, -30.0);
        enter_war($world, $reactorId, $holderId);
        w_log($world, $message);
        return;
    }
    if ($reaction === 'pressure_for_access') {
        set_add($world['nations'][$reactorId]['access_pressure_against'], $holderId);
        shift_relations($world, $reactorId, $holderId, -8.0);
        w_log($world, $message);
        return;
    }
    if ($reaction === 'propose_alliance') {
        set_add($world['nations'][$reactorId]['alliances'], $holderId);
        set_add($world['nations'][$holderId]['alliances'], $reactorId);
        shift_relations($world, $reactorId, $holderId, 10.0);
        w_log($world, $message);
        return;
    }
    if ($reaction === 'propose_trade_pact') {
        set_add($world['nations'][$reactorId]['trade_pacts'], $holderId);
        set_add($world['nations'][$holderId]['trade_pacts'], $reactorId);
        shift_relations($world, $reactorId, $holderId, 5.0);
        w_log($world, $message);
        return;
    }
    if ($reaction === 'imitate_race') {
        $sector = IMITATE_SECTOR_BY_CATEGORY[$status['category']];
        $r = &$world['nations'][$reactorId];
        if ($sector) {
            $r['sectors'][$sector] = ($r['sectors'][$sector] ?? 40.0) + 6.0;
        } else {
            $r['military'] += 3.0;
        }
        clamp_nation($r);
        w_log($world, $message);
        return;
    }
    if ($reaction === 'condemn') {
        shift_relations($world, $reactorId, $holderId, -12.0);
        w_log($world, $message);
        return;
    }
}
