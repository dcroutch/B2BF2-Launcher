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

// Every other UN member state (plus Taiwan), added as background
// nations -- see models.php's new_nation() 'is_background' doc comment.
const BACKGROUND_NATIONS = [
    ['algeria', 'Algeria'],
    ['angola', 'Angola'],
    ['benin', 'Benin'],
    ['botswana', 'Botswana'],
    ['burkina_faso', 'Burkina Faso'],
    ['burundi', 'Burundi'],
    ['cabo_verde', 'Cabo Verde'],
    ['cameroon', 'Cameroon'],
    ['central_african_republic', 'Central African Republic'],
    ['chad', 'Chad'],
    ['comoros', 'Comoros'],
    ['congo_republic', 'Republic of the Congo'],
    ['congo_dr', 'Democratic Republic of the Congo'],
    ['djibouti', 'Djibouti'],
    ['equatorial_guinea', 'Equatorial Guinea'],
    ['eritrea', 'Eritrea'],
    ['eswatini', 'Eswatini'],
    ['ethiopia', 'Ethiopia'],
    ['gabon', 'Gabon'],
    ['gambia', 'Gambia'],
    ['ghana', 'Ghana'],
    ['guinea', 'Guinea'],
    ['guinea_bissau', 'Guinea-Bissau'],
    ['ivory_coast', 'Ivory Coast'],
    ['kenya', 'Kenya'],
    ['lesotho', 'Lesotho'],
    ['liberia', 'Liberia'],
    ['libya', 'Libya'],
    ['madagascar', 'Madagascar'],
    ['malawi', 'Malawi'],
    ['mali', 'Mali'],
    ['mauritania', 'Mauritania'],
    ['mauritius', 'Mauritius'],
    ['morocco', 'Morocco'],
    ['mozambique', 'Mozambique'],
    ['namibia', 'Namibia'],
    ['niger', 'Niger'],
    ['rwanda', 'Rwanda'],
    ['sao_tome_and_principe', 'Sao Tome and Principe'],
    ['senegal', 'Senegal'],
    ['seychelles', 'Seychelles'],
    ['sierra_leone', 'Sierra Leone'],
    ['somalia', 'Somalia'],
    ['south_sudan', 'South Sudan'],
    ['sudan', 'Sudan'],
    ['tanzania', 'Tanzania'],
    ['togo', 'Togo'],
    ['tunisia', 'Tunisia'],
    ['uganda', 'Uganda'],
    ['zambia', 'Zambia'],
    ['zimbabwe', 'Zimbabwe'],
    ['antigua_and_barbuda', 'Antigua and Barbuda'],
    ['bahamas', 'Bahamas'],
    ['barbados', 'Barbados'],
    ['belize', 'Belize'],
    ['bolivia', 'Bolivia'],
    ['chile', 'Chile'],
    ['colombia', 'Colombia'],
    ['costa_rica', 'Costa Rica'],
    ['cuba', 'Cuba'],
    ['dominica', 'Dominica'],
    ['dominican_republic', 'Dominican Republic'],
    ['ecuador', 'Ecuador'],
    ['el_salvador', 'El Salvador'],
    ['grenada', 'Grenada'],
    ['guatemala', 'Guatemala'],
    ['guyana', 'Guyana'],
    ['haiti', 'Haiti'],
    ['honduras', 'Honduras'],
    ['jamaica', 'Jamaica'],
    ['nicaragua', 'Nicaragua'],
    ['panama', 'Panama'],
    ['paraguay', 'Paraguay'],
    ['peru', 'Peru'],
    ['saint_kitts_and_nevis', 'Saint Kitts and Nevis'],
    ['saint_lucia', 'Saint Lucia'],
    ['saint_vincent_and_the_grenadines', 'Saint Vincent and the Grenadines'],
    ['suriname', 'Suriname'],
    ['trinidad_and_tobago', 'Trinidad and Tobago'],
    ['uruguay', 'Uruguay'],
    ['venezuela', 'Venezuela'],
    ['afghanistan', 'Afghanistan'],
    ['bahrain', 'Bahrain'],
    ['bangladesh', 'Bangladesh'],
    ['bhutan', 'Bhutan'],
    ['brunei', 'Brunei'],
    ['cambodia', 'Cambodia'],
    ['cyprus', 'Cyprus'],
    ['timor_leste', 'Timor-Leste'],
    ['jordan', 'Jordan'],
    ['kazakhstan', 'Kazakhstan'],
    ['kuwait', 'Kuwait'],
    ['kyrgyzstan', 'Kyrgyzstan'],
    ['laos', 'Laos'],
    ['lebanon', 'Lebanon'],
    ['malaysia', 'Malaysia'],
    ['maldives', 'Maldives'],
    ['mongolia', 'Mongolia'],
    ['myanmar', 'Myanmar'],
    ['nepal', 'Nepal'],
    ['north_korea', 'North Korea'],
    ['oman', 'Oman'],
    ['philippines', 'Philippines'],
    ['qatar', 'Qatar'],
    ['singapore', 'Singapore'],
    ['sri_lanka', 'Sri Lanka'],
    ['syria', 'Syria'],
    ['taiwan', 'Taiwan'],
    ['tajikistan', 'Tajikistan'],
    ['thailand', 'Thailand'],
    ['turkmenistan', 'Turkmenistan'],
    ['uae', 'United Arab Emirates'],
    ['uzbekistan', 'Uzbekistan'],
    ['yemen', 'Yemen'],
    ['albania', 'Albania'],
    ['andorra', 'Andorra'],
    ['austria', 'Austria'],
    ['belarus', 'Belarus'],
    ['belgium', 'Belgium'],
    ['bosnia_and_herzegovina', 'Bosnia and Herzegovina'],
    ['bulgaria', 'Bulgaria'],
    ['croatia', 'Croatia'],
    ['czech_republic', 'Czech Republic'],
    ['denmark', 'Denmark'],
    ['estonia', 'Estonia'],
    ['finland', 'Finland'],
    ['greece', 'Greece'],
    ['hungary', 'Hungary'],
    ['iceland', 'Iceland'],
    ['ireland', 'Ireland'],
    ['latvia', 'Latvia'],
    ['liechtenstein', 'Liechtenstein'],
    ['lithuania', 'Lithuania'],
    ['luxembourg', 'Luxembourg'],
    ['malta', 'Malta'],
    ['moldova', 'Moldova'],
    ['monaco', 'Monaco'],
    ['montenegro', 'Montenegro'],
    ['netherlands', 'Netherlands'],
    ['north_macedonia', 'North Macedonia'],
    ['norway', 'Norway'],
    ['portugal', 'Portugal'],
    ['romania', 'Romania'],
    ['san_marino', 'San Marino'],
    ['serbia', 'Serbia'],
    ['slovakia', 'Slovakia'],
    ['slovenia', 'Slovenia'],
    ['sweden', 'Sweden'],
    ['switzerland', 'Switzerland'],
    ['fiji', 'Fiji'],
    ['kiribati', 'Kiribati'],
    ['marshall_islands', 'Marshall Islands'],
    ['micronesia', 'Micronesia'],
    ['nauru', 'Nauru'],
    ['new_zealand', 'New Zealand'],
    ['palau', 'Palau'],
    ['papua_new_guinea', 'Papua New Guinea'],
    ['samoa', 'Samoa'],
    ['solomon_islands', 'Solomon Islands'],
    ['tonga', 'Tonga'],
    ['tuvalu', 'Tuvalu'],
    ['vanuatu', 'Vanuatu']
];

