<?php
require_once __DIR__ . '/orders.php';

function score_order(array $world, array $order): float {
    $actor = $world['nations'][$order['actor_id']];
    $target = $order['target_id'] !== null ? $world['nations'][$order['target_id']] : null;
    $type = $order['type'];

    if ($type === 'pass') return 0.1;

    if ($type === 'build_military') {
        $threat = 0.0;
        foreach (set_ids($actor['at_war_with']) as $eid) {
            if (isset($world['nations'][$eid])) $threat = max($threat, $world['nations'][$eid]['military']);
        }
        $base = 1.0 + ($threat - $actor['military']) * 0.05;
        return $actor['economy'] > 20 ? $base : -5.0;
    }

    if ($type === 'invest_economy') {
        return 3.0 + (60 - $actor['economy']) * 0.05;
    }

    if ($type === 'invest_sector') {
        return 2.0 + (50 - ($actor['sectors'][$order['detail']] ?? 40)) * 0.05;
    }

    if ($type === 'modify_constitution') return -50.0;

    if ($type === 'improve_relations') {
        $rel = nation_relation($actor, $order['target_id']);
        return 1.0 + (50 - $rel) * 0.02;
    }

    if ($type === 'propose_alliance') {
        $mutual = min(nation_relation($actor, $order['target_id']), nation_relation($target, $order['actor_id']));
        return 4.0 + $mutual * 0.05;
    }

    if ($type === 'break_alliance') {
        $rel = nation_relation($actor, $order['target_id']);
        return $rel < -40 ? (-$rel - 40) * 0.1 : -10.0;
    }

    if ($type === 'trade_pact') {
        $mutual = min(nation_relation($actor, $order['target_id']), nation_relation($target, $order['actor_id']));
        $saturation = max(0, count($actor['trade_pacts']) - 3) * 1.5;
        return 2.0 + $mutual * 0.03 + (60 - $actor['economy']) * 0.02 - $saturation;
    }

    if ($type === 'impose_embargo') {
        $rel = nation_relation($actor, $order['target_id']);
        return $rel < -20 ? (-$rel) * 0.05 : -10.0;
    }

    if ($type === 'declare_war') {
        $rel = nation_relation($actor, $order['target_id']);
        if ($rel > -30) return -20.0;
        $powerEdge = $actor['military'] - $target['military'];
        $stabilityOk = $actor['stability'] > 40;
        $score = $powerEdge * 0.1 + (-$rel) * 0.05;
        return $stabilityOk ? $score : $score - 15.0;
    }

    if ($type === 'sue_for_peace') {
        $losing = $actor['military'] < $target['military'] * 0.8;
        $exhausted = $actor['stability'] < 35;
        $mutuallyExhausted = $actor['military'] < 15 && $target['military'] < 15;
        return ($losing || $exhausted || $mutuallyExhausted) ? 6.0 : -5.0;
    }

    if ($type === 'annex') {
        return 8.0 + ($actor['military'] - $target['military']) * 0.05;
    }

    if ($type === 'propose_accession') return -50.0;

    if ($type === 'invite_accession') {
        $mutual = min(nation_relation($actor, $order['target_id']), nation_relation($target, $order['actor_id']));
        return 5.0 + $mutual * 0.05;
    }

    return -100.0;
}

function choose_order(array $world, string $actorId): array {
    $candidates = legal_orders($world, $actorId);
    $best = null; $bestScore = -INF; $bestTie = -INF;
    foreach ($candidates as $o) {
        $s = score_order($world, $o);
        $tie = mt_rand() / mt_getrandmax();
        if ($s > $bestScore || ($s === $bestScore && $tie > $bestTie)) {
            $best = $o; $bestScore = $s; $bestTie = $tie;
        }
    }
    return $best;
}
