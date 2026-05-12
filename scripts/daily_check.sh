#!/bin/bash
# Daily bot health check. Run every morning before /digest.
cd /Users/olivierlegendre/mes-bots-finance
source venv/bin/activate 2>/dev/null

echo "═══════════════════════════════════════════════════════"
echo "  BOT HEALTH CHECK — $(date '+%Y-%m-%d %H:%M')"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "▶ Process state"
PROCS=$(ps aux | grep "bot.main" | grep -v grep | wc -l | tr -d ' ')
if [ "$PROCS" = "1" ]; then echo "  ✓ 1 instance running"; 
elif [ "$PROCS" = "0" ]; then echo "  ✗ DEAD — no bot process"; 
else echo "  ⚠ $PROCS instances (DEDUPE NEEDED)"; fi

echo ""
echo "▶ Last 3 log lines"
tail -3 bot.log 2>/dev/null | sed 's/^/  /'

echo ""
echo "▶ DB snapshot"
python3 -c "
from shared.storage import db
from datetime import date, timedelta
today = date.today().isoformat()
weekago = (date.today() - timedelta(days=7)).isoformat()
with db() as cx:
    sig_total = cx.execute('SELECT COUNT(*) AS n FROM signals').fetchone()['n']
    sig_week = cx.execute('SELECT COUNT(*) AS n FROM signals WHERE date(received_at) >= ?', (weekago,)).fetchone()['n']
    th_active = cx.execute(\"SELECT COUNT(*) AS n FROM theses WHERE status='active'\").fetchone()['n']
    pred_open = cx.execute(\"SELECT COUNT(*) AS n FROM predictions WHERE outcome IS NULL\").fetchone()['n']
    pred_resolved = cx.execute(\"SELECT COUNT(*) AS n FROM predictions WHERE outcome IS NOT NULL\").fetchone()['n']
    macro_next7 = cx.execute(\"SELECT COUNT(*) AS n FROM events WHERE event_type IN ('fomc','cpi','nfp') AND date BETWEEN ? AND date(?, '+7 days')\", (today, today)).fetchone()['n']
    earn_next7 = cx.execute(\"SELECT COUNT(*) AS n FROM events WHERE event_type='earnings' AND date BETWEEN ? AND date(?, '+7 days')\", (today, today)).fetchone()['n']
    print(f'  signals: {sig_total} total ({sig_week} this week)')
    print(f'  theses active: {th_active}')
    print(f'  predictions: {pred_open} open / {pred_resolved} resolved')
    print(f'  events next 7d: {macro_next7} macro + {earn_next7} earnings')
"

echo ""
echo "▶ Macro catalysts next 14d"
python3 -c "
from intelligence.calendar import format_macro_calendar
out = format_macro_calendar(14)
for line in out.split('\n')[1:]:
    print('  ' + line.strip())
" 2>/dev/null

echo ""
echo "▶ Insider flow snapshot (cached)"
python3 -c "
from shared import edgar
from intelligence.digest import INSIDER_TOP_TICKERS
heavy_sellers = []
buyers = []
for t in INSIDER_TOP_TICKERS:
    b = edgar.get_insider_brief(t)
    if b:
        if b['net_m'] < -30: heavy_sellers.append((t, b['net_m']))
        elif b['net_m'] > 1: buyers.append((t, b['net_m']))
heavy_sellers.sort(key=lambda x: x[1])
print(f'  heavy sellers (<-\$30M): ' + ', '.join(f'{t} \${m:+.0f}M' for t,m in heavy_sellers[:5]))
print(f'  insider buyers (>\$1M):  ' + (', '.join(f'{t} \${m:+.1f}M' for t,m in buyers) if buyers else '(none)'))
"

echo ""
echo "═══════════════════════════════════════════════════════"
