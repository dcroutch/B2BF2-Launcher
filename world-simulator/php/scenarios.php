<?php
require_once __DIR__ . '/models.php';

// id => [name, stability, military, economy]
const MAJOR_POWERS = [
    ['usa', 'United States', 62, 85, 90],
    ['china', 'China', 68, 80, 88],
    ['russia', 'Russia', 55, 78, 45],
    ['india', 'India', 60, 55, 62],
    ['germany', 'Germany', 70, 40, 70],
    ['uk', 'United Kingdom', 65, 50, 68],
    ['france', 'France', 62, 52, 66],
    ['japan', 'Japan', 72, 45, 72],
];

const MODERATE_POWERS = [
    ['brazil', 'Brazil', 52, 35, 50],
    ['canada', 'Canada', 72, 30, 60],
    ['australia', 'Australia', 74, 35, 58],
    ['south_korea', 'South Korea', 68, 50, 65],
    ['indonesia', 'Indonesia', 58, 30, 45],
    ['turkey', 'Turkey', 50, 55, 42],
    ['saudi_arabia', 'Saudi Arabia', 60, 50, 55],
    ['iran', 'Iran', 48, 55, 35],
    ['israel', 'Israel', 62, 65, 60],
    ['egypt', 'Egypt', 45, 40, 32],
    ['nigeria', 'Nigeria', 42, 30, 28],
    ['south_africa', 'South Africa', 50, 25, 35],
    ['mexico', 'Mexico', 55, 30, 42],
    ['pakistan', 'Pakistan', 45, 50, 30],
    ['vietnam', 'Vietnam', 60, 35, 40],
    ['poland', 'Poland', 65, 40, 48],
    ['italy', 'Italy', 58, 35, 55],
    ['spain', 'Spain', 60, 30, 52],
    ['ukraine', 'Ukraine', 40, 45, 25],
    ['argentina', 'Argentina', 48, 25, 35],
];

function default_nations_list(): array {
    return array_merge(MAJOR_POWERS, MODERATE_POWERS);
}

const NATO_BLOC = ['usa', 'uk', 'france', 'germany', 'italy', 'spain', 'poland', 'canada', 'turkey'];
const EASTERN_BLOC_RELATIONS = ['china', 'russia', 'india', 'brazil', 'south_africa'];

const SEED_RELATIONS = [
    ['usa', 'russia', -55], ['usa', 'china', -35], ['usa', 'iran', -60],
    ['usa', 'canada', 60], ['usa', 'uk', 65],
    ['china', 'japan', -20], ['china', 'india', -15], ['china', 'russia', 30],
    ['russia', 'ukraine', -70], ['russia', 'poland', -40],
    ['india', 'pakistan', -65],
    ['israel', 'iran', -75],
    ['saudi_arabia', 'iran', -50],
    ['turkey', 'israel', -20],
    ['south_korea', 'japan', 20],
    ['brazil', 'argentina', 25],
    ['egypt', 'israel', 10],
];

const SEED_EMBARGOES = [
    ['usa', 'russia'], ['usa', 'iran'], ['uk', 'russia'], ['germany', 'russia'],
];

const RESOURCE_PROFILES = [
    'saudi_arabia' => ['oil' => 140],
    'russia' => ['oil' => 120, 'energy' => 130, 'metals' => 90],
    'usa' => ['oil' => 90, 'tech_components' => 110, 'food' => 90],
    'china' => ['metals' => 110, 'tech_components' => 100, 'energy' => 70],
    'australia' => ['metals' => 130, 'food' => 90],
    'canada' => ['energy' => 100, 'food' => 100, 'metals' => 90],
    'brazil' => ['food' => 120, 'metals' => 80],
    'iran' => ['oil' => 110, 'energy' => 90],
    'nigeria' => ['oil' => 100],
    'vietnam' => ['food' => 90],
    'argentina' => ['food' => 110],
    'south_korea' => ['tech_components' => 120],
    'japan' => ['tech_components' => 130],
    'germany' => ['tech_components' => 100, 'metals' => 80],
    'india' => ['food' => 90, 'tech_components' => 80],
];

