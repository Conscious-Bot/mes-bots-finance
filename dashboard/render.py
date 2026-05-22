"""dashboard/render.py — high-level dashboard (light Atrium, gamified-discipline).

Mix: Atrium classe + clair (Enki) + dopamine gamifie CABLE SUR LE PROCESS:
paliers = progres vers target PRE-COMMITE (hitting = trim signal, fights
hold-too-long), gold milestones, prismatic apex. Green/red % coupled with the
bot's flags. READ-ONLY. Reads via canonical gateways (CONVENTIONS rule 5).
"""

from datetime import datetime
from pathlib import Path

from intelligence import asymmetry as asym_mod

OUTPUT = Path("dashboard/dashboard.html")


def build_paliers() -> tuple[str, int, int]:
    """Progress bars vers target pre-commit. Hit = trim signal (discipline reward)."""
    results = asym_mod.compute_portfolio_asymmetry()
    computed = [r for r in results if "asymmetry_ratio" in r]
    rows = []
    hit_count = 0
    for r in computed:
        entry = r.get("entry") or 0
        target = r.get("target_full") or 0
        cur = r.get("current_price") or 0
        if not entry or not target or target == entry:
            continue
        pnl = (cur - entry) / entry * 100
        prog = (cur - entry) / (target - entry) * 100
        prog_clamped = max(0.0, min(100.0, prog))
        hit = prog >= 100
        if hit:
            hit_count += 1
        pnl_cls = "up" if pnl >= 0 else "down"
        pnl_sign = "+" if pnl >= 0 else ""
        bar_cls = "prismatic" if hit else "gold"
        flag = " 🎯" if hit else ""
        rows.append((prog, f'''
      <div class="palier">
        <div class="palier-top">
          <span class="tk">{r['ticker']}{flag}</span>
          <span class="pnl {pnl_cls}">{pnl_sign}{pnl:.1f}%</span>
        </div>
        <div class="track"><div class="fill {bar_cls}" style="width:{prog_clamped:.0f}%"></div></div>
        <div class="palier-sub"><span>vers target</span><span class="prog">{prog:.0f}%</span></div>
      </div>'''))
    rows.sort(key=lambda x: -x[0])
    return "".join(h for _, h in rows), len(rows), hit_count


_SHELL = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Heimdall</title>
<style>
  :root { --atrium:#F9FAF6; --card:#FFFFFF; --ink:#0E1726; --steel:#6B7689; --line:#E8E9E4;
          --bull:#0E9F45; --bear:#D33A2C; --gold:#D9AC2E; --tide:#2D8A8B; }
  * { box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
         background:var(--atrium); color:var(--ink); margin:0; padding:28px 32px;
         -webkit-font-smoothing:antialiased; }
  .head { display:flex; align-items:center; justify-content:space-between; margin-bottom:26px; }
  .brand { display:flex; align-items:center; gap:14px; }
  .logo { width:42px; height:42px; border-radius:11px; background:var(--ink); color:var(--atrium);
          display:flex; align-items:center; justify-content:center; font-weight:700; font-size:20px; }
  .brand h1 { font-size:22px; font-weight:600; margin:0; letter-spacing:-0.01em; }
  .status { display:flex; align-items:center; gap:8px; color:var(--steel); font-size:13px; }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--bull); }
  .labrow { display:flex; align-items:baseline; justify-content:space-between; margin:0 0 12px; }
  .label { text-transform:uppercase; letter-spacing:0.16em; font-size:11px; font-weight:600;
           color:var(--steel); margin:0; }
  .label b { color:var(--tide); }
  .summary { font-size:13px; color:var(--steel); }
  .summary b { color:var(--gold); font-weight:700; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:16px;
          padding:20px 22px; margin-bottom:22px; box-shadow:0 1px 3px rgba(15,23,38,.04); }
  .palier { padding:13px 0; border-bottom:1px solid var(--line); }
  .palier:last-child { border-bottom:none; }
  .palier-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
  .tk { font-weight:600; font-size:15px; }
  .pnl { font-weight:700; font-size:14px; padding:2px 9px; border-radius:7px; }
  .pnl.up { color:var(--bull); background:rgba(14,159,69,.10); }
  .pnl.down { color:var(--bear); background:rgba(211,58,44,.10); }
  .track { height:10px; background:#EDEEE9; border-radius:6px; overflow:hidden; }
  .fill { height:100%; border-radius:6px; }
  .fill.gold { background:linear-gradient(90deg,#E9B949,#D9AC2E); }
  .fill.prismatic { background:linear-gradient(100deg,#FFD24A,#FF5E9C,#8A6CFF,#36C6C6);
                    box-shadow:0 0 12px rgba(255,94,156,.55); }
  .palier-sub { display:flex; justify-content:space-between; margin-top:6px;
                font-size:12px; color:var(--steel); }
  .prog { font-weight:600; color:var(--ink); }
</style></head><body>
  <div class="head">
    <div class="brand"><div class="logo">H</div><h1>Heimdall</h1></div>
    <div class="status"><span class="dot"></span>en veille · ___STAMP___</div>
  </div>
  <div class="labrow">
    <p class="label"><b>01</b> // Paliers — progression vers tes targets pre-commits</p>
    <span class="summary"><b>___HITS___</b> atteints · ___ACTIVE___ en cours</span>
  </div>
  <div class="card">___PANEL_PALIERS___</div>
</body></html>
"""


def render() -> Path:
    paliers_html, active, hits = build_paliers()
    html = _SHELL.replace("___PANEL_PALIERS___", paliers_html)
    html = html.replace("___HITS___", str(hits)).replace("___ACTIVE___", str(active))
    html = html.replace("___STAMP___", datetime.now().strftime("%d.%m.%Y · %H:%M"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html)
    return OUTPUT


if __name__ == "__main__":
    p = render()
    print(f"[OK] dashboard: {p} ({p.stat().st_size} bytes)")
