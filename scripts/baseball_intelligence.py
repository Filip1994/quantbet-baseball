from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OBS = Path('data/baseball/market_observations.jsonl')
OUT = Path('data/baseball/market_intelligence.json')


def num(x: Any) -> float | None:
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def dt(x: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(x)).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def main() -> None:
    rows: list[dict[str, Any]] = []
    if OBS.exists():
        with OBS.open(encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if num(r.get('odds')) is not None and r.get('game_id') is not None:
                    rows.append(r)

    market_counts = Counter(str(r.get('market') or 'UNKNOWN') for r in rows)
    book_counts = Counter(str(r.get('bookmaker_name') or 'UNKNOWN') for r in rows)
    league_counts = Counter(str(r.get('league') or 'UNKNOWN') for r in rows)
    event_counts = Counter(str(r.get('game_id')) for r in rows)

    groups: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for r in rows:
        key = (str(r.get('game_id')), str(r.get('market')), str(r.get('selection')), str(r.get('handicap')))
        v = num(r.get('odds'))
        if v is not None:
            groups[key].append(v)
    dispersion: list[dict[str, Any]] = []
    for (game, market, selection, handicap), vals in groups.items():
        if len(vals) < 3:
            continue
        dispersion.append({
            'game_id': game, 'market': market, 'selection': selection,
            'handicap': None if handicap == 'None' else handicap,
            'books': len(vals), 'min_odds': min(vals), 'max_odds': max(vals),
            'mean_odds': round(statistics.mean(vals), 4),
            'stdev': round(statistics.pstdev(vals), 4),
            'range': round(max(vals) - min(vals), 4),
        })
    dispersion.sort(key=lambda x: (x['range'], x['books']), reverse=True)

    series: dict[tuple[str, str, str, str, str], list[tuple[datetime, float]]] = defaultdict(list)
    for r in rows:
        t, v = dt(r.get('captured_at')), num(r.get('odds'))
        if t and v is not None:
            key = (str(r.get('game_id')), str(r.get('bookmaker_name')), str(r.get('market')), str(r.get('selection')), str(r.get('handicap')))
            series[key].append((t, v))
    movements: list[dict[str, Any]] = []
    for (game, book, market, selection, handicap), vals in series.items():
        vals.sort()
        if len(vals) < 2:
            continue
        first_t, first = vals[0]
        last_t, last = vals[-1]
        movements.append({
            'game_id': game, 'bookmaker': book, 'market': market, 'selection': selection,
            'handicap': None if handicap == 'None' else handicap, 'observations': len(vals),
            'first_odds': first, 'last_odds': last, 'delta': round(last - first, 4),
            'pct_change': round((last / first - 1) * 100, 3),
            'first_at': first_t.isoformat(), 'last_at': last_t.isoformat(),
        })
    movers = sorted(movements, key=lambda x: abs(x['pct_change']), reverse=True)

    late: list[dict[str, Any]] = []
    for r in rows:
        k, t, v = dt(r.get('kickoff')), dt(r.get('captured_at')), num(r.get('odds'))
        if k and t and v:
            mins = (k - t).total_seconds() / 60
            if 0 <= mins <= 60:
                rr = dict(r); rr['_mins_to_kickoff'] = mins; late.append(rr)
    late_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in late:
        late_groups[(str(r.get('game_id')), str(r.get('bookmaker_name')), str(r.get('market')), str(r.get('selection')))].append(r)
    late_moves = []
    for key, vals in late_groups.items():
        vals.sort(key=lambda x: x['_mins_to_kickoff'], reverse=True)
        if len(vals) < 2:
            continue
        a, b = num(vals[0].get('odds')), num(vals[-1].get('odds'))
        if a and b:
            late_moves.append({
                'game_id': key[0], 'bookmaker': key[1], 'market': key[2], 'selection': key[3],
                'first_60m_odds': a, 'last_60m_odds': b, 'delta': round(b-a, 4),
                'pct_change': round((b/a-1)*100, 3), 'observations': len(vals),
            })
    late_moves.sort(key=lambda x: abs(x['pct_change']), reverse=True)

    family_tokens = {
        'winner': ('match winner', 'home/away', '1x2'),
        'run_line': ('asian handicap',),
        'totals': ('over/under', 'team total', 'goals over/under'),
        'hits': ('total hits', 'home total hits', 'away total hits'),
        'player_props': ('player runs', 'player hits', 'player total bases', 'pitcher strikeouts', 'pitcher hits allowed', 'player doubles', 'player stolen bases'),
    }
    family_counts = {fam: sum(c for m, c in market_counts.items() if any(t in m.casefold() for t in toks)) for fam, toks in family_tokens.items()}

    result = {
        'generated_at': datetime.now(UTC).isoformat(),
        'dataset': {'observations': len(rows), 'events': len(event_counts), 'leagues': len(league_counts), 'bookmakers': len(book_counts), 'markets': len(market_counts)},
        'market_family_observations': family_counts,
        'top_leagues_by_observations': league_counts.most_common(15),
        'top_bookmakers_by_observations': book_counts.most_common(15),
        'top_markets_by_observations': market_counts.most_common(30),
        'event_density': {'median_observations_per_event': statistics.median(event_counts.values()) if event_counts else 0, 'max': max(event_counts.values()) if event_counts else 0, 'min': min(event_counts.values()) if event_counts else 0},
        'cross_bookmaker_dispersion': {'groups': len(dispersion), 'largest_ranges': dispersion[:25]},
        'price_movement': {'series': len(movements), 'largest_absolute_moves': movers[:40]},
        'closing_60m': {'rows': len(late), 'largest_moves': late_moves[:40]},
        'model_readiness': {'status': 'LEARNING_ONLY', 'validated_predictions': 0, 'real_money_enabled': False},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'observations': len(rows), 'events': len(event_counts), 'dispersion_groups': len(dispersion), 'movement_series': len(movements), 'closing_rows': len(late)}))


if __name__ == '__main__':
    main()