// A handful of background nations whose real-world government is
// unambiguously authoritarian; everything else defaults to 'democracy'
// as a simplification -- these are reference nations, not individually
// researched the way the core roster is.
const BACKGROUND_AUTHORITARIAN = [
    'afghanistan' => true,
    'belarus' => true,
    'cuba' => true,
    'equatorial_guinea' => true,
    'eritrea' => true,
    'myanmar' => true,
    'north_korea' => true,
    'syria' => true,
    'turkmenistan' => true
];

const BACKGROUND_NATION_ALIASES = [
    'uae' => ['uae', 'united arab emirates'],
    'north_korea' => ['north korea', 'dprk'],
    'congo_dr' => ['democratic republic of the congo', 'dr congo', 'drc'],
    'congo_republic' => ['republic of the congo', 'congo-brazzaville'],
    'ivory_coast' => ['ivory coast', 'cote d\'ivoire', 'côte d\'ivoire'],
    'timor_leste' => ['timor-leste', 'east timor'],
    'czech_republic' => ['czech republic', 'czechia']
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

    foreach (BACKGROUND_NATIONS as [$bid, $bname]) {
        $nations[$bid] = new_nation($bid, $bname, [
            'stability' => 55.0,
            'military' => 20.0,
            'economy' => 30.0,
            'is_background' => true,
            'government_type' => isset(BACKGROUND_AUTHORITARIAN[$bid]) ? 'authoritarian' : 'democracy',
        ]);
    }

    return new_world($nations, random_int(1, 1000000));
}