const SECTOR_PROFILES = [
    'usa' => ['technology' => 80, 'services' => 75, 'industry' => 60],
    'china' => ['industry' => 85, 'technology' => 70, 'agriculture' => 55],
    'japan' => ['technology' => 85, 'industry' => 65],
    'south_korea' => ['technology' => 80, 'industry' => 65],
    'germany' => ['industry' => 75, 'technology' => 65],
    'saudi_arabia' => ['energy_sector' => 90, 'services' => 50],
    'russia' => ['energy_sector' => 85, 'industry' => 60],
    'brazil' => ['agriculture' => 75, 'industry' => 45],
    'australia' => ['agriculture' => 65, 'industry' => 50],
    'canada' => ['agriculture' => 60, 'energy_sector' => 70],
    'india' => ['services' => 60, 'agriculture' => 55, 'technology' => 50],
    'nigeria' => ['energy_sector' => 60, 'agriculture' => 45],
    'vietnam' => ['agriculture' => 60, 'industry' => 55],
    'argentina' => ['agriculture' => 70],
];

const GOVERNMENT_PROFILES = [
    'uk' => 'parliamentary', 'germany' => 'parliamentary', 'japan' => 'parliamentary',
    'india' => 'parliamentary', 'canada' => 'parliamentary', 'australia' => 'parliamentary',
    'israel' => 'parliamentary', 'italy' => 'parliamentary', 'spain' => 'parliamentary',
    'china' => 'authoritarian', 'russia' => 'authoritarian', 'saudi_arabia' => 'authoritarian',
    'iran' => 'authoritarian', 'egypt' => 'authoritarian', 'vietnam' => 'authoritarian',
];

function list_nation_ids(): array {
    return array_column(default_nations_list(), 0);
}

function default_world(string $playerId = 'usa'): array {
    $validIds = list_nation_ids();
    if (!in_array($playerId, $validIds, true)) {
        throw new InvalidArgumentException("Unknown player_id: $playerId");
    }

    $nations = [];
    foreach (default_nations_list() as [$id, $name, $stability, $military, $economy]) {
        $n = new_nation($id, $name, [
            'stability' => (float)$stability,
            'military' => (float)$military,
            'economy' => (float)$economy,
            'is_player' => $id === $playerId,
            'government_type' => GOVERNMENT_PROFILES[$id] ?? 'democracy',
        ]);
        foreach (RESOURCE_PROFILES[$id] ?? [] as $r => $v) {
            $n['resources'][$r] = (float)$v;
        }
        foreach (SECTOR_PROFILES[$id] ?? [] as $s => $v) {
            $n['sectors'][$s] = (float)$v;
        }
        $nations[$id] = $n;
    }

    foreach (NATO_BLOC as $i => $aId) {
        for ($j = $i + 1; $j < count(NATO_BLOC); $j++) {
            $bId = NATO_BLOC[$j];
            set_add($nations[$aId]['alliances'], $bId);
            set_add($nations[$bId]['alliances'], $aId);
            $nations[$aId]['relations'][$bId] = 45;
            $nations[$bId]['relations'][$aId] = 45;
        }
    }

    foreach (EASTERN_BLOC_RELATIONS as $i => $aId) {
        for ($j = $i + 1; $j < count(EASTERN_BLOC_RELATIONS); $j++) {
            $bId = EASTERN_BLOC_RELATIONS[$j];
            $nations[$aId]['relations'][$bId] = ($nations[$aId]['relations'][$bId] ?? 0) + 20;
            $nations[$bId]['relations'][$aId] = ($nations[$bId]['relations'][$aId] ?? 0) + 20;
        }
    }

    foreach (SEED_RELATIONS as [$aId, $bId, $rel]) {
        $nations[$aId]['relations'][$bId] = $rel;
        $nations[$bId]['relations'][$aId] = $rel;
    }

    foreach (SEED_EMBARGOES as [$actorId, $targetId]) {
        set_add($nations[$actorId]['embargoes_against'], $targetId);
    }

    return new_world($nations, random_int(1, 1000000));
}
