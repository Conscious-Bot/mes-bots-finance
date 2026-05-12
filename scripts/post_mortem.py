#!/usr/bin/env python3
"""
Post-mortem : observable state of the bot over N days.
Schema-aware (introspects bot.db).
Usage: python scripts/post_mortem.py [--days=10] [--out=report.md]
"""
import argparse, sqlite3
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'bot.db'


def cols(cx, tbl):
    try:
        return [r['name'] for r in cx.execute(f'PRAGMA table_info({tbl})').fetchall()]
    except Exception:
        return []


def pick(cands, available):
    for c in cands:
        if c in available:
            return c
    return None


def keys_of(row):
    return row.keys() if row else []


def report(days: int = 10, out_path: str | None = None):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    end30 = (date.today() + timedelta(days=30)).isoformat()
    buf: list[str] = []

    def p(s: str = ''):
        buf.append(s)
        print(s)

    p('═' * 60)
    p(f'  POST-MORTEM — last {days} days (since {cutoff})')
    p('═' * 60)
    p()

    cx = sqlite3.connect(str(DB))
    cx.row_factory = sqlite3.Row

    # source_id (int) → name lookup
    src_map = {}
    if cols(cx, 'sources'):
        for r in cx.execute('SELECT id, name FROM sources').fetchall():
            src_map[r['id']] = r['name']

    def resolve_source(v):
        if v is None: return '?'
        if isinstance(v, int) and v in src_map: return src_map[v]
        return str(v)

    # ── Signals ──────────────────────────────────────────────────
    sc = cols(cx, 'signals')
    if sc:
        date_col = pick(['timestamp','processed_at','received_at','ingested_at','created_at'], sc)
        score_col = pick(['score','final_score','synthesis_score'], sc)
        src_col = pick(['source_id','source','source_name'], sc)
        ttl_col = pick(['title','subject','headline'], sc)

        total = cx.execute('SELECT COUNT(*) AS n FROM signals').fetchone()['n']
        if date_col:
            recent = cx.execute(
                f'SELECT * FROM signals WHERE {date_col} >= ? ORDER BY id DESC',
                (cutoff,)
            ).fetchall()
        else:
            recent = cx.execute('SELECT * FROM signals ORDER BY id DESC LIMIT 30').fetchall()
        p(f'▶ Signals: {len(recent)} in window / {total} total')

        if recent and score_col:
            top = sorted(recent, key=lambda r: (r[score_col] or 0), reverse=True)[:5]
            p('  top by score:')
            for s in top:
                sc_v = s[score_col] if score_col else '?'
                src_v = resolve_source(s[src_col]) if src_col else '?'
                ttl_v = (s[ttl_col] if ttl_col and s[ttl_col] else '?').replace('\n',' ')[:55]
                p(f'    [{s["id"]:4d}] score={sc_v} src={src_v[:20]:20s} | {ttl_v}')
        p()

    # ── Predictions ──────────────────────────────────────────────
    if cols(cx, 'predictions'):
        opened = cx.execute("SELECT COUNT(*) AS n FROM predictions WHERE outcome IS NULL").fetchone()['n']
        resolved = cx.execute("SELECT COUNT(*) AS n FROM predictions WHERE outcome IS NOT NULL").fetchone()['n']
        p(f'▶ Predictions: {opened} open / {resolved} resolved')
        if resolved > 0:
            wins = cx.execute("SELECT COUNT(*) AS n FROM predictions WHERE outcome='CORRECT'").fetchone()['n']
            avg = cx.execute("SELECT AVG(return_pct) AS r FROM predictions WHERE outcome IS NOT NULL").fetchone()['r'] or 0
            p(f'  win rate: {wins}/{resolved} ({100*wins/resolved:.0f}%) | avg return: {avg:+.2%}')
            rec = cx.execute("""
                SELECT id, signal_id, ticker, direction, baseline_price, final_price, return_pct, outcome, credibility_delta, resolved_at
                FROM predictions WHERE outcome IS NOT NULL
                ORDER BY resolved_at DESC LIMIT 5
            """).fetchall()
            if rec:
                p('  last 5 resolved:')
                for r in rec:
                    p(f'    [{r["id"]:3d}] {r["ticker"]:6s} {r["direction"]:5s} '
                      f'${r["baseline_price"]:.2f}→${r["final_price"]:.2f} '
                      f'({r["return_pct"]:+.2%}) {r["outcome"]:10s} '
                      f'cred_Δ={r["credibility_delta"]:+.3f}')
        if opened > 0:
            opens = cx.execute("""
                SELECT id, ticker, direction, baseline_price, baseline_date, target_date, horizon_days
                FROM predictions WHERE outcome IS NULL
                ORDER BY target_date ASC LIMIT 5
            """).fetchall()
            p('  open predictions:')
            for r in opens:
                p(f'    [{r["id"]:3d}] {r["ticker"]:6s} {r["direction"]:5s} '
                  f'@${r["baseline_price"]:.2f} since {r["baseline_date"]} '
                  f'→ resolve {r["target_date"]} ({r["horizon_days"]}d)')
        p()

    # ── Theses ───────────────────────────────────────────────────
    if cols(cx, 'theses'):
        rows = cx.execute('SELECT * FROM theses ORDER BY id DESC LIMIT 20').fetchall()
        active = [r for r in rows if r['status'] == 'active']
        closed = [r for r in rows if r['status'] != 'active']
        p(f'▶ Theses: {len(active)} active / {len(closed)} closed (last 20)')
        for t in active:
            keys = keys_of(t)
            tk = t['ticker']
            direction = t['direction'] if 'direction' in keys else ''
            conv = t['conviction'] if 'conviction' in keys else ''
            entry = t['entry_price'] if 'entry_price' in keys else '?'
            target = t['target_price'] if 'target_price' in keys else '?'
            stop = t['stop_price'] if 'stop_price' in keys else '?'
            horizon = t['horizon'] if 'horizon' in keys else '?'
            drv = ((t['key_drivers'] if 'key_drivers' in keys else '') or '').replace('\n',' ')[:80]
            partial = t['target_partial'] if 'target_partial' in keys else None
            full_t = t['target_full'] if 'target_full' in keys else None
            tgt_str = f"target=${target}"
            if partial or full_t:
                tgt_str = f"partial=${partial} full=${full_t}"
            p(f'  ACTIVE  {tk:6s} [{direction}/conv={conv}] entry=${entry} {tgt_str} stop=${stop} ({horizon})')
            if drv:
                p(f'          drivers: {drv}')
            for tag in ('clv_90d','clv_30d','clv_7d'):
                if tag in keys and t[tag] is not None:
                    p(f'          {tag}={t[tag]:+.2%}')
                    break
        for t in closed[:5]:
            p(f'  {t["status"].upper():8s} {t["ticker"]}')
        p()

    # ── Upcoming catalysts ───────────────────────────────────────
    p('▶ Upcoming catalysts (next 30d)')
    events = cx.execute(
        "SELECT date, event_type, ticker, description FROM events "
        "WHERE date BETWEEN ? AND ? ORDER BY date",
        (today, end30)
    ).fetchall()
    icons = {'fomc':'🏦','cpi':'📊','nfp':'💼','earnings':'📈'}
    for e in events[:15]:
        icn = icons.get(e['event_type'], '•')
        desc = (e['description'] or '')[:50]
        tk = e['ticker'] or 'MACRO'
        p(f'  {icn} {e["date"]} {e["event_type"]:8s} {tk:6s} {desc}')
    if len(events) > 15:
        p(f'  ... + {len(events)-15} more')
    p()

    # ── Shadow decisions ─────────────────────────────────────────
    if cols(cx, 'shadow_decisions'):
        tot = cx.execute('SELECT COUNT(*) AS n FROM shadow_decisions').fetchone()['n']
        rez = cx.execute('SELECT COUNT(*) AS n FROM shadow_decisions WHERE resolved_at IS NOT NULL').fetchone()['n']
        p(f'▶ Shadow decisions: {tot} total / {rez} resolved')
        if rez > 0:
            r = cx.execute("""
                SELECT
                    SUM(CASE WHEN main_outcome='CORRECT' THEN 1 ELSE 0 END) AS m,
                    SUM(CASE WHEN aggressive_outcome='CORRECT' THEN 1 ELSE 0 END) AS a,
                    SUM(CASE WHEN conservative_outcome='CORRECT' THEN 1 ELSE 0 END) AS c
                FROM shadow_decisions WHERE resolved_at IS NOT NULL
            """).fetchone()
            m, a, c = (r['m'] or 0), (r['a'] or 0), (r['c'] or 0)
            p(f'  CORRECT — main:{m}  aggressive:{a}  conservative:{c}  (out of {rez})')
            if rez >= 5:
                if a > m:
                    p(f'  ⚠ aggressive > main — bot may be under-confident, raise scoring')
                elif c > m:
                    p(f'  ⚠ conservative > main — bot may be over-confident, lower scoring')
        p()

    # ── Source credibility + activity ────────────────────────────
    if cols(cx, 'sources'):
        srcs = cx.execute("""
            SELECT name, type, credibility, n_signals, n_correct, last_signal_at
            FROM sources
            WHERE credibility IS NOT NULL
            ORDER BY credibility DESC LIMIT 12
        """).fetchall()
        if srcs:
            p('▶ Source credibility (top 12)')
            for s in srcs:
                n_sig = s['n_signals'] or 0
                n_cor = s['n_correct'] or 0
                wr = (n_cor / n_sig * 100) if n_sig > 0 else 0
                last = (s['last_signal_at'] or '?')[:10]
                p(f'  {(s["name"] or "?")[:24]:24s} cred={s["credibility"]:.3f} '
                  f'({n_cor}/{n_sig}, {wr:3.0f}%) last={last}')
            p()

    cx.close()
    p('═' * 60)

    if out_path:
        Path(out_path).write_text('\n'.join(buf))
        print(f'\n[saved → {out_path}]')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=10)
    ap.add_argument('--out', type=str, default=None, help='save report to markdown file')
    args = ap.parse_args()
    report(days=args.days, out_path=args.out)
