"""Dashboard CSS constants -- extracted from render.py Phase 1 refactor (02/06).

Pure data, no behavior. Imported by render.py.
"""
from pathlib import Path

_TH_CSS = """
<style>
  .th-gap { margin-bottom:var(--s4); }
  .th-hist { display:flex; flex-direction:column; gap:var(--s15); padding:2px 0; }
  .th-hbar { display:flex; align-items:center; gap:11px; font-family:var(--fm); font-size:var(--t-data2); }
  .th-hlab { width:24px; color:var(--steel); }
  .th-hbar .axis { flex:1; margin:0; }
  .th-htrack { flex:1; height:5px; border-radius:var(--r0); background:color-mix(in srgb,var(--ink) 6%,transparent); overflow:hidden; }
  .th-hfill { height:100%; border-radius:var(--r0); background:color-mix(in srgb,var(--ink) 55%,transparent); transition:width .25s ease-out; }
  body.midnight .th-htrack { background:rgba(255,255,255,.05); }
  body.midnight .th-hfill { background:color-mix(in srgb,var(--ink) 75%,transparent); }
  .th-hn { width:22px; text-align:right; color:var(--ink); font-weight:600; }

  /* === Canonical track bar (#91 signature unifie 03/06/2026) =============
     Une primitive visuelle pour TOUS les axes du dashboard : track + dot +
     ticks optionnels. Remplace .axis + .axis-mark + .axis-target-tick + le
     mask SVG losange. Pas de gradient (sauf cas signature ou les extremes
     ont vraiment un sens et le tick aux extremites le porte). Stripe/Linear.
     Anti-Robinhood (#103 invariant : motion encode le delta, pas l'excitation). */
  .tbar { position:relative; width:100%; height:5px; border-radius:var(--r0); background:color-mix(in srgb,var(--ink) 6%,transparent); margin:var(--s2) 0; cursor:default; }
  .tbar-tick { position:absolute; top:-2px; width:1.5px; height:9px; background:var(--ink); opacity:.7; border-radius:var(--r0); pointer-events:none; }
  .tbar-tick.dash { background:transparent; border-left:1px dashed var(--steel); opacity:.55; width:0; }
  /* Ticks colores axes signature position (limit/zero/target) :
     - stop = red (limit gauche)
     - entry/cost = grey (zero central, ton coût = point de départ)
     - partial = jaune (première prise de profit decidée, feu tricolore)
     - target = green (cible pleine decidée)
     Dot noir par defaut ; rouge si dot <= stop, vert si dot >= target OU
     beyond (cur_native >= target_native, cf SPEC_GAUGE §1.4). */
  /* Feu tricolore canonique de la gauge (cf SPEC_GAUGE §1.3) : couleurs FLUO
     vives explicites, pour que stop/partial/target se distinguent d'un coup
     d'œil. Les vars globales --bear/--warn/--acc restent sobres pour le reste
     du dashboard (DNA parchemin/instrument). Ici, sur la gauge spécifiquement,
     on assume le contraste vif — c'est l'unique surface où le feu tricolore
     doit crier sa sémantique. */
  .tbar-tick.stop    { background:#ff1744; opacity:1; height:14px; top:-4.5px; width:3px; border-radius:var(--r0); box-shadow:0 0 4px rgba(255,23,68,.55); }
  .tbar-tick.entry   { background:var(--steel); opacity:.75; height:11px; top:-3px; width:1.5px; }
  .tbar-tick.partial { background:#ffd400; opacity:1; height:14px; top:-4.5px; width:3px; border-radius:var(--r0); box-shadow:0 0 4px rgba(255,212,0,.55); }
  .tbar-tick.target  { background:#00e676; opacity:1; height:14px; top:-4.5px; width:3px; border-radius:var(--r0); box-shadow:0 0 4px rgba(0,230,118,.55); }
  /* axe-prix natif (SPEC_GAUGE §3) : caret cost sous-ligne + chevrons overflow */
  .tbar-cost-caret { position:absolute; bottom:-5px; width:0; height:0; border-left:4px solid transparent; border-right:4px solid transparent; border-bottom:6px solid var(--steel); transform:translateX(-50%); pointer-events:none; z-index:2; }
  .tbar-cost-caret.stale { opacity:.5; border-bottom-color:var(--warn); }
  .tbar-chevron-left, .tbar-chevron-right { position:absolute; top:50%; transform:translateY(-50%); color:var(--steel); font-size:var(--t-fine); line-height:1; opacity:.7; pointer-events:none; z-index:2; }
  .tbar-chevron-left { left:1px; }
  .tbar-chevron-right { right:1px; }
  .tbar-dot { position:absolute; top:50%; width:9px; height:9px; border-radius:var(--r-circle); background:var(--ink); transform:translate(-50%,-50%); z-index:2; box-shadow:0 0 0 1.5px var(--bg), 0 1px 3px rgba(0,0,0,.18); transition:left .25s ease-out; }
  .tbar-dot.acc { background:var(--acc); }
  .tbar-dot.warn { background:var(--warn); }
  .tbar-dot.bear { background:var(--bear); }
  .tbar-fill { position:absolute; left:0; top:0; height:100%; border-radius:var(--r0); background:color-mix(in srgb,var(--ink) 50%,transparent); transition:width .25s ease-out; }
  /* Hover tooltip : % continu sous le curseur. Pill ink-on-bg haute contraste,
     tabular nums (digits ne shiftent pas en width quand le curseur glisse),
     caret vers le bar, micro-motion opacity+slide.
     Variants .pos / .neg : pill verte / rouge quand signed % > 0 / < 0
     (user 03/06 "dynamic % cursor green above 0, red under 0"). */
  .tbar-hover-tip { --pill-bg:var(--ink); --pill-fg:var(--bg); position:absolute; bottom:13px; transform:translateX(-50%) translateY(3px); background:var(--pill-bg); color:var(--pill-fg); border-radius:var(--r1); padding:3px 8px 3.5px; font-family:var(--fm); font-size:var(--t-meta); font-weight:500; letter-spacing:.01em; font-variant-numeric:tabular-nums; line-height:1.25; pointer-events:none; white-space:nowrap; opacity:0; transition:opacity .14s ease-out, transform .14s ease-out, background .14s ease-out; z-index:5; box-shadow:var(--elev1); }
  .tbar-hover-tip::after { content:""; position:absolute; left:50%; top:100%; transform:translateX(-50%); width:0; height:0; border:3.5px solid transparent; border-top-color:var(--pill-bg); border-bottom:0; transition:border-top-color .14s ease-out; }
  .tbar-hover-tip.pos { --pill-bg:var(--acc); --pill-fg:#fff; }
  .tbar-hover-tip.neg { --pill-bg:var(--bear); --pill-fg:#fff; }
  .tbar:hover .tbar-hover-tip { opacity:1; transform:translateX(-50%) translateY(0); }
  /* Midnight adaptations : track plus subtil + ticks neutres lift en blanc
     transparent (mais SKIP les ticks colores sig-ent0 stop/entry/target qui
     gardent leur couleur tokens). Dot box-shadow ring follows var(--bg)
     auto -> pas besoin d'override. */
  body.midnight .tbar { background:rgba(255,255,255,.05); }
  body.midnight .tbar-fill { background:color-mix(in srgb,var(--ink) 70%,transparent); }
  body.midnight .tbar-tick:not(.stop):not(.entry):not(.partial):not(.target):not(.dash) { background:rgba(255,255,255,.55); }
  body.midnight .tbar-tick.entry { background:var(--steel); opacity:.7; }
  body.midnight .tbar-hover-tip { box-shadow:var(--elev1); }
  /* Section headers unifies (Polish 01/06) : meme pattern visuel pour
     .th-grp / .strat-sh / .vigie-sh / .dba-sh. Noms preserves pour HTML.
     Petit icon optionnel via .sh-ico (data-icon attr peut etre utilise). */
  .th-grp { font-family:var(--fm); font-weight:500; font-size:var(--t-data2); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:var(--s4) 2px var(--s3); display:flex; align-items:center; gap:var(--s3); }
  .th-grp::after { content:""; flex:1; height:1px; background:var(--line); }
  .sh-ico { width:14px; height:14px; flex-shrink:0; opacity:.6; }
  /* Sprint 2 purge borders TR-style + Sprint C polish : grid 180/52/1fr,
     hover translateX(2px), padding plus généreux, transition ease-out. */
  .th-row { display:grid; grid-template-columns:180px 52px 1fr; gap:var(--s3); align-items:center; padding:16px 8px; border-bottom:1px solid var(--line); margin-bottom:0; cursor:pointer; transition:background .15s ease-out, transform .15s ease-out, padding-left .15s ease-out; }
  .th-row:last-child { border-bottom:none; }
  .th-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); padding-left:14px; }
  .th-row:active { transform:scale(.997); }
  .th-id { display:flex; align-items:center; gap:9px; flex-wrap:wrap; }
  .th-conv { font-family:var(--fm); font-weight:600; font-size:var(--t-data); letter-spacing:.04em; padding:2px 7px; border-radius:var(--r1); }
  .th-conv.c5 { color:var(--bg); background:var(--ink); }
  .th-conv.c4 { color:var(--bg); background:var(--acc); }
  .th-conv.c3 { color:var(--bg); background:var(--warn); }
  .th-conv.c2 { color:var(--steel); border:1px solid var(--line2); }
  .th-conv.c1 { color:var(--steel); border:1px solid var(--line); opacity:.65; }
  .th-tk { font-weight:600; font-size:var(--t-base); }
  .th-w { font-family:var(--fm); font-size:var(--t-data2); font-weight:600; color:var(--ink); text-align:right; align-self:center; }
  .th-dir { font-family:var(--fb); font-size:var(--t-data); color:var(--steel); text-transform:uppercase; letter-spacing:.12em; }
  .th-bar { display:flex; flex-direction:column; gap:var(--s15); grid-column:1/-1; margin-top:var(--s2); }
  .sizebar { margin:var(--s15) 0 4px; }
  .th-adj { font-family:var(--fm); font-size:var(--t-data); letter-spacing:.02em; line-height:1.3; font-weight:500; }
  /* trim/bump alignes sur palette flashy (user 03/06) : trim=bear action-trigger,
     bump=acc action-trigger. ok reste steel mute (pas d'action). */
  .th-adj.trim { color:var(--bear); }
  .th-adj.add { color:var(--acc); }
  .th-adj.ok { color:var(--steel); }
  .th-szcol { display:flex; flex-direction:column; gap:5px; }
  .th-zone-loss { position:absolute; left:0; top:0; bottom:0; background:color-mix(in srgb, var(--bear) 13%, transparent); }
  .th-zone-profit { position:absolute; right:0; top:0; bottom:0; background:color-mix(in srgb, var(--acc) 13%, transparent); }
  .th-ends { display:flex; justify-content:space-between; align-items:baseline; font-family:var(--fm); font-size:var(--t-data); }
  .th-stop { color:var(--bear); }
  .th-tgt { color:var(--acc); font-weight:600; }
  /* Pass 6 audit color discipline : .th-pt = TARGET HIT (good news event).
     Defaut vert/acc. Variant .warn pour les rares cas "target hit + decision
     trim risquée" — amber, jamais rouge sur evenement favorable. */
  .th-pt { font-family:var(--fm); font-size:var(--t-data); padding:1px 7px; border-radius:var(--r1); background:color-mix(in srgb,var(--acc) 16%,transparent); color:var(--acc); letter-spacing:.04em; margin-left:var(--s2); text-transform:uppercase; }
  .th-pt.warn { background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }
  .th-pt.acc { background:color-mix(in srgb,var(--acc) 16%,transparent); color:var(--acc); }
  .th-na { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); }
  .th-cat { font-family:var(--fm); font-size:var(--t-data); letter-spacing:.03em; color:var(--steel); background:color-mix(in srgb, var(--steel) 10%, transparent); border:1px solid var(--line); border-radius:var(--r1); padding:2px 8px; margin-left:2px; white-space:nowrap; }
</style>
"""

_TOKENS_CSS = (Path(__file__).parent / "tokens.css").read_text(encoding="utf-8")

# Mode cahier-de-bord supprime 02/06 user "mode cahier a supprimer"
# (incompatible avec DNA instrument v2 cold/single accent).
# _CAHIER_CSS = (Path(__file__).parent / "cahier_de_bord.css").read_text(encoding="utf-8")

_CSS = """
  * { box-sizing:border-box; }
  /* Visually-hidden : a11y headings/labels for screen readers, off-screen visual. */
  .vh { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  /* Pass 15 audit 6 #3 — Long-form readability defaults.
     Auditor: "Augmentez l'interligne (line-height ~1.5–1.6) sur les paragraphes
     longs, et limitez la largeur de ligne." Cible : tout conteneur narratif
     (descriptions, empty states, copilot, narrative, at_risk, biais) hereft.
     Pas de touch sur les tables/numbers (mono compact reste). */
  p, .prose, .empty, .narrativecard p, .copilotcard p,
  .riskwatchcard .rw-cell, .biaiscard p,
  .gloss-def, .cp-latest-teaser { line-height: 1.55; }
  .prose, .narrativecard p, .biaiscard p, .gloss-def { max-width: 64ch; }
  /* Pass 15 audit 6 #4 — Canonical badge system.
     Avant : tag/bdg/warn-chip/pc-chip/qs-st/th-cat/th-pt incoherents.
     Apres : .badge avec 4 variants semantiques (neutral / info / warn / danger).
     Forme uniforme (pill 99px), padding 2/8px, mono 11px tracking .08em uppercase.
     Migration progressive — toute nouvelle ecriture utilise .badge.
     Tooltip data-tip pour expliciter ce que le tag represente. */
  .badge { display: inline-flex; align-items: center; gap: 4px; font-family: var(--fm); font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; padding: 2px 8px; border-radius: var(--r-pill); border: 1px solid transparent; line-height: 1.4; white-space: nowrap; }
  .badge.neutral { background: color-mix(in srgb, var(--steel) 10%, transparent); color: var(--steel); border-color: color-mix(in srgb, var(--steel) 25%, transparent); }
  .badge.info { background: color-mix(in srgb, var(--data) 10%, transparent); color: var(--data); border-color: color-mix(in srgb, var(--data) 35%, transparent); }
  .badge.warn { background: color-mix(in srgb, var(--warn) 12%, transparent); color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
  .badge.danger { background: color-mix(in srgb, var(--bear) 12%, transparent); color: var(--bear); border-color: color-mix(in srgb, var(--bear) 35%, transparent); }
  .badge.success { background: color-mix(in srgb, var(--acc) 12%, transparent); color: var(--acc); border-color: color-mix(in srgb, var(--acc) 35%, transparent); }
  /* content-visibility :auto skips layout/paint for off-viewport cards.
     ~3500 nodes pre-built in 26 position cards (47% DOM weight). Browser
     treats each card as a single skeleton box until scrolled near, then
     materialises full content. Cure Pass 2 audit #9 (lazy-paint, not lazy-build). */
  .pc-card { content-visibility:auto; contain-intrinsic-size:0 800px; }
  /* Pass 5 audit polish — contain isolation : chaque card limite ses repaints
     a son propre cadre. Mouse hover/state change ne force pas relayout amont. */
  .card, .kpi { contain: layout paint; }
  /* Pass 11 audit promotion — Copilot card in Overview prime real estate.
     Subtle highlight (border tinted with accent) signals "this is your edge"
     without screaming. CTA button mimics .cta-bar pill grammar. */
  .copilot-promote { border-color: color-mix(in srgb, var(--data) 30%, var(--line)); background: color-mix(in srgb, var(--data) 3%, var(--panel)); }
  .copilot-promote .cp-promote-edge { font-family: var(--fm); font-size: 11px; font-weight: 400; letter-spacing: .12em; text-transform: uppercase; color: var(--data); margin-left: 8px; padding: 2px 8px; border: 1px solid color-mix(in srgb, var(--data) 40%, transparent); border-radius: var(--r-pill); }
  .copilot-promote .cp-latest { display: flex; flex-direction: column; gap: 6px; padding: 14px 0 12px; }
  .copilot-promote .cp-latest-meta { font-family: var(--fm); font-size: 12px; color: var(--steel); letter-spacing: .04em; }
  .copilot-promote .cp-latest-verdict { font-family: var(--fm); font-size: 13px; font-weight: 600; letter-spacing: .04em; }
  .copilot-promote .cp-latest-verdict.ok { color: var(--acc); }
  .copilot-promote .cp-latest-verdict.warn { color: var(--warn); }
  .copilot-promote .cp-latest-verdict.bad { color: var(--bear); }
  .copilot-promote .cp-latest-verdict.calm { color: var(--steel); }
  .copilot-promote .cp-latest-teaser { font-family: var(--fb); font-size: 15px; line-height: 1.45; color: var(--ink); margin-top: 2px; }
  .copilot-promote .cp-promote-cta { display: flex; align-items: center; gap: 14px; padding-top: 14px; border-top: 1px solid color-mix(in srgb, var(--line) 60%, transparent); }
  .copilot-promote .cp-promote-btn { font-family: var(--fb); font-size: 15px; font-weight: 500; color: var(--bg); background: var(--ink); border: none; padding: 10px 18px; border-radius: var(--r-pill); cursor: pointer; transition: transform .08s ease-out, box-shadow .15s ease-out; box-shadow: var(--elev1); }
  .copilot-promote .cp-promote-btn:hover { box-shadow: var(--elev2); }
  .copilot-promote .cp-promote-btn:active { transform: scale(.97); }
  .copilot-promote .cp-promote-hint { font-family: var(--fm); font-size: 12px; color: var(--steel); }
  /* Pass 12 audit lexicon — glossary definition list in Method section.
     2-col grid > 720px, 1-col stack < 720. Term-def visual pair, scannable. */
  .glosscard .gloss-list { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s35) var(--s4); margin: 0; padding: 0; }
  @media (max-width: 720px) { .glosscard .gloss-list { grid-template-columns: 1fr; gap: var(--s3); } }
  .glosscard .gloss-item { padding: 14px 16px; border: 1px solid var(--line); border-radius: var(--r2); background: color-mix(in srgb, var(--ink) 2%, transparent); scroll-margin-top: 90px; }
  .glosscard .gloss-item:target { border-color: var(--data); background: color-mix(in srgb, var(--data) 6%, transparent); }
  .glosscard .gloss-term { font-family: var(--fm); font-size: 14px; font-weight: 600; color: var(--ink); margin: 0 0 6px; letter-spacing: .02em; }
  .glosscard .gloss-def { font-family: var(--fb); font-size: 14px; line-height: 1.5; color: var(--steel); margin: 0; }
  /* Pass 5 audit #19 : smooth scroll keyboard navigation (Tab/anchor jumps),
     gated by prefers-reduced-motion. Scroll-margin pour eviter clip sous
     header sticky .phead (~70px). */
  @media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
  [data-page] { scroll-margin-top: 78px; }
  /* Pass 5 audit P3 micro : tabular-nums sur monospace data cells -- evite
     jitter horizontal au hover/update (numbers ne shiftent pas comme avec
     proportional digits). Applique a .mono qui est le hot path data. */
  .mono { font-variant-numeric: tabular-nums; }
  /* Pass 5 audit P3 : prefers-contrast more -- bump ink/line pour user
     accessibility opt-in. Token-level override, transparent au reste du CSS. */
  @media (prefers-contrast: more) {
    :root { --steel: #424954; --line: #C5C9CF; --line2: #9DA3AC; }
    body.midnight { --steel: #B1B6BE; --line: #3A3F47; --line2: #535963; }
  }
  /* Accessibility focus-visible (keyboard nav). Polish DA 31/05.
     - Suppress browser default outline-on-click (ugly, non-keyboard)
     - Outline propre pour TAB navigation (keyboard) avec offset coherent palette
     - Cohorent dark/light : utilise var(--ink) qui flip automatiquement */
  :focus { outline: none; }
  :focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; border-radius: var(--r1); }
  .modetgl:focus-visible { outline-color: var(--ink); }
  /* Respect prefers-reduced-motion : users avec sensibilite vestibulaire / a11y.
     Force animations/transitions ultra-courtes (= comportement quasi-instantane).
     Polish DA 31/05. */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
  /* Pass 14 audit 6 #1 : dband sticky masquait section h1 + clipping sidebar.
     Cure Pass 15 (post-screenshot user) : non-sticky tout court. Apparait au
     top de page, scroll away naturellement. Reste capsule pill thin. */
  .dband { display:flex; align-items:center; gap:10px; padding:6px 14px; margin:0 0 var(--s35); border:1px solid var(--line3); border-radius:var(--r-pill); background:var(--panel); cursor:pointer; transition:border-color .15s,background .15s; font-size:var(--t-small); width:fit-content; }
  .dband:hover { background:color-mix(in srgb,var(--panel) 95%,transparent); }
  .dband .dd { width:9px; height:9px; border-radius:var(--r-circle); flex:none; }
  .dband.bear .dd { background:var(--bear); }
  .dband.acc .dd { background:var(--acc); } .dband.size .dd { background:var(--metal); }
  .dband .dv { font-family:var(--fd); font-weight:500; font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; flex:none; }
  .dband.bear .dv { color:var(--bear); }
  .dband.acc .dv { color:var(--acc); }
  .dband.size .dv { color:var(--metal); }
  .dband .dx { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .dband .dn { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); font-weight:600; flex:none; }
  .dband .dc { font-size:var(--t-h3); line-height:1; color:var(--steel); flex:none; transition:transform .15s,color .15s; }
  .dband:hover .dc { color:var(--ink); transform:translateX(3px); }
  .dband.bear .dx, .dband.bear .dn, .dband.bear .dc { color:var(--bear); } .dband.acc .dx, .dband.acc .dn, .dband.acc .dc { color:var(--acc); }
  .sec-super { border:1px solid var(--line2); border-radius:var(--r2); padding:var(--s1) 8px 8px; margin-bottom:16px; background:color-mix(in srgb,var(--ink) 2%,transparent); }
  .sec-superh { display:flex; align-items:baseline; justify-content:space-between; gap:var(--s3); padding:13px 12px 10px; flex-wrap:wrap; }
  .sec-supername { font-family:var(--fd); font-weight:500; font-size:var(--t-h3); letter-spacing:0; color:var(--ink); }
  .sec-subwrap { display:flex; flex-direction:column; gap:var(--s1); }
  .sec-super .sec-grp.sub { margin:0; border-left:2px solid var(--line); border-radius:0 var(--r2) var(--r2) 0; }
  .sec-super .sec-grp.sub .sec-name { font-family:var(--fd); font-weight:600; font-size:var(--t-base); color:var(--steel); letter-spacing:0; }
  body { font-family:var(--fb); font-size:var(--t-base); color:var(--ink); margin:0; display:flex; min-height:100vh; background:var(--bg); -webkit-font-smoothing:antialiased; transition:background .3s ease,color .3s ease; }
  .sidebar { width:78px; flex-shrink:0; background:transparent; border-right:1px solid var(--line); padding:20px 0; display:flex; flex-direction:column; align-items:center; position:sticky; top:0; align-self:flex-start; height:100vh; z-index:60; }
  .logo { display:flex; align-items:center; justify-content:center; margin-bottom:var(--s35); padding:2px 0 0; }
  .logo svg { width:62px; height:auto; color:var(--ink); }
  /* wordmark integre dans le SVG -- on garde la span en a11y mais visuel cache */
  .logo .wm { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  .nav { display:flex; flex-direction:column; gap:var(--s1); align-items:center; width:100%; }
  .nitem { position:relative; display:flex; align-items:center; justify-content:center; width:48px; height:48px; border-radius:var(--r3); cursor:pointer; color:var(--steel); border-left:2px solid transparent; transition:.15s; }
  .nitem svg { width:26px; height:26px; }
  .nitem:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); color:var(--ink); }
  .nitem.on { background:color-mix(in srgb,var(--id) 13%,transparent); color:var(--ink); border-left-color:var(--id); box-shadow:inset 0 0 22px -10px color-mix(in srgb,var(--id) 55%,transparent); }
  /* Emil :active feedback tactile presse sur tous les boutons interactifs */
  .nitem:active, .cta-bar button:active, .modetgl:active, .cta-chip:active { transform:scale(.97); transition:transform .08s ease-out; }
  .ctx-item:active { transform:scale(.98); }
  .nlab { position:absolute; left:58px; top:50%; transform:translateY(-50%); white-space:nowrap; background:var(--ink); color:var(--bg); border-radius:var(--r2); padding:6px 11px; font-family:var(--fb); font-size:12.5px; font-weight:500; letter-spacing:-.005em; opacity:0; pointer-events:none; transition:opacity .12s ease-out, transform .12s ease-out; z-index:1000; box-shadow:var(--elev2); will-change:opacity,transform; }
  .nitem:hover .nlab { opacity:1; transform:translateY(-50%) translateX(2px); }
  .foot { margin-top:auto; padding:var(--s3) 0 var(--s25); display:flex; flex-direction:column; align-items:center; gap:var(--s2); }
  .foot-sep { width:30px; height:1px; background:var(--line); margin:var(--s15) 0; }
  .rfoot { display:flex; flex-direction:column; align-items:center; gap:var(--s15); }
  .rfm { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); }
  .rfmacro { width:8px; height:8px; border-radius:var(--r0); }
  .dot { width:7px; height:7px; border-radius:var(--r-circle); background:var(--acc); }
  .wrap { flex:1; display:flex; flex-direction:column; min-width:0; position:relative; z-index:0; }
  /* Pass 15 audit 6 #7c — tape edge fade mask. Avant : items partiellement
     scrolles aux bords (ex: "AMD +2.5%" devenait "A 2.5%") lisaient comme
     "cut off". Mask gradient = fade au lieu de clip dur. */
  .tape { overflow:hidden; white-space:nowrap; padding:11px 0; -webkit-mask-image: linear-gradient(to right, transparent 0, black 32px, black calc(100% - 32px), transparent 100%); mask-image: linear-gradient(to right, transparent 0, black 32px, black calc(100% - 32px), transparent 100%); }
  .tape .track2 { display:inline-block; animation:scroll 60s linear infinite; will-change:transform; }
  .tape:hover .track2 { animation-play-state:paused; }
  /* Pass 5 audit P3 : pause ticker quand l'onglet est en background. CPU/battery saving. */
  body.tab-hidden .tape .track2 { animation-play-state:paused; }
  .tape .ti { font-family:var(--fm); font-size:var(--t-data2); margin:0 30px; letter-spacing:.02em; } .tape .ti b { color:var(--ink); } .tape .ti .pos { color:var(--acc); } .tape .ti .neg { color:var(--bear); }
  @keyframes scroll { from{transform:translateX(0);} to{transform:translateX(-50%);} }
  .tape8k { background:var(--tape); padding:var(--s2) 0; } .tape8k .ti .warn { color:var(--warn); } .tape8k .track2 { animation-duration:75s; }
  .statedot { width:8px; height:8px; border-radius:var(--r-circle); }
  .statedot.calm { background:var(--acc); color:var(--acc); } .statedot.warn { background:var(--warn); color:var(--warn); } .statedot.alert { background:var(--bear); color:var(--bear); }
  .main { padding:30px clamp(16px, 4vw, 52px) 54px; max-width:1340px; }
  /* Pass 3 audit cleanup #5 #6 #7 #8 : mobile responsive layout.
     Below 640px : sidebar becomes bottom tab-bar (touch-friendly position),
     main reclaims full width with clamp-padding, tables get overflow-x scroll,
     ticker tape compressed. Above 640px : current desktop layout untouched. */
  @media (max-width: 640px) {
    body { flex-direction: column; }
    .sidebar { position: fixed; bottom: 0; left: 0; width: 100%; height: auto;
               flex-direction: row; justify-content: space-around; align-items: center;
               padding: 6px 8px; border-right: 0; border-top: 1px solid var(--line);
               background: color-mix(in srgb, var(--bg) 95%, transparent);
               backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); z-index: 200; }
    .sidebar .logo { display: none; }
    .sidebar .nav { flex-direction: row; gap: 4px; flex: 1; justify-content: space-around; }
    .sidebar .nitem { width: 40px; height: 40px; border-left: 0; border-top: 2px solid transparent; }
    .sidebar .nitem.on { border-left: 0; border-top-color: var(--id); box-shadow: none; }
    .sidebar .nitem svg { width: 22px; height: 22px; }
    .sidebar .nlab { display: none; }
    .sidebar .foot { display: none; }
    .wrap { width: 100%; }
    .main { padding: 16px 16px 84px; max-width: 100%; }
    /* Tables : convertir en bloc scrollable horizontalement. Pas de clip silencieux. */
    .card table, .pad table, table.dt { display: block; max-width: 100%; overflow-x: auto;
                                         -webkit-overflow-scrolling: touch; }
    /* Ticker tape compressee. */
    .tape .ti { font-size: 13px; margin: 0 18px; }
    .tape .tklogo { width: 14px; height: 14px; }
    /* CTA bar bottom (search) : remontee au-dessus du tab-bar, centree (pas decalee du sidebar). */
    .cta-bar { bottom: 64px !important; left: 50% !important; }
    /* Tape hover pause non-tactile : auto-replay mobile. */
    .tape:hover .track2 { animation-play-state: running; }
  }
  /* Sticky page header (Stripe/Linear pattern) : reste en haut au scroll
     avec backdrop subtil. Z-index 30 sous .dband (45). Drop shadow apparaît
     quand le header est "stuck" (detecté via .stuck class JS IntersectionObserver). */
  /* Pass 16-bis screenshot user : phead reste card-like malgre fixes. Cure
     radicale : bg & backdrop totalement retires. Titre = simple texte qui
     coule au-dessus du contenu (sticky preserve pour rester visible scroll). */
  .phead { position:sticky; top:0; z-index:30; margin-bottom:var(--s2); padding:14px 0 10px; background:transparent; transition:box-shadow .2s ease-out; }
  .phead.stuck { box-shadow:var(--elev1); border-bottom-color:var(--line2); }
  .phead h1 { font-family:var(--fdis); font-weight:700; font-size:clamp(26px, 5vw, 35px); margin:0 0 6px; letter-spacing:.02em; text-transform:uppercase; color:var(--ink); }
  .phead .sub { font-family:var(--fb); font-weight:400; font-size:var(--t-small); letter-spacing:.04em; color:var(--steel); opacity:.65; transition:opacity .22s ease; }
  .phead:hover .sub { opacity:1; }
  /* Page transitions (Emil framework) : Cmd+1..9 = action keyboard 30-50x/jour
     -> doit feel instant. .26s cubic-bezier ease-out vs .42s ease (sluggish). */
  [data-page] { display:none; } [data-page].active { display:block; animation:fadein .26s cubic-bezier(.22,.61,.36,1); } @keyframes fadein { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
  /* View Transitions API (Chrome 111+, Safari 18+, Edge 111+). Override le
     fadein generique : croise old + new snapshots avec slide subtil. Linear-
     like. Fallback : fadein keyframe ci-dessus reste. */
  @supports (view-transition-name: a) {
    [data-page].active { view-transition-name: page-body; animation: none; }
    .phead h1 { view-transition-name: page-title; }
    .phead .sub { view-transition-name: page-sub; }
    ::view-transition-group(page-body) { animation-duration: .32s; animation-timing-function: var(--ease); }
    ::view-transition-old(page-body) { animation: vt-fade-out .18s var(--ease) both; }
    ::view-transition-new(page-body) { animation: vt-slide-in .32s var(--ease) both; }
    ::view-transition-old(page-title), ::view-transition-new(page-title) { animation-duration: .26s; animation-timing-function: var(--ease); }
    ::view-transition-old(page-sub),   ::view-transition-new(page-sub)   { animation-duration: .26s; animation-timing-function: var(--ease); }
    @keyframes vt-fade-out { to { opacity: 0; transform: translateY(-6px); } }
    @keyframes vt-slide-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  }
  /* Respect prefers-reduced-motion : kill toute view-transition. */
  @media (prefers-reduced-motion: reduce) {
    ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none !important; }
  }
  /* Cascade signature Vue d'ensemble : page load orchestre, blocs en revel
     staggered 60ms. Remplace le fadein page generique sur vigie uniquement.
     Direction "instrument vivant qui se decouvre" (task #37 axe 4). */
  [data-page="vigie"].active { animation:none; }
  [data-page="vigie"].active > * { animation:presage-cascade .32s var(--ease) both; }
  [data-page="vigie"].active > *:nth-child(1) { animation-delay:0ms; }
  [data-page="vigie"].active > *:nth-child(2) { animation-delay:60ms; }
  [data-page="vigie"].active > *:nth-child(3) { animation-delay:120ms; }
  [data-page="vigie"].active > *:nth-child(4) { animation-delay:180ms; }
  [data-page="vigie"].active > *:nth-child(5) { animation-delay:240ms; }
  [data-page="vigie"].active > *:nth-child(6) { animation-delay:300ms; }
  [data-page="vigie"].active > *:nth-child(7) { animation-delay:360ms; }
  [data-page="vigie"].active > *:nth-child(8) { animation-delay:420ms; }
  [data-page="vigie"].active > *:nth-child(n+9) { animation-delay:480ms; }
  @keyframes presage-cascade { from { opacity:0; transform:translateY(6px); } to { opacity:1; transform:none; } }
  .noanim [data-page="vigie"].active > * { animation:none; opacity:1; transform:none; }
  .hero { background:var(--panel); border:1px solid var(--line3); border-radius:var(--r3); padding:28px 34px; margin-bottom:26px; display:flex; align-items:center; gap:28px; flex-wrap:wrap; }
  .hero .big { font-family:var(--fdis); font-weight:800; font-size:var(--t-hero); line-height:.95; letter-spacing:-.015em; font-variant-numeric:tabular-nums; }
  .hero .big.pos { color:var(--acc); } .hero .big.neg { color:var(--bear); }
  .hero .hl { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.2em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .hero .hsub { font-size:var(--t-base); color:var(--steel); margin-top:var(--s15); }
  .distbar { flex:1; min-width:240px; } .distline { display:flex; height:8px; border-radius:var(--r1); overflow:hidden; cursor:help; }
  .distline .g { background:var(--acc); transition:opacity .15s ease-out; } .distline .r { background:var(--bear); transition:opacity .15s ease-out; }
  .distline:hover .g { opacity:.7; } .distline:hover .r { opacity:.7; }
  .distline .g:hover, .distline .r:hover { opacity:1 !important; }
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:var(--s4); margin-bottom:26px; }
  .kpi { background:var(--panel); border:1px solid var(--line); border-radius:var(--r3); padding:18px 24px; transition:border-color .18s ease-out; }
  .kl { display:block; font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .kv { font-family:var(--fdis); font-weight:700; font-size:var(--t-h1); letter-spacing:-.01em; line-height:1; font-variant-numeric:tabular-nums; }
  .kv, .gvm, .big { color:var(--c, var(--ink)); }
  .kv.bear { --c:var(--bear); } .kv.acc { --c:var(--acc); } .kv.warn { --c:var(--warn); } .kv.id { --c:var(--id); }
  .kv.acc { color:var(--acc); } .kv.negc { color:var(--bear); } .kv.warn { color:var(--warn); } .kv.hot { color:var(--warn); } .kv.danger { color:var(--bear); } .kv.calm { color:var(--acc); }
  .kd { display:block; font-size:var(--t-data); color:var(--steel); margin-top:var(--s15); }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:30px; align-items:start; }
  /* Move #4 DNA : colhead .a recede (font-size 12 + opacity .55) pour reduire cognitive load.
     Reveal-on-hover du parent (.colhead:hover .a opacity 1) = recompense l'attention. */
  /* CANONIQUE 02/06 user pref Image #8 : .colhead aligne sur .strat-sh ->
     uppercase letterspaced steel + divider line ::after qui remplit a droite.
     Ancien style (22px ink-bold) abandonne -- trop dominant, casse l'unite
     visuelle avec strat-sh / th-grp / dba-sh / vigie-sh. */
  .colhead { display:flex; align-items:center; gap:var(--s3); margin:0 2px var(--s3); padding-left:0; font-family:var(--fm); font-weight:500; font-size:var(--t-data2); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); }
  .colhead::after { content:""; flex:1; height:1px; background:var(--line); }
  .colhead .t { font-family:inherit; font-weight:inherit; font-size:inherit; letter-spacing:inherit; color:inherit; text-transform:inherit; }
  .colhead .a { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); opacity:.55; text-transform:none; letter-spacing:.01em; }
  /* Sub line inside .card (PAS .phead) : data caption, doit lire SOUS le titre colhead. */
  .card .sub { font-family:var(--fb); font-size:var(--t-small); color:var(--steel); letter-spacing:.02em; }
  .colhead:hover .a { opacity:1; }
  .colhead.tight { margin-top:var(--s15); } /* 6px : aerer un peu apres un bloc voisin */
  .colhead.spaced { margin-top:var(--s4); } /* 20px : separateur de section, sous-titre marque */
  .sec-cols { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:var(--s3); padding:2px 16px 9px; font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); border-bottom:1px solid var(--line); margin-bottom:var(--s3); }
  .sec-cols .num { text-align:right; }
  .sec-grp { margin-bottom:var(--s35); }
  /* Pass 6 audit : sec-h grille IDENTIQUE a sec-row/sec-cols pour vrai alignement
     vertical des colonnes (n / € / $ / % / Day / P&L) sur la ligne resume. */
  .sec-h { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:var(--s3); align-items:baseline; margin:0 4px 9px; cursor:pointer; user-select:none; padding:6px 16px; border-radius:var(--r2); transition:background .12s; }
  .sec-h .sec-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:8px; font-weight:400; }
  .sec-h .num.sec-agg { text-align:right; color:var(--ink); font-variant-numeric:tabular-nums; font-family:var(--fm); }
  .sec-h:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); }
  .sec-name { font-family:var(--fd); font-weight:500; font-size:var(--t-h3); color:var(--ink); display:flex; align-items:center; gap:9px; }
  .sec-name::before { content:""; width:6px; height:6px; border-radius:var(--r0); background:var(--id); }
  .sec-name::after { content:"\\25B8"; margin-left:8px; color:var(--steel); font-size:var(--t-data); transition:transform .18s ease; display:inline-block; }
  .sec-grp.open .sec-name::after { transform:rotate(90deg); }
  .sec-meta { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); white-space:nowrap; }
  .sec-pl.pos { color:var(--acc); } .sec-pl.neg { color:var(--bear); }
  .sec-rows { display:flex; flex-direction:column; gap:1px; max-height:0; overflow:hidden; opacity:0; transition:max-height .28s ease, opacity .18s ease, margin .28s ease; }
  .sec-grp.open .sec-rows { max-height:2000px; opacity:1; margin-bottom:var(--s2); }
  .sec-row { display:grid; grid-template-columns:1fr 92px 96px 58px 72px 78px; gap:var(--s3); align-items:center; padding:var(--s2) 16px; border-radius:var(--r2); font-family:var(--fm); font-size:var(--t-base); cursor:pointer; transition:background .12s; }
  .sec-row:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); }
  .sec-row .num { text-align:right; color:var(--ink); font-variant-numeric:tabular-nums; }
  .sec-row .num.pos, .sec-pl.pos { color:var(--acc); } .sec-row .num.neg { color:var(--bear); }
  .sec-tk { font-weight:600; color:var(--ink); }
  .sec-nm { color:var(--steel); font-family:var(--fb); font-size:var(--t-data); margin-left:9px; font-weight:400; }
  /*CHER*/
  /* Card hover elevation (Linear/Stripe premium) : subtle shadow + translateY */
  .card, .kpi { transition:transform .18s ease-out, box-shadow .18s ease-out, border-color .15s ease-out; }
  /* DNA v2 : carte = bordure OU ombre, jamais les deux. On garde la bordure
     subtile au repos ET au hover (ombre + transform retires). Hover signal
     via border-color shift seul. */
  .card:hover, .kpi:hover { border-color:var(--line2); }
  .tape .ti::after { content:"·"; margin-left:30px; color:var(--steel); opacity:.4; }
  /*METAL2*/
  .card, .kpi, .hero, .pfcard { border-top:1px solid color-mix(in srgb,var(--ink) 16%,var(--line)); }
  .th-grid { display:grid; grid-template-columns:1fr 1fr; gap:13px; margin-bottom:var(--s15); }
  .th-anchor { grid-column:1/-1; margin-top:var(--s2); padding:var(--s2) 11px; border-radius:var(--r2); font-family:var(--fb); font-size:var(--t-data2); line-height:1.5; color:var(--ink); border-left:2px solid var(--id); }
  .th-anchor.acc { border-left-color:var(--acc); background:color-mix(in srgb,var(--acc) 7%,transparent); }
  .th-anchor.warn { border-left-color:var(--warn); background:color-mix(in srgb,var(--warn) 9%,transparent); }
  /*THEME-ICO*/
  .modetgl .ico-sun { display:none; } body.midnight .modetgl .ico-moon { display:none; } body.midnight .modetgl .ico-sun { display:inline-block; }
  /*DVAL-STATE*/
  .dval.calm { color:var(--acc); } .dval.warn { color:var(--warn); } .dval.danger { color:var(--bear); } .dval.mute { color:var(--steel); }
  /* DNA v2 : padding ample 24-32px (charte instrument). */
  .card { background:var(--panel); border:1px solid var(--line); border-radius:var(--r3); padding:18px 26px; transition:border-color .18s ease-out; }
  .card.pad { padding:26px 28px; }
  .line { display:flex; justify-content:space-between; padding:9px 0; border-bottom:1px solid var(--line); font-size:var(--t-base); } .line:last-child { border-bottom:none; }
  .mono { font-family:var(--fm); font-weight:600; color:var(--ink); } .mono.pos { color:var(--acc); } .mono.neg { color:var(--bear); }
  .gauge { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:16px 20px; margin-bottom:15px; }
  .ghead { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:11px; } .ghead .gl { font-family:var(--fb); font-weight:600; font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); } .ghead .gv { font-family:var(--fm); font-weight:500; font-size:var(--t-h2); letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .gtrack { position:relative; height:6px; border-radius:var(--r0); background:linear-gradient(90deg, var(--acc), var(--warn) 52%, var(--bear)); }
  .glab { margin-top:9px; font-size:var(--t-data); color:var(--steel); display:flex; justify-content:space-between; font-family:var(--fm); letter-spacing:.08em; }
  .row { padding:9px 0; border-bottom:1px solid var(--line); opacity:0; animation:fade .45s ease forwards; } .row:last-child { border-bottom:none; }
  .row[data-tk] { cursor:pointer; transition:background .15s ease-out, padding-left .15s ease-out; } .row[data-tk]:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); padding-left:4px; }
  .rt { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; gap:8px; } .tk { font-family:var(--fm); font-weight:600; font-size:var(--t-base); display:inline-flex; align-items:center; gap:7px; }
  /* Sprint 3 logos tickers (Clearbit + fallback initiale, cf shared/ticker_logos.py) */
  .tklogo { width:18px; height:18px; border-radius:var(--r-circle); object-fit:contain; background:#fff; padding:2px; vertical-align:middle; flex-shrink:0; box-sizing:border-box; border:1px solid var(--line); margin-right:6px; }
  .tklogo.tkfb { display:inline-flex; align-items:center; justify-content:center; background:var(--steel); color:var(--bg); font-family:var(--fm); font-size:var(--t-mini); font-weight:700; padding:0; border:none; }
  .tape .tklogo { width:16px; height:16px; padding:1px; margin-right:5px; }
  .lp-h .tklogo { width:32px; height:32px; padding:3px; margin-right:10px; align-self:center; }
  .lp-h .tklogo.tkfb { font-size:var(--t-base); }
  .lp-h { align-items:center !important; }
  /* === Page Star : panneau hero "verdict 3 secondes" par page === */
  /* User feedback 01/06 : un panneau clair, bien espace, hierarchie typo
     restreinte (label uppercase steel + value 24-28px ink + caption steel),
     3 strates separees par hairlines, padding genereux (32-40px). */
  /* Animation entry fade-in sur Star (Polish 01/06) : subtle premium feel
     a la TR/Linear. 280ms ease, opacity + translate-y 8px. Anti-double-fire
     via .noanim gate (cf dashboard_anim_session_gate). */
  /* page-star kill 02/06 user "degage moi ces panneaux horribles".
     EXCEPTIONS :
       - Vigie/Overview : full hero card (valeur PF + note PF)
       - Urgence/Alerts : strate 1 seule (macro state + frise gauge) sans
         cadre lourd. User 02/06 "j'aimais le principe de la gauge". */
  .page-star { display:none !important; }
  [data-page="vigie"] .page-star { display:block !important; background:var(--panel); border:1px solid var(--line); border-radius:var(--r3); padding:24px 28px; margin-bottom:var(--s4); }
  [data-page="urgence"] .page-star { display:block !important; background:transparent; border:none; padding:0; margin-bottom:var(--s4); }
  [data-page="urgence"] .page-star .ps-strate:not(:first-child) { display:none !important; }
  [data-page="urgence"] .page-star .ps-strate:first-child { border-top:none; padding:0; }
  [data-page="vigie"] .page-star .ps-strate { display:block; padding:14px 0; gap:0; }
  [data-page="vigie"] .page-star .ps-strate:first-child { padding-top:0; }
  [data-page="vigie"] .page-star .ps-strate:last-child { padding-bottom:0; }
  [data-page="vigie"] .page-star .ps-strate + .ps-strate { border-top:1px solid var(--line); }
  /* Pass 6 audit hero rebalance : 1.6fr / 1fr (gauche dense, droite focalisee).
     Grade module : letter + score reunis dans une capsule subtile (border + bg
     tint), elimine le "decroche visuel" du 40px vs 22px sans gap. */
  [data-page="vigie"] .page-star .ps-hero-row { display:grid; grid-template-columns:1.6fr 1fr; gap:32px; align-items:start; }
  [data-page="vigie"] .page-star .ps-hero-left, [data-page="vigie"] .page-star .ps-hero-right { display:block; }
  [data-page="vigie"] .page-star .ps-lbl { display:block; margin-bottom:8px; font-size:var(--t-meta); letter-spacing:.10em; }
  /* Pass 7 audit number determinism : as-of timestamp etiquette le snapshot.
     User comprend "this is at 14:32, refresh for newer" plutot que de voir
     yfinance refresh silencieuse comme jitter. */
  [data-page="vigie"] .page-star .ps-asof { font-family:var(--fm); font-size:var(--t-fine); letter-spacing:.06em; color:var(--steel); text-transform:none; font-weight:400; margin-left:6px; }
  [data-page="vigie"] .page-star .ps-macro-row { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  [data-page="vigie"] .page-star .ps-val { font-size:var(--t-h1); font-family:var(--fdis); font-variant-numeric:tabular-nums; font-weight:700; line-height:1.1; letter-spacing:-.01em; }
  [data-page="vigie"] .page-star .ps-val[style*="font-size:var(--t-h1)"] { font-size:var(--t-h1) !important; }
  [data-page="vigie"] .page-star .ps-val[style*="font-size:var(--t-h3)"] { font-size:var(--t-h3) !important; }
  [data-page="vigie"] .page-star .ps-sub-lien { font-family:var(--fm); font-size:var(--t-small); color:var(--steel); margin-top:8px; }
  [data-page="vigie"] .page-star .ps-grade-row { display:flex; align-items:center; gap:14px; margin-top:6px; padding:12px 16px; background:color-mix(in srgb, var(--ink) 3%, transparent); border:1px solid var(--line); border-radius:var(--r2); }
  [data-page="vigie"] .page-star .ps-grade-letter { font-size:38px; line-height:1; }
  [data-page="vigie"] .page-star .ps-grade-num { font-size:var(--t-h3); margin-bottom:6px; }
  [data-page="vigie"] .page-star .ps-grade-max { font-size:var(--t-mini); }
  [data-page="vigie"] .page-star .ps-grade-score { flex:1; min-width:120px; }
  [data-page="vigie"] .page-star .ps-grade-bar { height:6px; background:var(--line); border-radius:var(--r0); overflow:hidden; }
  [data-page="vigie"] .page-star .ps-grade-fill { height:100%; transition:width .3s ease; }
  [data-page="vigie"] .page-star .ps-grade-fill.acc { background:var(--acc); }
  [data-page="vigie"] .page-star .ps-grade-fill.warn { background:var(--warn); }
  [data-page="vigie"] .page-star .ps-grade-fill.bear { background:var(--bear); }

  /* Concentration page-star : verdict + grid 3-cell + foot cluster */
  [data-page="concentration"] .page-star .ps-strate { display:block; padding:14px 0; gap:0; }
  [data-page="concentration"] .page-star .ps-strate:first-child { padding-top:0; }
  [data-page="concentration"] .page-star .ps-strate:last-child { padding-bottom:0; }
  [data-page="concentration"] .page-star .ps-strate + .ps-strate { border-top:1px solid var(--line); }
  [data-page="concentration"] .page-star .ps-lbl { display:block; margin-bottom:8px; font-size:var(--t-meta); letter-spacing:.10em; }
  [data-page="concentration"] .page-star .ps-macro-row { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  [data-page="concentration"] .page-star .ps-val { font-size:var(--t-h2); font-family:var(--fm); font-variant-numeric:tabular-nums; font-weight:500; line-height:1.15; }
  [data-page="concentration"] .page-star .ps-cap { font-size:var(--t-small); margin-top:4px; }
  [data-page="concentration"] .page-star .ps-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:28px; }
  [data-page="concentration"] .page-star .ps-cell { display:block; }
  [data-page="concentration"] .page-star .ps-cell .ps-val { font-size:var(--t-h2); }
  [data-page="concentration"] .page-star .ps-foot { font-size:var(--t-mini); padding-top:4px; }
  .page-star .ps-strate { padding:6px 0; display:flex; flex-wrap:wrap; align-items:baseline; gap:18px; }
  .page-star .ps-lbl { font-family:var(--fb); font-size:var(--t-meta); letter-spacing:.06em; text-transform:uppercase; color:var(--steel); margin:0; font-weight:500; display:inline-block; }
  .ps-tag-explor { display:inline-block; margin-left:6px; padding:1px 6px; font-size:var(--t-fine); font-weight:500; letter-spacing:.06em; text-transform:uppercase; color:var(--steel); border:1px solid var(--line2); border-radius:var(--r1); font-family:var(--fm); cursor:help; }
  /* ps-val : inline, monosbre, plus de hero. Accent applique seulement
     quand .acc/.bear/.warn explicite. */
  .page-star .ps-val { font-family:var(--fm); font-size:var(--t-base); font-weight:500; color:var(--ink); line-height:1.4; font-variant-numeric:tabular-nums; letter-spacing:-.005em; }
  .page-star .ps-val.bear { color:var(--bear); }
  .page-star .ps-val.acc { color:var(--acc); }
  .page-star .ps-val.warn { color:var(--warn); }
  /* Color helpers generiques (applicable a n'importe quel inline element) */
  .acc-c, b.acc { color:var(--acc); }
  .warn-c, b.warn { color:var(--warn); }
  .bear-c, b.bear { color:var(--bear); }
  .page-star .ps-cap { font-family:var(--fb); font-size:var(--t-mini); color:var(--steel); margin:0; line-height:1.4; display:inline; }
  .page-star .ps-cap::before { content:"\\00a0\\00b7\\00a0"; color:var(--steel); opacity:.5; }
  .page-star .ps-macro-row { display:inline-flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
  .page-star .ps-macro-meta { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); }
  /* Frise gauge : stable -> crise, GREEN gauche (calm) -> RED droite (crise).
     Wrap frise + labels dans ps-frise-wrap pour aligner les ticks. */
  .page-star .ps-frise-wrap { flex:0 0 260px; min-width:200px; display:block; margin-top:10px; }
  .page-star .ps-frise { height:4px; border-radius:var(--r0); background:linear-gradient(90deg,color-mix(in srgb,var(--acc) 60%,transparent),color-mix(in srgb,var(--warn) 55%,transparent) 50%,color-mix(in srgb,var(--bear) 65%,transparent)); position:relative; }
  /* #91 sig viz : ps-frise-mark adopte le 4-pointed star canonical (meme
     pattern que .axis-mark) pour identite visuelle unifiee. Plus de circle
     dot generique. */
  .page-star .ps-frise-mark { position:absolute; top:50%; width:24px; height:13px;
    background-color:var(--ink);
    -webkit-mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    transform:translate(-50%,-50%); z-index:2; animation: axis-mark-slide-in .9s cubic-bezier(.2,.8,.2,1) both; }
  .noanim .page-star .ps-frise-mark { animation: none; }
  .page-star .ps-frise-labs { display:grid; grid-template-columns:repeat(4, 1fr); font-family:var(--fm); font-size:var(--t-fine); color:var(--steel); margin-top:8px; letter-spacing:.06em; text-transform:uppercase; cursor:help; }
  .page-star .ps-frise-labs span { text-align:center; }
  .page-star .ps-frise-labs span:first-child { text-align:left; }
  .page-star .ps-frise-labs span:last-child { text-align:right; }
  /* Tally indicateurs par phase -- responsive feedback de ce qui pousse la frise. */
  .page-star .ps-frise-tally { display:grid; grid-template-columns:repeat(4, 1fr); font-family:var(--fm); font-size:var(--t-meta); color:var(--steel); margin-top:6px; gap:6px; cursor:help; letter-spacing:.02em; }
  .page-star .ps-tally-cell { display:flex; align-items:center; gap:5px; justify-content:center; }
  .page-star .ps-frise-tally .ps-tally-cell:first-child { justify-content:flex-start; }
  .page-star .ps-frise-tally .ps-tally-cell:last-child { justify-content:flex-end; }
  .page-star .ps-tally-dot { width:7px; height:7px; border-radius:var(--r-circle); flex-shrink:0; }
  .page-star .ps-tally-dot.ph1 { background:var(--acc); }
  .page-star .ps-tally-dot.ph2 { background:color-mix(in srgb,var(--warn) 70%,var(--acc) 30%); }
  .page-star .ps-tally-dot.ph3 { background:var(--warn); }
  .page-star .ps-tally-dot.ph4 { background:var(--bear); }
  /* Top stressor : nomme le pire indicateur quand frise >= alert. */
  .page-star .ps-stressor { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); margin-top:8px; letter-spacing:.02em; }
  .page-star .ps-stressor b { font-weight:500; }
  .page-star .ps-stressor b.bear { color:var(--bear); }
  .page-star .ps-stressor b.warn { color:var(--warn); }
  /* Delta vs reading precedente -- direction du score. */
  .page-star .ps-delta { font-family:var(--fm); font-size:var(--t-mini); margin-left:4px; font-weight:500; }
  .page-star .ps-delta.bear { color:var(--bear); }
  .page-star .ps-delta.acc { color:var(--acc); }
  /* ps-grid : flex inline row au lieu de 3-col grid card */
  .page-star .ps-grid { display:flex; flex-wrap:wrap; gap:24px; margin:0; }
  .page-star .ps-cell { display:flex; align-items:baseline; gap:6px; }
  .page-star .ps-cell .ps-lbl { margin:0; }
  .page-star .ps-cell .ps-val { font-size:var(--t-data2); }
  .page-star .ps-foot { font-family:var(--fm); font-size:var(--t-meta); color:var(--steel); padding-top:4px; opacity:.8; }
  .page-star .ps-foot b { color:var(--ink); font-weight:500; }
  /* Hero row Vigie (valeur + grade) : inline aussi, sober */
  .page-star .ps-hero-row { display:flex; align-items:baseline; gap:24px; flex-wrap:wrap; }
  .page-star .ps-hero-left, .page-star .ps-hero-right { min-width:0; display:flex; align-items:baseline; gap:10px; }
  .page-star .ps-grade-row { display:inline-flex; align-items:center; gap:10px; }
  .page-star .ps-grade-letter { font-family:var(--fm); font-size:var(--t-h2); font-weight:500; line-height:1; flex-shrink:0; color:var(--ink); }
  .page-star .ps-grade-letter.acc { color:var(--acc); }
  .page-star .ps-grade-letter.warn { color:var(--warn); }
  .page-star .ps-grade-letter.bear { color:var(--bear); }
  .page-star .ps-grade-score { display:inline-flex; align-items:baseline; gap:6px; min-width:0; }
  .page-star .ps-grade-num { font-family:var(--fm); font-size:var(--t-data); font-weight:500; color:var(--ink); margin:0; font-variant-numeric:tabular-nums; }
  .page-star .ps-grade-max { font-family:var(--fm); font-size:var(--t-meta); color:var(--steel); font-weight:400; }
  /* Sub-lien / val-delta sous le hero : compact inline */
  .page-star .ps-sub-lien { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); margin:6px 0 0; }
  .page-star .ps-sub-lien b { color:var(--ink); font-weight:500; }
  .page-star .ps-grade-bar { height:6px; background:color-mix(in srgb,var(--line) 90%,transparent); border-radius:var(--r0); overflow:hidden; }
  .page-star .ps-grade-fill { height:100%; transition:width .3s ease; }
  .page-star .ps-grade-fill.acc { background:var(--acc); }
  .page-star .ps-grade-fill.warn { background:var(--warn); }
  .page-star .ps-grade-fill.bear { background:var(--bear); }
  /* Ligne sous Valeur portefeuille (sub-info en lien typographique) */
  .page-star .ps-sub-lien { font-family:var(--fb); font-size:var(--t-base); color:var(--steel); margin-top:8px; }
  .page-star .ps-sub-lien b { color:var(--ink); font-weight:500; }
  .page-star .ps-sub-lien b.acc { color:var(--acc); }
  /* Sparkline hero 30j (Robinhood/TR pattern) inline avec PnL */
  .ps-spark { margin-left:14px; vertical-align:middle; opacity:.85; }
  .ps-spark-wrap { position:relative; display:inline-block; vertical-align:middle; cursor:crosshair; }
  .ps-spark-wrap:hover .ps-spark { opacity:1; }
  .ps-spark-wrap:hover .spk-cross, .ps-spark-wrap:hover .spk-cur { opacity:1 !important; transition:opacity .12s ease-out; }
  .spk-tip { position:absolute; bottom:calc(100% + 8px); transform:translateX(-50%); background:var(--ink); color:var(--bg); padding:5px 10px; border-radius:var(--r1); font-family:var(--fm); font-size:var(--t-data); font-weight:500; white-space:nowrap; pointer-events:none; z-index:60; box-shadow:var(--elev1); }
  .spk-tip .tip-val { font-weight:600; }
  .spk-tip .tip-date { opacity:.6; margin-left:6px; font-weight:400; }
  /* Sparkline macro composite 30 derniers points sous la frise stress */
  .ps-macro-spark { display:block; margin-top:8px; opacity:.7; width:100%; height:auto; }
  /* Trend delta vs J-1 (subtle inline next to PnL caption) */
  .ps-trend-delta { font-family:var(--fm); font-size:var(--t-data); font-weight:500; margin-left:10px; letter-spacing:.03em; opacity:.85; }
  .ps-trend-delta.acc { color:var(--acc); }
  .ps-trend-delta.bear { color:var(--bear); }
  /* === Print stylesheet : export PDF propre (Stars + contenu, retirer chrome) */
  @media print {
    body { background:#fff !important; color:#000 !important; }
    .sidebar, .tape, .tape8k, .cta-bar, .cta-modal, .llm-badge, #loupe, .modetgl { display:none !important; }
    main { margin-left:0 !important; padding:0 !important; }
    .phead { position:static !important; background:#fff !important; backdrop-filter:none !important; box-shadow:none !important; border-bottom:1px solid #ccc !important; }
    .page-star, .card, .kpi, .gauge, .dba-card { animation:none !important; box-shadow:none !important; page-break-inside:avoid; }
    [data-page] { display:block !important; animation:none !important; page-break-after:auto; }
    [data-page]:not(.active) { display:none !important; }
    a { color:inherit !important; text-decoration:none !important; }
    .tklogo { filter:grayscale(0); }
    .ps-frise, .gtrack { background:#eee !important; border:1px solid #ccc !important; }
    .ps-spark, .ps-macro-spark { opacity:1 !important; }
  }
  /* Sprint 4 CTA flottants bas (TR/RH-inspired) : 3 pills sticky bottom */
  /* CTA bar : pill clair distinct du body via border marquee + shadow forte.
     Centree dans zone main (compense sidebar 78px). */
  /* Pass 14 audit 6 #7 : CTA bottom-center overlap content. Move bottom-right
     coin moins intrusif. Reste a 78+22=100px du bord gauche pour eviter sidebar. */
  .cta-bar { position:fixed; bottom:22px; right:64px; background:var(--panel); border:1px solid var(--line2); border-radius:var(--r-pill); padding:6px; display:flex; gap:2px; z-index:50; box-shadow:var(--elev3), inset 0 1px 0 rgba(255,255,255,.8); }
  .cta-bar button:hover { background:color-mix(in srgb,var(--ink) 6%,transparent); }
  body.midnight .cta-bar { background:var(--panel); border-color:var(--line2); box-shadow:var(--elev3), inset 0 1px 0 rgba(255,255,255,.06); }
  body.midnight .cta-bar button { color:var(--ink); }
  body.midnight .cta-bar button:hover { background:rgba(255,255,255,.06); }
  body.midnight .cta-bar kbd { background:rgba(255,255,255,.12); color:color-mix(in srgb,var(--ink) 70%,transparent); }
  .cta-bar button { font-family:var(--fb); font-size:var(--t-base); font-weight:500; color:var(--ink); background:transparent; border:none; padding:10px 18px; border-radius:var(--r-pill); cursor:pointer; display:flex; align-items:center; gap:8px; transition:background .15s,color .15s; }
  .cta-bar button:hover { background:color-mix(in srgb,var(--ink) 6%,transparent); transition:background .12s ease-out; }
  .cta-bar button.act { background:var(--ink); color:var(--bg); }
  .cta-bar kbd { font-family:var(--fm); font-size:var(--t-small); padding:1px 5px; background:color-mix(in srgb,var(--ink) 10%,transparent); border-radius:var(--r1); opacity:.7; border:none; }
  .cta-bar button.act kbd { background:color-mix(in srgb,var(--bg) 25%,transparent); color:var(--bg); }
  /* Search modal */
  .cta-modal { position:fixed; inset:0; background:rgba(0,0,0,.4); z-index:100; display:none; align-items:flex-start; justify-content:center; padding-top:14vh; opacity:0; transition:opacity .2s ease; }
  .cta-modal.open { display:flex; opacity:1; }
  .cta-modal-inner { animation:modalIn .24s ease-out; }
  @keyframes modalIn { from { opacity:0; transform:translateY(-12px); } to { opacity:1; transform:translateY(0); } }
  @media (prefers-reduced-motion: reduce) { .cta-modal, .cta-modal-inner { animation:none; transition:none; } }
  .cta-modal-inner { background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); width:min(560px,92vw); max-height:64vh; overflow:hidden; display:flex; flex-direction:column; box-shadow:var(--elev3); }
  .cta-search-input { width:100%; padding:18px 24px; font-family:var(--fb); font-size:var(--t-h3); background:transparent; border:none; border-bottom:1px solid var(--line); color:var(--ink); outline:none; box-sizing:border-box; }
  .cta-search-input:focus-visible { outline:2px solid var(--ink); outline-offset:2px; border-radius:var(--r1); }
  .cta-search-results { max-height:46vh; overflow-y:auto; padding:4px; }
  /* Chips sector filter (search modal enrichi) */
  .cta-search-chips { display:flex; gap:6px; padding:8px 16px 4px; flex-wrap:wrap; border-bottom:1px solid color-mix(in srgb,var(--line) 70%,transparent); }
  .cta-chip { font-family:var(--fb); font-size:var(--t-data); font-weight:500; padding:5px 11px; border-radius:var(--r3); background:transparent; border:1px solid var(--line); color:var(--steel); cursor:pointer; transition:.12s; }
  .cta-chip:hover { background:color-mix(in srgb,var(--ink) 5%,transparent); color:var(--ink); }
  .cta-chip.act { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  .cta-chip-n { opacity:.6; font-size:var(--t-small); margin-left:3px; }
  /* Tag "recent" sur les resultats */
  .cta-tag { margin-left:auto; font-family:var(--fm); font-size:var(--t-small); padding:2px 7px; border-radius:var(--r2); background:color-mix(in srgb,var(--warn) 18%,transparent); color:var(--warn); text-transform:uppercase; letter-spacing:.06em; font-weight:600; }
  .cta-result { padding:10px 16px; display:flex; align-items:center; gap:10px; cursor:pointer; border-radius:var(--r2); }
  .cta-result:hover, .cta-result.sel { background:color-mix(in srgb,var(--ink) 6%,transparent); }
  .cta-result .ctk { font-family:var(--fm); font-weight:600; color:var(--ink); }
  .cta-result .cnm { color:var(--steel); font-size:var(--t-base); }
  .cta-result .tklogo { width:24px; height:24px; padding:2px; margin-right:4px; }
  .cta-result .tklogo.tkfb { font-size:var(--t-data); }
  /* Cmd+K highlight match : bold + couleur accent --data sur les chars matches.
     Donne le retour visuel signature Linear/VSCode sur la pertinence. */
  .cta-result .ctk b, .cta-result .cnm b { color:var(--data); font-weight:700; font-style:normal; }
  .cta-result.sel .ctk b, .cta-result.sel .cnm b { color:var(--data); }
  .tag { font-family:var(--fm); font-weight:600; font-size:var(--t-data); padding:3px 9px; border-radius:var(--r1); }
  .tag.up { color:var(--acc); background:color-mix(in srgb, var(--acc) 12%, transparent); } .tag.acc2 { color:var(--acc2); background:color-mix(in srgb, var(--acc2) 12%, transparent); }
  .tag.down,.tag.danger { color:var(--bear); background:color-mix(in srgb, var(--bear) 13%, transparent); } .tag.warn { color:var(--warn); background:color-mix(in srgb, var(--warn) 14%, transparent); } .tag.calm { color:var(--steel); background:color-mix(in srgb, var(--steel) 12%, transparent); } .tag.mute { color:var(--steel); background:color-mix(in srgb, var(--steel) 12%, transparent); }
  /* Axe gradient evolutif smooth (red -> steel -> green) du DNA original.
     Target tick a 66.67% (zone overshoot 66.67..100%). Le marker peut
     occuper la zone droite, mais le DEGRADE reste continu (pas de zone
     gold rupture) -- user "gauges evolutives etaient bien". */
  .axis { position:relative; height:5px; border-radius:var(--r0); margin:var(--s35) 0 6px;
    background:linear-gradient(90deg,
      var(--bear) 0%,
      color-mix(in srgb,var(--bear) 45%,transparent) 22%,
      color-mix(in srgb,var(--steel) 35%,transparent) 44%,
      color-mix(in srgb,var(--acc) 50%,transparent) 66.67%,
      var(--acc) 100%); }
  .axis-target-tick { position:absolute; top:-3px; width:2px; height:11px; background:var(--ink); opacity:.6; border-radius:var(--r0); pointer-events:none; }
  /* Row-axis : variant compact pour cellules de table (Positions broker). */
  .axis.row-axis { width:120px; height:4px; margin:0; }
  .axis.row-axis .axis-target-tick { top:-2px; height:8px; }
  td.row-gauge { padding:6px 8px; min-width:140px; }
  /* Sizebar redesign 02/06 : target a 50% = zone verte optimale.
     Under-target = rouge (under-sized, need bump). Over-cap = rouge
     (over-sized, need trim). Marker dans la zone verte = bonne taille,
     marker dans le rouge = correction urgente. */
  .axis.sizebar { background:linear-gradient(90deg,
    var(--bear) 0%,
    color-mix(in srgb,var(--bear) 55%,transparent) 20%,
    color-mix(in srgb,var(--steel) 35%,transparent) 38%,
    var(--acc) 50%,
    color-mix(in srgb,var(--acc) 55%,transparent) 62%,
    color-mix(in srgb,var(--warn) 50%,transparent) 80%,
    var(--bear) 100%); }
  .axis::before, .axis::after { content:""; position:absolute; top:-3px; width:1px; height:10px; background:var(--line2); }
  .axis::before { left:0; } .axis::after { right:0; }
  .axis-mark { position:absolute; top:50%; width:32px; height:15px;
    background-color:var(--ink);
    -webkit-mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    transform:translate(-50%,-50%); z-index:2; transition:left .6s cubic-bezier(.2,.8,.2,1); }
  .axis-mark.pos { background-color:var(--acc); }
  .axis-mark.neg, .axis-mark.danger { background-color:var(--bear); }
  /* #91 sig viz : marker slide-in depuis 0% au load 1ere visite. Le marker
     glisse depuis l'entree (gauche) jusqu'a sa position courante -- preuve
     visuelle de la trajectoire. .noanim (2e visite) skip. */
  @keyframes axis-mark-slide-in {
    from { left: 0% !important; opacity: 0; }
    to   { opacity: 1; }
  }
  .axis-mark { animation: axis-mark-slide-in .9s cubic-bezier(.2,.8,.2,1) both; }
  .noanim .axis-mark { animation: none; }
  @media (prefers-reduced-motion: reduce) {
    .axis-mark { animation: none !important; }
  }
  .axis-mark.warn { background-color:var(--warn); }
  .axis-mark.mute { background-color:var(--steel); opacity:.6; }
  .axis-tick { position:absolute; top:-3px; width:1px; height:7px; background:var(--line2); }
  .axis-tick.strong { top:-4px; height:9px; background:var(--ink); opacity:.55; }
  .axis-tick.dash { border-left:1px dashed var(--steel); background:transparent; opacity:.6; }
  .noanim .axis-mark { transition:none !important; }

  /* Track record refonte W14 (31/05) : axes = primitive, filets fins, encre,
     curve fiabilite SVG cadre vide + diagonale qui se trace au load. */
  .tr-card .tr-metric { padding:var(--s35) 0; border-bottom:1px solid var(--line); }
  .tr-card .tr-metric:last-of-type { border-bottom:none; }
  .tr-card .tr-mlabel { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s2); flex-wrap:wrap; }
  .tr-card .tr-mname { font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .tr-card .tr-mval { font-family:var(--fdis); font-weight:700; font-size:var(--t-h3); color:var(--ink); letter-spacing:-.01em; }
  .tr-card .tr-mvsep { color:var(--steel); padding:0 2px; }
  .tr-card .tr-munit { font-size:var(--t-caption); color:var(--steel); }
  .tr-card .tr-axis-brier { background:linear-gradient(to right, var(--acc) 0%, var(--acc) 40%, var(--line2) 40%, var(--bear) 100%); }
  .tr-card .tr-axref { position:absolute; top:-3px; bottom:-3px; width:1px; background:var(--ink); opacity:.45; }
  .tr-card .tr-axref::after { content:""; position:absolute; top:-4px; left:-3px; width:7px; height:1px; background:var(--ink); opacity:.55; }
  .tr-card .tr-mfoot { display:flex; justify-content:space-between; margin-top:var(--s2); font-size:var(--t-caption); }
  .tr-card .tr-mfoot .mono { color:var(--ink2); }
  .tr-card .tr-verdict { color:var(--steel); }
  .tr-card .tr-rsvg { display:block; width:100%; height:96px; margin:var(--s2) 0; }
  /* tr-diag : diagonale pointillée gris pâle = référence "calibration parfaite",
     pas une trace data. La couleur/style distincte signale que c'est un guide
     visuel, pas une mesure. Cure 15/06 data-honesty. */
  .tr-card .tr-diag { stroke:var(--steel); stroke-width:.6; fill:none; stroke-dasharray:2,2; opacity:.55; }
  .tr-card .tr-frame { stroke:var(--line2); stroke-width:.5; fill:none; }
  /* tr-rempty : bg gris pâle + texte annotation quand N < MIN_CONCLUSIF.
     Le viz lui-même dit "vide" sans qu'on ait à lire le label. */
  .tr-card .tr-rempty { fill:color-mix(in srgb, var(--steel) 6%, transparent); }
  .tr-card .tr-rempty-txt { fill:var(--steel); font-size:7px; font-family:var(--fm); opacity:.75; }
  /* Taux correct démoté : titre plus petit + caveat sous-jacent + bordure
     latérale gauche pour signifier "secondaire" visuellement. */
  .tr-card .tr-metric--secondary { opacity:.85; }
  .tr-card .tr-mname--small { font-size:var(--t-caption); font-weight:500; color:var(--ink2); }
  .tr-card .tr-msubcaveat { font-size:var(--t-caption); color:var(--steel); margin:calc(-1 * var(--s2)) 0 var(--s2) 0; font-style:italic; }
  .tr-card .tr-pipe { display:flex; flex-wrap:wrap; gap:var(--s2) var(--s3); padding-top:var(--s35); color:var(--ink2); font-size:var(--t-body); }
  .tr-card .tr-pipe b { color:var(--ink); font-weight:600; }
  .tr-card .tr-sep { color:var(--line3); }
  .rs { display:flex; justify-content:space-between; margin-top:var(--s15); font-size:var(--t-data); color:var(--steel); }
  .dwrap { display:flex; align-items:center; gap:var(--s5); flex-wrap:wrap; }
  .legend { display:flex; flex-direction:column; gap:var(--s2); flex:1; min-width:200px; }
  /* Empty states polish (Linear pattern) : padding genereux + typo douce +
     icone hairline sobre devant le texte si present (.empty-ico). */
  .empty { padding:36px 16px; text-align:center; color:var(--steel); font-family:var(--fb); font-size:var(--t-base); line-height:1.5; }
  .empty b { display:block; font-family:var(--fd); font-size:var(--t-h3); font-weight:500; color:var(--ink); margin-bottom:6px; letter-spacing:.04em; }
  .empty-ico { display:inline-block; width:24px; height:24px; border-radius:var(--r-circle); background:color-mix(in srgb,var(--steel) 18%,transparent); margin-bottom:10px; line-height:24px; color:var(--steel); font-family:var(--fm); font-size:var(--t-base); font-weight:600; }
  .empty .hint { display:block; margin-top:6px; font-size:var(--t-data); color:color-mix(in srgb,var(--steel) 70%,transparent); }
  .dt { width:100%; border-collapse:collapse; font-size:var(--t-base); }
  .dt th { text-align:left; font-family:var(--fb); font-size:var(--t-data); letter-spacing:.12em; text-transform:uppercase; color:var(--steel); padding:var(--s2) 10px; border-bottom:1px solid var(--line2); cursor:pointer; user-select:none; }
  .dt th.num { text-align:right; } .dt th:hover { color:var(--ink); }
  .dt td { padding:var(--s2) 10px; border-bottom:1px solid var(--line); } .dt td.num { text-align:right; font-family:var(--fm); }
  .dt td.tk { font-family:var(--fm); font-weight:600; } .dt tr:hover td { background:color-mix(in srgb,var(--ink) 2.5%,transparent); }
  .dt td.pos { color:var(--acc); } .dt td.neg { color:var(--bear); }
  .bdg { display:inline-block; margin-left:var(--s2); font-family:var(--fb); font-size:var(--t-data); letter-spacing:.1em; text-transform:uppercase; color:var(--id); border:1px solid color-mix(in srgb, var(--acc2) 40%, transparent); border-radius:var(--r0); padding:1px 5px; vertical-align:middle; }
  .dt tr.prev td { opacity:.72; } .dt tr.prev td.tk { color:var(--id); }
  .nm { display:block; font-size:var(--t-data); font-weight:400; color:var(--steel); margin-top:2px; }
  .ph3 { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.14em; text-transform:uppercase; color:var(--steel); margin:0 0 12px; }
  .dtier { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.12em; text-transform:uppercase; color:var(--steel); margin:0 0 6px; padding-bottom:var(--s15); border-bottom:1px solid var(--line); break-after:avoid; }
  /* Macro stress monitor full-width : flow tiers en colonnes auto
     pour eviter le trou. Sous-blocs lus de gauche a droite. */
  .dlist { columns: 2; column-gap: var(--s4); }
  .dlist > .dtier { break-inside:avoid; }
  .dlist > .dtier + * { break-before:avoid; }
  @media (max-width: 980px) { .dlist { columns: 1; } }
  [data-tip]{position:relative;cursor:help}
  /* Tooltip position : appears ABOVE trigger (bottom:100%) to avoid overlapping
     content below (colhead, ps-cell). Fully opaque bg + strong shadow + high
     z-index pour clarte visuelle. */
  [data-tip]:hover::after{content:attr(data-tip);position:absolute;left:0;bottom:calc(100% + 6px);top:auto;background:var(--panel);color:var(--ink);border:1px solid var(--line2);padding:8px 12px;border-radius:var(--r1);font-family:var(--fb);font-size:var(--t-data);font-weight:400;letter-spacing:0;text-transform:none;white-space:normal;max-width:340px;min-width:240px;width:max-content;z-index:9999;box-shadow:var(--elev2);pointer-events:none;line-height:1.45;}
  body.midnight [data-tip]:hover::after{box-shadow:var(--elev2);background:var(--panel);}
  .drow { display:grid; grid-template-columns:14px 1fr auto auto auto; align-items:center; gap:var(--s3); padding:var(--s2) 0; font-size:var(--t-base); }
  .ddot { width:8px; height:8px; border-radius:var(--r-circle); }
  .ddot.calm { background:var(--acc); } .ddot.warn { background:var(--warn); }
  .ddot.hot { background:var(--warn); } .ddot.danger { background:var(--bear); }
  .ddot.mute { background:var(--steel); opacity:.45; }
  .dname { color:var(--ink); } .dval { font-family:var(--fm); text-align:right; color:var(--ink); } .dp { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); }
  .stale { font-family:var(--fb); font-size:var(--t-data); color:var(--steel); opacity:.7; text-transform:uppercase; letter-spacing:.08em; }
  .nodata { font-family:var(--fb); font-size:var(--t-data); color:var(--bear); opacity:.85; text-transform:uppercase; letter-spacing:.08em; font-weight:600; }
  /* Macro stress monitor : triage ACT/WATCH/ASLEEP/SILENT (Phase C). */
  .dbucket { display:flex; align-items:baseline; gap:var(--s2); margin:var(--s3) 0 var(--s15); padding-bottom:var(--s15); border-bottom:1px solid var(--line); break-after:avoid; }
  .dbucket-lbl { font-family:var(--fb); font-size:var(--t-data2); letter-spacing:.14em; text-transform:uppercase; font-weight:600; }
  .dbucket-lbl.bear { color:var(--bear); } .dbucket-lbl.warn { color:var(--warn); } .dbucket-lbl.steel { color:var(--steel); }
  .dbucket-count { font-family:var(--fm); font-size:var(--t-small); color:var(--steel); padding:1px 7px; border:1px solid var(--line); border-radius:var(--r2); }
  .dbucket + .drow { margin-top:2px; }
  .dlist > .dbucket { break-inside:avoid; }
  .dlist > .dbucket + * { break-before:avoid; }
  /* Tier chip per row : preserve tier origin sans dominer la lecture. */
  .dtchip { font-family:var(--fb); font-size:var(--t-meta); letter-spacing:.1em; color:var(--steel); opacity:.65; margin-left:var(--s2); padding:1px 5px; border:1px solid var(--line); border-radius:var(--r1); }
  /* Cycle phase chip (Positions panel, 06/06 wire shared/sectors). */
  .cycle-chip { font-family:var(--fb); font-size:var(--t-fine); letter-spacing:.1em; text-transform:uppercase; margin-left:var(--s2); padding:1px 6px; border-radius:var(--r2); font-weight:600; }
  .cycle-chip.cycle-acc { color:var(--acc); background:color-mix(in srgb, var(--acc) 12%, transparent); }
  .cycle-chip.cycle-warn { color:var(--warn); background:color-mix(in srgb, var(--warn) 13%, transparent); }
  .cycle-chip.cycle-bear { color:var(--bear); background:color-mix(in srgb, var(--bear) 13%, transparent); }
  .cycle-chip.cycle-steel { color:var(--steel); background:color-mix(in srgb, var(--steel) 12%, transparent); }
  .cycle-chip.cycle-steel-mute { color:var(--steel); opacity:.55; background:color-mix(in srgb, var(--steel) 8%, transparent); }
  /* Macro book warning chip (R1/R2/R4/...) per ticker on Positions panel. */
  .warn-chip { font-family:var(--fb); font-size:var(--t-fine); letter-spacing:.1em; text-transform:uppercase; margin-left:var(--s15); padding:1px 5px; border-radius:var(--r1); font-weight:700; border:1px solid currentColor; }
  .warn-chip.warn-chip-bear { color:var(--bear); }
  .warn-chip.warn-chip-warn { color:var(--warn); }
  .warn-chip.warn-chip-steel { color:var(--steel); }
  /* Tooltip warn-chip : preserve \n pour structure ACTION / POURQUOI. */
  .warn-chip[data-tip]:hover::after { white-space: pre-line; max-width: 400px; }
  /* Regime chip (Phase A) : label classify_regime dans le header panel. */
  .regime-chip { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.14em; text-transform:uppercase; font-weight:600; padding:2px 9px; border-radius:var(--r2); border:1px solid currentColor; }
  .regime-chip.regime-bear { color:var(--bear); background:color-mix(in srgb, var(--bear) 12%, transparent); }
  .regime-chip.regime-warn { color:var(--warn); background:color-mix(in srgb, var(--warn) 13%, transparent); }
  .regime-chip.regime-calm { color:var(--acc); background:color-mix(in srgb, var(--acc) 12%, transparent); }
  .regime-chip.regime-steel { color:var(--steel); background:color-mix(in srgb, var(--steel) 10%, transparent); }
  /* Audit metadata chip (06/06 Phase A canonical) : surface date + version dernier audit calibration. */
  .audit-chip { font-family:var(--fb); font-size:var(--t-meta); letter-spacing:.1em; color:var(--steel); opacity:.65; padding:1px 7px; border:1px solid var(--line); border-radius:var(--r2); margin-left:var(--s2); cursor:help; }
  /* Phase B : tie-to-book warnings */
  .bookwarn-block { margin-top:var(--s4); padding-top:var(--s3); border-top:1px dashed var(--line2); }
  .bookwarn-hdr { font-family:var(--fb); font-size:var(--t-small); letter-spacing:.14em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s3); }
  .bookwarn-row { display:grid; grid-template-columns:auto 1fr auto; gap:var(--s3); align-items:baseline; padding:var(--s2) 0; border-bottom:1px solid var(--line); cursor:help; }
  .bookwarn-row:last-child { border-bottom:none; }
  .bookwarn-sev { font-family:var(--fb); font-size:var(--t-mini); letter-spacing:.12em; text-transform:uppercase; font-weight:700; padding:1px 7px; border:1px solid currentColor; border-radius:var(--r2); }
  .bookwarn-sev.bear { color:var(--bear); } .bookwarn-sev.warn { color:var(--warn); } .bookwarn-sev.steel { color:var(--steel); }
  .bookwarn-action { color:var(--ink); font-size:var(--t-data2); }
  .bookwarn-tk { font-family:var(--fm); font-size:var(--t-small); color:var(--steel); }
  @keyframes fade { to { opacity:1; } }
  .noanim [data-page].active, .noanim .row { animation:none !important; }
  .noanim .row { opacity:1 !important; }
  .plan { background:var(--panel); border:1px solid var(--line3); border-radius:var(--r2); padding:15px 20px; margin-bottom:var(--s4); }
  .plan-h { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:13px; }
  .plan-row { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
  .pi { display:flex; flex-direction:column; gap:var(--s1); padding-left:13px; border-left:2px solid var(--line2); border-radius:0; }
  .pi.danger { border-left-color:var(--bear); } .pi.warn { border-left-color:var(--warn); } .pi.calm { border-left-color:var(--acc); } .pi.size { border-left-color:var(--steel); }
  .pn { font-family:var(--fm); font-weight:500; font-size:var(--t-h2); line-height:1; letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .pi.danger .pn { color:var(--bear); } .pi.warn .pn { color:var(--warn); } .pi.calm .pn { color:var(--acc); } .pi.size .pn { color:var(--metal); }
  .pl { font-size:var(--t-data2); color:var(--ink); } .pt { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); }
  .dt tbody tr:not(.prev) { cursor:pointer; }
  .loupe { position:fixed; inset:0; z-index:60; display:none; align-items:center; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:34px; }
  .loupe.open { display:flex; }
  /* vt-loupe : kill le root crossfade pendant la transition loupe.
     Seul le .tklogo morph (shared element), background reste statique.
     Pas de scale-in card (root cause du bug "interface saute"). */
  html.vt-loupe { view-transition-name: none; }
  /* Respect prefers-reduced-motion. */
  @media (prefers-reduced-motion: reduce) {
    .loupe.open, .loupe.open .loupe-card { animation: none !important; }
  }
  .loupe-card { position:relative; width:min(560px,100%); max-height:86vh; overflow:auto; background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); padding:28px 30px; box-shadow:var(--elev3); }
  .loupe-x { position:absolute; top:var(--s35); right:var(--s4); background:none; border:none; color:var(--steel); font-size:var(--t-h2); line-height:1; cursor:pointer; }
  .loupe-x:hover { color:var(--ink); }
  .lp-h { display:flex; align-items:baseline; gap:11px; }
  .lp-tk { font-family:var(--fm); font-weight:500; font-size:var(--t-h2); letter-spacing:.02em; color:var(--ink); }
  .lp-nm { font-size:var(--t-base); color:var(--steel); }
  .lp-meta { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin:var(--s15) 0 18px; }
  .lp-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--s3); }
  .lp-mom { display:grid; grid-template-columns:repeat(3,1fr); gap:var(--s3); }
  .lp-stat { background:var(--panel); border:1px solid var(--line); border-radius:var(--r2); padding:11px 13px; }
  .lp-sl { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.14em; text-transform:uppercase; color:var(--steel); }
  .lp-sv { font-family:var(--fm); font-weight:500; font-size:var(--t-h3); letter-spacing:-.01em; margin-top:var(--s15); font-variant-numeric:tabular-nums; }
  .lp-sec { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:20px 0 10px; border-top:1px solid var(--line); padding-top:var(--s35); }
  .lp-score { display:flex; align-items:center; gap:var(--s3); margin:var(--s2) 0; font-size:var(--t-data2); }
  .lp-score .ln { width:92px; color:var(--steel); }
  .lp-score .bar { flex:1; height:6px; background:var(--barbg); border-radius:var(--r0); overflow:hidden; }
  .lp-score .bf { display:block; height:100%; background:linear-gradient(90deg,var(--acc),var(--acc)); }
  .lp-score .vv { font-family:var(--fm); width:32px; text-align:right; }
  .lp-ex { font-size:var(--t-base); color:var(--ink); line-height:1.6; opacity:.82; }
  .lp-empty { font-size:var(--t-data2); color:var(--steel); padding:var(--s15) 0; }
  .lp-hint { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-top:var(--s35); padding-top:var(--s3); border-top:1px solid color-mix(in srgb,var(--ink) 5%,transparent); line-height:1.5; }
  .lp-hint code { font-family:var(--fm); font-weight:600; color:var(--ink); background:color-mix(in srgb,var(--ink) 5%,transparent); padding:1px 5px; border-radius:var(--r0); font-size:var(--t-data); }
  .tkc { cursor:pointer; transition:color .12s; } .tkc:hover { color:var(--id); }
  .lp-badge { display:inline-block; font-family:var(--fb); font-size:var(--t-data); letter-spacing:.1em; text-transform:uppercase; padding:2px 8px; border-radius:var(--r1); border:1px solid currentColor; }
  .lp-badge.held { color:var(--acc); } .lp-badge.watch { color:var(--warn); } .lp-badge.univ { color:var(--acc2); } .lp-badge.out { color:var(--steel); }
  .sbwrap { display:flex; flex-direction:column; gap:var(--s5); }
  .sb-top { display:grid; grid-template-columns:repeat(3,1fr); gap:32px; width:100%; padding:var(--s2) 4px 16px; border-bottom:1px solid var(--line); }
  .sb-kpi { display:flex; flex-direction:column; gap:var(--s15); }
  .sb-kl { font-family:var(--fb); font-weight:600; font-size:var(--t-data); letter-spacing:.18em; color:var(--steel); }
  .sb-kv { font-family:var(--fm); font-weight:500; font-size:var(--t-h2); color:var(--ink); letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .sb-bars { display:flex; flex-direction:column; gap:2px; width:100%; }
  .sb-row { display:grid; grid-template-columns:minmax(160px,1.4fr) minmax(120px,3fr) 50px 70px; align-items:center; gap:16px; padding:var(--s25) 6px; border-radius:var(--r1); cursor:pointer; transition:background .15s,opacity .2s; }
  .sb-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .sb-row.on { background:color-mix(in srgb,var(--ink) 5%,transparent); }
  .sb-bars:has(.sb-row.on) .sb-row.dim { opacity:.28; }
  .sb-row-name { display:flex; align-items:center; gap:var(--s3); min-width:0; }
  .sb-row-dot { width:8px; height:8px; border-radius:var(--r-circle); flex:0 0 auto; }
  .sb-row-label { font-family:var(--fb); font-weight:500; font-size:var(--t-base); color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .sb-row-bar { height:4px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r0); overflow:hidden; }
  .sb-row-fill { height:100%; border-radius:var(--r0); transition:width .4s cubic-bezier(.2,.8,.2,1); }
  .sb-row-pct { font-family:var(--fm); font-weight:500; font-size:var(--t-base); color:var(--ink); text-align:right; font-variant-numeric:tabular-nums; }
  .sb-row-val { font-family:var(--fm); font-weight:400; font-size:var(--t-data2); color:var(--steel); text-align:right; font-variant-numeric:tabular-nums; }
  #sb-panel { width:100%; font-size:var(--t-base); padding:var(--s3) 0 0; }
  #sb-panel:empty { display:none; }
  .sbrow { display:flex; justify-content:space-between; align-items:center; padding:var(--s2) 0; border-bottom:.5px solid var(--line); cursor:pointer; } .sbrow:last-child { border-bottom:none; } .sbrow:hover { background:color-mix(in srgb,var(--ink) 2.5%,transparent); }
  .qs { position:fixed; inset:0; z-index:70; display:none; align-items:flex-start; justify-content:center; background:rgba(6,10,18,.72); backdrop-filter:blur(6px); padding:12vh 20px 20px; }
  .qs.open { display:flex; }
  .qs-card { width:min(560px,100%); background:var(--panel); border:1px solid var(--line2); border-radius:var(--r3); box-shadow:var(--elev3); overflow:hidden; }
  #qs-input { width:100%; box-sizing:border-box; background:transparent; border:none; outline:none; color:var(--ink); font-family:var(--fb); font-size:var(--t-h3); padding:var(--s4) 20px; border-bottom:1px solid var(--line); }
  #qs-input:focus-visible { outline:2px solid var(--ink); outline-offset:2px; border-radius:var(--r1); }
  #qs-input::placeholder { color:var(--steel); }
  #qs-res { max-height:50vh; overflow:auto; }
  .qs-row { display:flex; align-items:center; gap:var(--s3); padding:11px 20px; cursor:pointer; border-bottom:.5px solid var(--line); }
  .qs-row:last-child { border-bottom:none; } .qs-row.on, .qs-row:hover { background:color-mix(in srgb, var(--acc) 10%, transparent); }
  .qs-tk { font-family:var(--fm); font-weight:600; font-size:var(--t-base); width:78px; }
  .qs-nm { flex:1; font-size:var(--t-base); color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .qs-st { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.08em; text-transform:uppercase; color:var(--steel); }
  .qs-st.held { color:var(--acc); } .qs-st.watch { color:var(--warn); } .qs-st.core, .qs-st.extended { color:var(--acc2); }
  .qs-empty { padding:22px 20px; color:var(--steel); font-size:var(--t-base); text-align:center; }
  .hero.posture { display:block; }
  .hero.posture .plan-row { margin-top:var(--s35); gap:var(--s5); }
  .hero.posture .pn { font-size:var(--t-h1); }
  .hrow { display:grid; grid-template-columns:1.3fr 1fr; gap:var(--s4); margin-bottom:20px; align-items:stretch; }
  /* hero-single : refonte vigie 31/05 -- pfcard seule sans disc_hero a droite */
  .hero-single { display:block; margin-bottom:var(--s4); }
  .hero-single .pfcard { max-width:none; }
  .hrow .hero.posture { margin-bottom:0; height:100%; }
  .pfcard { background:var(--panel); border:1px solid var(--line3); border-radius:var(--r3); padding:20px 24px; display:flex; flex-direction:column; }
  .pfcard .v { font-family:var(--fm); font-weight:500; font-size:var(--t-h1); letter-spacing:-.01em; line-height:1; margin:var(--s2) 0 5px; color:var(--ink); font-variant-numeric:tabular-nums; }
  .pfcard .d { font-family:var(--fm); font-size:var(--t-base); font-weight:600; } .pfcard .d.pos { color:var(--acc); } .pfcard .d.neg { color:var(--bear); }
  .pfcard .distline { margin:16px 0 0; height:20px; gap:3px; border-radius:0; overflow:visible; }
  .pfcard .distline .g { background:var(--acc); border-radius:var(--r1); }
  .pfcard .distline .r { background:var(--bear); border-radius:var(--r1); }
  .pfcard .distcap { display:flex; justify-content:space-between; font-family:var(--fm); font-size:var(--t-data2); margin-top:9px; }
  .pfcard .distcap .cg { color:var(--acc); font-weight:600; }
  .pfcard .distcap .cr { color:var(--bear); font-weight:600; }
  .pfcard .sub2 { font-size:var(--t-data2); color:var(--steel); margin-top:auto; padding-top:13px; } .pfcard .sub2 b { color:var(--ink); font-weight:600; }
  @media (max-width:980px) { .hrow { grid-template-columns:1fr; } }
  /* Star treatment - hero row au top de Vue d'ensemble */
  .hrow.star { gap:22px; margin-bottom:28px; }
  .hrow.star .pfcard { padding:30px 36px; }
  .hrow.star .pfcard .hl { font-size:var(--t-data); letter-spacing:.22em; }
  .hrow.star .pfcard .v { font-size:var(--t-hero); margin:var(--s35) 0 9px; line-height:.95; }
  .hrow.star .pfcard .d { font-size:var(--t-h3); }
  .hrow.star .pfcard .distline { margin-top:22px; height:24px; }
  .hrow.star .pfcard .distcap { font-size:var(--t-base); margin-top:var(--s3); }
  .hrow.star .pfcard .sub2 { font-size:var(--t-base); padding-top:var(--s4); }
  .hrow.star .hero.posture { padding:30px 36px; }
  .hrow.star .hero.posture .hl { font-size:var(--t-data); letter-spacing:.22em; }
  .hrow.star .hero.posture .pn { font-size:45px; line-height:.95; }
  .hrow.star .hero.posture .plan-row { margin-top:var(--s4); gap:30px; }
  /* Sprint 5 - Portfolio grade */
  .gradecard .ghead { display:flex; align-items:center; gap:22px; margin:var(--s35) 0 18px; padding-bottom:var(--s4); border-bottom:1px solid var(--line); }
  .gradecard .gletter { font-family:var(--fm); font-weight:500; font-size:59px; line-height:.9; letter-spacing:-.02em; padding:0 18px; border-radius:var(--r2); }
  .gradecard .gletter.good { color:var(--acc); }
  .gradecard .gletter.warn { color:var(--warn); }
  .gradecard .gletter.bad { color:var(--bear); }
  .gradecard .gscore { flex:1; display:flex; flex-direction:column; gap:var(--s15); }
  .gradecard .gscoreval { font-size:var(--t-h1); font-weight:500; letter-spacing:-.01em; line-height:1; color:var(--ink); }
  .gradecard .gscoremax { color:var(--steel); font-weight:400; font-size:var(--t-h3); margin-left:2px; }
  .gradecard .gscorebar { height:6px; background:color-mix(in srgb,var(--ink) 6%,transparent); border-radius:var(--r1); overflow:hidden; }
  .gradecard .gscorefill { height:100%; border-radius:var(--r1); transition:width .4s ease; }
  .gradecard .gscorefill.good { background:var(--acc); }
  .gradecard .gscorefill.warn { background:var(--warn); }
  .gradecard .gscorefill.bad { background:var(--bear); }
  .gradecard .gbody { display:grid; gap:var(--s3); }
  .gradecard .grow { display:grid; grid-template-columns:200px 1fr 180px; align-items:center; gap:var(--s35); }
  .gradecard .glab { font-family:var(--fm); font-size:var(--t-base); color:var(--steel); font-weight:500; }
  .gradecard .gaxis { position:relative; height:6px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); }
  .gradecard .gfill { position:absolute; left:0; top:0; height:100%; border-radius:var(--r1); }
  .gradecard .gfill.good { background:var(--acc); }
  .gradecard .gfill.bad { background:var(--bear); opacity:.55; }
  /* Needle iconic canonique (diamant SVG noir/blanc — meme forme que .axis-mark) */
  .gradecard .gtgt { position:absolute; top:50%; width:28px; height:13px;
    background-color:var(--ink);
    -webkit-mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 60 24'><path d='M1 12 Q26 10 30 1 Q34 10 59 12 Q34 14 30 23 Q26 14 1 12 Z' fill='%23ffffff'/></svg>") no-repeat center / contain;
    transform:translate(-50%,-50%); z-index:2; opacity:.85; }
  .gradecard .gnum { display:flex; align-items:center; gap:var(--s3); justify-content:flex-end; font-size:var(--t-data2); color:var(--ink); }
  .gradecard .gnum .gt { color:var(--steel); font-size:var(--t-data); }
  @media (max-width:980px) { .gradecard .grow { grid-template-columns:1fr; gap:var(--s1); } .gradecard .gnum { justify-content:flex-start; } }
  /* Sprint 21 - Accordion dim qui deroule INLINE en dessous (pattern geo) */
  .gradecard .grow-wrap { cursor:pointer; }
  .gradecard .grow.has-acc { transition:background .15s; border-radius:var(--r2); padding:2px 4px; margin:0 -4px; }
  .gradecard .grow-wrap:hover .grow.has-acc { background:color-mix(in srgb,var(--ink) 4%,transparent); }
  .gradecard .gsub { max-height:0; overflow:hidden; opacity:0; transition:max-height .3s ease, opacity .2s ease, margin .3s ease, padding .3s ease; padding:0 10px; margin:0; }
  .gradecard .grow-wrap.open .gsub { max-height:260px; opacity:1; margin:var(--s15) 0 14px; padding:var(--s25) 14px; }
  .gradecard .gsub { background:color-mix(in srgb,var(--ink) 3%,transparent); border-left:2px solid var(--line2); border-radius:0 var(--r2) var(--r2) 0; margin-left:var(--s15); }
  .gradecard .gsub-chips { display:flex; flex-wrap:wrap; gap:var(--s15); margin-bottom:var(--s2); }
  .gradecard .gsub-tk { font-family:var(--fm); font-size:var(--t-data); font-weight:600; color:var(--ink); background:color-mix(in srgb,var(--ink) 8%,transparent); padding:3px 9px; border-radius:var(--r1); cursor:pointer; transition:.12s; }
  .gradecard .gsub-tk:hover { background:color-mix(in srgb,var(--id) 16%,transparent); color:var(--id); }
  .gradecard .gsub-empty { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-style:italic; }
  .gradecard .gsub-ev { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); line-height:1.55; padding-top:var(--s15); border-top:1px solid color-mix(in srgb,var(--ink) 6%,transparent); }
  /* Sub-notes Construction + Fragilite (glossaire canonique) */
  .gradecard .gsplit { display:grid; grid-template-columns:1fr 1fr; gap:var(--s5); margin-top:var(--s4); padding-top:var(--s4); border-top:1px solid var(--line); }
  .gradecard .gsub { display:flex; flex-direction:column; gap:var(--s3); }
  .gradecard .gsubh { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; }
  .gradecard .gsubscore { font-size:var(--t-h1); font-weight:500; line-height:1; letter-spacing:-.02em; }
  .gradecard .gsubscore.good { color:var(--acc); }
  .gradecard .gsubscore.warn { color:var(--warn); }
  .gradecard .gsubscore.bad { color:var(--bear); }
  .gradecard .gsubmax { color:var(--steel); font-size:var(--t-base); margin-left:1px; font-weight:400; }
  @media (max-width:980px) { .gradecard .gsplit { grid-template-columns:1fr; gap:var(--s35); } }
  .gradecard .ggate { font-family:var(--fm); font-size:var(--t-data2); color:var(--bear); background:color-mix(in srgb,var(--bear) 10%,transparent); padding:var(--s25) 14px; border-radius:var(--r2); margin:var(--s35) 0; border-left:3px solid var(--bear); }
  /* Top Risks surveillance */
  .riskwatchcard .rw-lens { font-family:var(--fm); margin:var(--s25) 0 4px; padding:9px 12px; background:color-mix(in srgb, var(--warn) 5%, transparent); border-left:2px solid var(--warn); border-radius:var(--r0); font-size:var(--t-data2); color:var(--ink); line-height:1.55; }
  .riskwatchcard .rw-card { padding:16px 0; border-bottom:1px solid var(--line); }
  .riskwatchcard .rw-card:last-child { border-bottom:none; }
  .riskwatchcard .rw-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s2); }
  .riskwatchcard .rw-rank { font-family:var(--fm); font-weight:700; font-size:var(--t-h3); color:var(--bear); }
  .riskwatchcard .rw-name { font-family:var(--fm); font-weight:500; font-size:var(--t-h3); color:var(--ink); flex:1; }
  .riskwatchcard .rw-sev { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.15em; text-transform:uppercase; font-weight:600; padding:2px 7px; border-radius:var(--r1); }
  .riskwatchcard .rw-sev.danger { background:color-mix(in srgb,var(--bear) 18%,transparent); color:var(--bear); }
  .riskwatchcard .rw-sev.warn { background:color-mix(in srgb,var(--warn) 18%,transparent); color:var(--warn); }
  .riskwatchcard .rw-expo { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); margin-bottom:var(--s35); }
  .riskwatchcard .rw-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--s35); margin-bottom:var(--s4); }
  .riskwatchcard .rw-cell { padding:var(--s3) var(--s35); background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); }
  .riskwatchcard .rw-h { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .riskwatchcard .rw-v { font-family:var(--fm); font-size:var(--t-h2); font-weight:500; color:var(--ink); line-height:1; }
  .riskwatchcard .rw-v.neg { color:var(--bear); }
  .riskwatchcard .rw-t { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-top:var(--s1); }
  .riskwatchcard .rw-section { margin-top:var(--s35); }
  .riskwatchcard .rw-sh { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s25); }
  .riskwatchcard .rw-sig { padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .riskwatchcard .rw-sig.atrisk { border-left:3px solid var(--warn); padding-left:var(--s25); margin-left:-10px; background:color-mix(in srgb,var(--warn) 4%,transparent); }
  .riskwatchcard .rw-sig.triggered { border-left:3px solid var(--bear); padding-left:var(--s25); margin-left:-10px; background:color-mix(in srgb,var(--bear) 5%,transparent); }
  .riskwatchcard .rw-sig-head { display:grid; grid-template-columns:1fr 100px 90px; gap:var(--s3); font-size:var(--t-data2); align-items:baseline; }
  .riskwatchcard .rw-sig-l { color:var(--ink); }
  .riskwatchcard .rw-sig-w { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.12em; text-transform:uppercase; color:var(--steel); text-align:right; }
  .riskwatchcard .rw-sig-s { font-family:var(--fm); font-size:var(--t-data); text-align:right; padding:1px 6px; border-radius:var(--r1); font-weight:600; }
  .riskwatchcard .rw-sig-s.monitoring { color:var(--steel); background:color-mix(in srgb,var(--ink) 6%,transparent); }
  .riskwatchcard .rw-sig-s.atrisk { color:var(--warn); background:color-mix(in srgb,var(--warn) 14%,transparent); }
  .riskwatchcard .rw-sig-s.triggered { color:var(--bear); background:color-mix(in srgb,var(--bear) 16%,transparent); }
  .riskwatchcard .rw-sig-reason { font-family:var(--fm); font-size:var(--t-data); color:var(--ink); opacity:.85; line-height:1.45; margin-top:var(--s15); }
  .riskwatchcard .rw-sig-conf { color:var(--steel); font-size:var(--t-data); }
  .riskwatchcard .rw-mit { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .riskwatchcard .rw-mit:last-child { border-bottom:none; }
  .riskwatchcard .rw-mit-h { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .riskwatchcard .rw-mit-l { font-family:var(--fm); font-weight:500; font-size:var(--t-base); color:var(--ink); flex:1; }
  .riskwatchcard .rw-mit-st { font-family:var(--fm); font-size:var(--t-data); font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); font-weight:600; }
  .riskwatchcard .rw-mit-st.started { background:color-mix(in srgb,var(--warn) 12%,transparent); color:var(--warn); }
  .riskwatchcard .rw-mit-st.in_progress { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .riskwatchcard .rw-mit-st.pending { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .riskwatchcard .rw-mit-a { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); opacity:.85; line-height:1.5; margin-bottom:3px; }
  .riskwatchcard .rw-mit-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-style:italic; }
  @media (max-width:980px) { .riskwatchcard .rw-grid { grid-template-columns:1fr; } .riskwatchcard .rw-sig { grid-template-columns:1fr; } }
  /* Data health panel (Axe 5 QUALITY_BAR, M1 freshness, 07/06 nuit++) */
  .data-health-card { padding:var(--s4); margin-top:var(--s4); border:1px solid var(--line); border-radius:var(--r2); background:var(--surface); }
  .data-health-card .card-h { font-family:var(--fb); font-size:var(--t-base); letter-spacing:.16em; text-transform:uppercase; color:var(--ink); margin-bottom:var(--s2); }
  .data-health-card .card-meta { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); margin-bottom:var(--s35); font-style:italic; }
  .data-health-card .card-b { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); padding:var(--s3) 0; }
  .data-health-card .dh-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--s3); margin-bottom:var(--s35); }
  .data-health-card .dh-kpi { padding:var(--s3); background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r1); }
  .data-health-card .dh-kpi .k { font-family:var(--fb); font-size:var(--t-small); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .data-health-card .dh-kpi .v { font-family:var(--fm); font-size:var(--t-h2); font-weight:500; color:var(--ink); line-height:1; }
  .data-health-card .dh-kpi .v.ok { color:var(--acc); }
  .data-health-card .dh-kpi .v.warn { color:var(--warn); }
  .data-health-card .dh-kpi .v.neg { color:var(--bear); }
  .data-health-card .dh-kpi .v.neu { color:var(--steel); }
  .data-health-card .dh-tip { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); margin-top:var(--s1); }
  .data-health-card .dh-distrib { display:flex; gap:var(--s2); flex-wrap:wrap; }
  .data-health-card .dh-chip { font-family:var(--fm); font-size:var(--t-small); padding:2px 8px; border-radius:var(--r1); font-variant-numeric:tabular-nums; }
  .data-health-card .dh-chip.ok { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .data-health-card .dh-chip.warn { background:color-mix(in srgb,var(--warn) 12%,transparent); color:var(--warn); }
  .data-health-card .dh-chip.neg { background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); }
  .data-health-card .dh-chip.neu { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  @media (max-width:980px) { .data-health-card .dh-grid { grid-template-columns:repeat(2, 1fr); } }
  /* Performance panel (Heimdall ffn analytics, post-audit 07/06) */
  .performance-card { padding:var(--s4); margin-top:var(--s4); border:1px solid var(--line); border-radius:var(--r2); background:var(--surface); }
  .performance-card .card-h { font-family:var(--fb); font-size:var(--t-base); letter-spacing:.16em; text-transform:uppercase; color:var(--ink); margin-bottom:var(--s2); }
  .performance-card .card-meta { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); margin-bottom:var(--s35); font-style:italic; }
  .performance-card .card-b { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); padding:var(--s3) 0; }
  .performance-card .perf-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--s3); }
  .performance-card .perf-kpi { padding:var(--s3); background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r1); }
  .performance-card .perf-kpi .k { font-family:var(--fb); font-size:var(--t-small); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .performance-card .perf-kpi .v { font-family:var(--fm); font-size:var(--t-h2); font-weight:500; color:var(--ink); line-height:1; }
  .performance-card .perf-kpi .v.neg { color:var(--bear); }
  .performance-card .perf-chart-block { margin-top:var(--s35); }
  .performance-card .perf-chart-h { font-family:var(--fb); font-size:var(--t-small); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .performance-card .perf-equity-svg { display:block; width:100%; max-height:60px; }
  .performance-card .perf-dd-svg { display:block; width:100%; max-height:50px; }
  @media (max-width:980px) { .performance-card .perf-grid { grid-template-columns:repeat(2, 1fr); } }
  /* Calibration progress panel (action #3 31/05) -- s'active a n>=30 */
  .calibcard .calib-progress { display:flex; align-items:center; gap:var(--s4); margin-top:var(--s35); }
  .calibcard .calib-bar { flex:1; height:8px; background:color-mix(in srgb, var(--steel) 12%, transparent); border-radius:var(--r0); overflow:hidden; position:relative; }
  .calibcard .calib-fill { height:100%; background:linear-gradient(90deg, var(--acc), color-mix(in srgb, var(--acc) 70%, var(--gold))); transition:width .4s ease; }
  .calibcard .calib-meta { display:flex; align-items:baseline; gap:var(--s35); min-width:160px; justify-content:flex-end; }
  .calibcard .calib-n { font-family:var(--fmono); font-size:var(--t-h3); font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .calibcard .calib-rem { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); }
  .calibcard .calib-verdict { display:flex; align-items:baseline; gap:var(--s4); margin-top:var(--s35); flex-wrap:wrap; }
  .calibcard .calib-status { font-family:var(--fm); font-weight:500; font-size:var(--t-base); letter-spacing:.08em; text-transform:uppercase; padding:3px 10px; border-radius:var(--r0); background:color-mix(in srgb, var(--ink) 6%, transparent); }
  .calibcard .calib-status.acc { color:var(--acc); background:color-mix(in srgb, var(--acc) 10%, transparent); }
  .calibcard .calib-status.warn { color:var(--warn); background:color-mix(in srgb, var(--warn) 12%, transparent); }
  .calibcard .calib-status.neg { color:var(--bear); background:color-mix(in srgb, var(--bear) 12%, transparent); }
  .calibcard .calib-brier, .calibcard .calib-gap { font-family:var(--fm); font-size:var(--t-base); color:var(--steel); }
  .calibcard .calib-brier .mono, .calibcard .calib-gap .mono { color:var(--ink); margin-left:var(--s1); }
  .calibcard .calib-msg { margin-top:var(--s25); font-family:var(--fm); font-size:var(--t-base); color:var(--ink2); line-height:1.55; padding-top:var(--s25); border-top:1px solid var(--line); }
  /* Page Strategie : sub-section headers */
  /* Unified avec .th-grp / .vigie-sh / .dba-sh : flex + after-line subtile */
  .strat-sh { font-family:var(--fm); font-weight:500; font-size:var(--t-data2); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:var(--s4) 2px var(--s3); display:flex; align-items:center; gap:var(--s3); }
  .strat-sh::after { content:""; flex:1; height:1px; background:var(--line); }
  .strat-sh:first-of-type { margin-top:var(--s35); }
  /* Section headers page vigie (refonte hierarchie 30/05 -- 3 blocs : Operationnel / Systeme V2 / Contextuel) */
  /* Unified avec .th-grp / .strat-sh / .dba-sh : flex + after-line subtile */
  .vigie-sh { font-family:var(--fm); font-weight:500; font-size:var(--t-data2); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:var(--s4) 2px var(--s3); display:flex; align-items:center; gap:var(--s3); }
  .vigie-sh::after { content:""; flex:1; height:1px; background:var(--line); }
  .vigie-sh:first-of-type { margin-top:var(--s4); }
  /* Sprint 19 - User strategy panel */
  .strategiecard .us-grid { display:grid; grid-template-columns:1fr; gap:var(--s2); margin:var(--s35) 0; padding-bottom:var(--s35); border-bottom:1px solid var(--line); }
  .strategiecard .us-row { display:flex; align-items:baseline; gap:var(--s35); padding:var(--s15) 0; }
  .strategiecard .us-k { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); min-width:200px; }
  .strategiecard .us-v { font-family:var(--fm); font-size:var(--t-base); color:var(--ink); font-variant-numeric:tabular-nums; }
  .strategiecard .us-desc { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); line-height:1.55; font-style:italic; margin-top:var(--s35); }
  .strategiecard .us-cta { font-family:var(--fm); margin:var(--s2) 0 14px; padding:var(--s3) var(--s35); border-left:2px solid var(--accent-red, #c44); background:color-mix(in srgb, var(--accent-red, #c44) 5%, transparent); border-radius:var(--r0); }
  .strategiecard .us-cta.valid { border-left-color:var(--accent-green, #4a8); background:color-mix(in srgb, var(--accent-green, #4a8) 4%, transparent); }
  .strategiecard .us-cta-h { font-size:var(--t-data); color:var(--steel); text-transform:uppercase; letter-spacing:.05em; margin-bottom:var(--s15); }
  .strategiecard .us-cta-b { font-size:var(--t-base); color:var(--ink); line-height:1.55; }
  .strategiecard .us-cta-f { font-size:var(--t-data); color:var(--steel); margin-top:var(--s2); font-family:var(--fm-mono, monospace); }
  .strategiecard .us-cta-f code { background:color-mix(in srgb, var(--ink) 6%, transparent); padding:2px 6px; border-radius:var(--r0); font-size:var(--t-data); }
  .strategiecard .us-construction { font-family:var(--fm); margin:var(--s2) 0 14px; padding:var(--s3) var(--s35); border-left:2px solid var(--warn); background:color-mix(in srgb, var(--warn) 5%, transparent); border-radius:var(--r0); }
  .strategiecard .us-cstr-h { font-size:var(--t-data); color:var(--warn); text-transform:uppercase; letter-spacing:.05em; font-weight:600; margin-bottom:var(--s15); }
  .strategiecard .us-cstr-b { font-size:var(--t-base); color:var(--ink); line-height:1.6; }
  /* F7 add 29/05 - Positions en vol disclosuregle (entry/target/stop/triggers manquants) */
  .blindcard { border-left:2px solid var(--bear); padding-left:var(--s35) !important; }
  .blindcard .ba-row { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .blindcard .ba-row:last-child { border-bottom:none; }
  .blindcard .ba-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s1); }
  .blindcard .ba-tk { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .blindcard .ba-conv { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); padding:1px 6px; background:color-mix(in srgb,var(--ink) 8%,transparent); border-radius:var(--r1); }
  .blindcard .ba-since { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:auto; }
  .blindcard .ba-missing { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); opacity:.85; }
  .blindcard .ba-missing b { color:var(--bear); font-weight:600; }
  /* Sprint 5/6 - Copilot interventions panel */
  .copilotcard .cp-row { padding:var(--s3) var(--s35); border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); cursor:pointer; transition:background .15s; }
  .copilotcard .cp-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); border-radius:var(--r2); }
  .copilotcard .cp-row:last-child { border-bottom:none; }
  .copilotcard .cp-row.cp-flagged { border-left:2px solid var(--bear); padding-left:var(--s3); background:color-mix(in srgb,var(--bear) 3%,transparent); }
  .copilotcard .cp-biases { display:flex; gap:var(--s15); flex-wrap:wrap; margin-top:var(--s2); }
  .copilotcard .cp-bias { font-family:var(--fm); font-size:var(--t-data); padding:2px 8px; border-radius:var(--r1); background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); letter-spacing:.03em; }
  .copilotcard .cp-brief-wrap { max-height:0; overflow:hidden; opacity:0; transition:max-height .3s ease, opacity .2s ease, margin .3s ease; }
  .copilotcard .cp-row.open .cp-brief-wrap { max-height:600px; opacity:1; margin-top:var(--s25); }
  .copilotcard .cp-brief-label { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .copilotcard .cp-brief { font-family:var(--fm); font-size:var(--t-base); color:var(--ink); line-height:1.6; padding:var(--s25) 12px; background:color-mix(in srgb,var(--ink) 4%,transparent); border-radius:var(--r2); border-left:2px solid color-mix(in srgb,var(--ink) 15%,transparent); }
  .copilotcard .cp-head { display:flex; align-items:center; gap:var(--s3); flex-wrap:wrap; margin-bottom:var(--s15); }
  .copilotcard .cp-tk { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .copilotcard .cp-dtype { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.15em; text-transform:uppercase; color:var(--steel); }
  .copilotcard .cp-ver { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.15em; font-weight:600; padding:2px 6px; border-radius:var(--r1); }
  .copilotcard .cp-ver.ok { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .copilotcard .cp-ver.warn { background:color-mix(in srgb,var(--warn) 14%,transparent); color:var(--warn); }
  .copilotcard .cp-ver.bad { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .copilotcard .cp-date { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .copilotcard .cp-anc { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); line-height:1.45; opacity:.85; }
  .copilotcard .cp-outc { display:inline-block; margin-top:var(--s15); font-family:var(--fb); font-size:var(--t-data); letter-spacing:.12em; padding:2px 6px; border-radius:var(--r1); }
  .copilotcard .cp-outc.ok { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .copilotcard .cp-outc.bad { background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); }
  /* Sprint 6 - Narrative clusters panel */
  .narrativecard .nv-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--s3); margin:var(--s35) 0 18px; }
  .narrativecard .nv-cluster { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s35) 16px; }
  .narrativecard .nv-cl-head { display:flex; align-items:baseline; gap:var(--s2); margin-bottom:var(--s15); flex-wrap:wrap; }
  .narrativecard .nv-cl-name { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); flex:1; min-width:0; }
  .narrativecard .nv-cl-overlap { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.12em; padding:2px 6px; border-radius:var(--r1); font-weight:600; }
  .narrativecard .nv-cl-overlap.high { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .narrativecard .nv-cl-overlap.mid { background:color-mix(in srgb,var(--warn) 14%,transparent); color:var(--warn); }
  .narrativecard .nv-cl-overlap.low { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .narrativecard .nv-cl-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; }
  .narrativecard .nv-cl-tks { font-family:var(--fm); font-size:var(--t-data); color:var(--ink); margin-bottom:var(--s15); opacity:.8; font-variant-numeric:tabular-nums; }
  .narrativecard .nv-cl-driv { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); line-height:1.4; }
  .narrativecard .nv-split { display:grid; grid-template-columns:1fr 1fr; gap:var(--s4); border-top:1px solid var(--line); padding-top:var(--s35); }
  .narrativecard .nv-h { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .narrativecard .nv-line { display:flex; align-items:baseline; gap:var(--s2); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); font-size:var(--t-data2); }
  .narrativecard .nv-line:last-child { border-bottom:none; }
  .narrativecard .nv-tk { font-family:var(--fm); font-weight:600; color:var(--ink); min-width:70px; }
  .narrativecard .nv-with { font-family:var(--fm); color:var(--steel); font-size:var(--t-data); }
  .narrativecard .nv-why { font-family:var(--fm); color:var(--ink); opacity:.85; line-height:1.4; flex:1; }
  @media (max-width:980px) { .narrativecard .nv-split { grid-template-columns:1fr; } }
  /* Sprint 9 - Conversations recentes */
  .conversationscard .cv-row { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .conversationscard .cv-row:last-child { border-bottom:none; }
  .conversationscard .cv-meta { display:flex; align-items:center; gap:var(--s2); margin-bottom:var(--s15); font-family:var(--fb); font-size:var(--t-data); letter-spacing:.14em; text-transform:uppercase; }
  .conversationscard .cv-role { font-weight:600; padding:2px 6px; border-radius:var(--r1); }
  .conversationscard .cv-role.user { background:color-mix(in srgb,var(--id) 14%,transparent); color:var(--id); }
  .conversationscard .cv-role.assistant { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--ink); }
  .conversationscard .cv-surf { color:var(--steel); }
  .conversationscard .cv-date { margin-left:auto; color:var(--steel); font-variant-numeric:tabular-nums; }
  .conversationscard .cv-content { font-family:var(--fm); font-size:var(--t-data2); line-height:1.45; color:var(--ink); opacity:.85; }
  .conversationscard .cv-user .cv-content { color:var(--ink); opacity:.95; }
  /* Sprint 9.d - Soft signals panel */
  .chatsigcard .cs-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--s35); margin-top:var(--s35); }
  .chatsigcard .cs-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s3) var(--s35); }
  .chatsigcard .cs-kind { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s25); }
  .chatsigcard .cs-row { padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .chatsigcard .cs-row:last-child { border-bottom:none; }
  .chatsigcard .cs-meta { display:flex; align-items:baseline; gap:var(--s2); margin-bottom:var(--s1); }
  .chatsigcard .cs-target { font-family:var(--fm); font-weight:600; font-size:var(--t-data2); color:var(--ink); }
  .chatsigcard .cs-val { font-family:var(--fm); font-size:var(--t-data); font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); margin-left:auto; }
  .chatsigcard .cs-val.neg { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .chatsigcard .cs-val.pos { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .chatsigcard .cs-val.neu { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .chatsigcard .cs-quote { font-family:var(--fm); font-size:var(--t-data2); font-style:italic; color:var(--ink); opacity:.85; line-height:1.4; margin-bottom:3px; }
  .chatsigcard .cs-note { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); line-height:1.4; }
  /* Layer 2 - Conceptions du bot */
  .conceptionscard .bc-row { padding:var(--s35) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); cursor:pointer; }
  .conceptionscard .bc-row:last-child { border-bottom:none; }
  .conceptionscard .bc-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); border-radius:var(--r2); }
  .conceptionscard .bc-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s2); flex-wrap:wrap; }
  .conceptionscard .bc-target { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .conceptionscard .bc-kind { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); }
  .conceptionscard .bc-conv { font-family:var(--fm); font-size:var(--t-data); font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); font-weight:600; }
  .conceptionscard .bc-conv.high { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .conceptionscard .bc-conv.mid { background:color-mix(in srgb,var(--warn) 14%,transparent); color:var(--warn); }
  .conceptionscard .bc-conv.low { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .conceptionscard .bc-val { font-family:var(--fm); font-size:var(--t-data); font-variant-numeric:tabular-nums; padding:1px 6px; border-radius:var(--r1); }
  .conceptionscard .bc-val.neg { background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); }
  .conceptionscard .bc-val.pos { background:color-mix(in srgb,var(--acc) 14%,transparent); color:var(--acc); }
  .conceptionscard .bc-val.neu { background:color-mix(in srgb,var(--ink) 8%,transparent); color:var(--steel); }
  .conceptionscard .bc-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .conceptionscard .bc-text { font-family:var(--fm); font-size:var(--t-base); line-height:1.55; color:var(--ink); opacity:.88; max-height:62px; overflow:hidden; position:relative; transition:max-height .3s ease; }
  .conceptionscard .bc-text::after { content:""; position:absolute; bottom:0; left:0; right:0; height:24px; background:linear-gradient(to bottom, transparent, var(--paper, #f5efe3)); pointer-events:none; transition:opacity .2s ease; }
  .conceptionscard .bc-row.open .bc-text { max-height:600px; }
  .conceptionscard .bc-row:hover .bc-text::after, .conceptionscard .bc-row.open .bc-text::after { opacity:0; }
  /* Layer 3 - Preferences calibrees */
  .preferencescard .pr-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:var(--s35); margin-top:var(--s35); }
  .preferencescard .pr-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s3) var(--s35); }
  .preferencescard .pr-h { display:flex; align-items:baseline; gap:var(--s2); margin-bottom:var(--s25); }
  .preferencescard .pr-kind { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--ink); font-weight:600; }
  .preferencescard .pr-meta { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .preferencescard .pr-row { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:var(--t-data2); }
  .preferencescard .pr-row:last-child { border-bottom:none; }
  .preferencescard .pr-key { font-family:var(--fm); font-weight:500; color:var(--ink); min-width:60px; }
  .preferencescard .pr-mid { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; }
  .preferencescard .pr-num { margin-left:auto; font-variant-numeric:tabular-nums; }
  .preferencescard .pr-num.pos { color:var(--acc); }
  .preferencescard .pr-num.neg { color:var(--bear); }
  .preferencescard .pr-num.neu { color:var(--steel); }
  .preferencescard .pr-win { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); min-width:50px; text-align:right; }
  /* Sprint 12 - Ticker axes */
  .axescard .ax-group { background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); padding:var(--s35) 16px; margin-top:var(--s35); }
  .axescard .ax-h { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s25); padding-bottom:var(--s2); border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .axescard .ax-macro { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .axescard .ax-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .axescard .ax-row { display:grid; grid-template-columns:78px 1fr; gap:var(--s35); padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .axescard .ax-row:last-child { border-bottom:none; }
  .axescard .ax-tk { font-family:var(--fm); font-weight:600; font-size:var(--t-data2); color:var(--ink); }
  .axescard .ax-fields { display:flex; flex-direction:column; gap:3px; }
  .axescard .ax-f { font-family:var(--fm); font-size:var(--t-data); color:var(--ink); opacity:.82; line-height:1.4; }
  .axescard .ax-l { display:inline-block; font-family:var(--fb); font-size:var(--t-data); letter-spacing:.14em; text-transform:uppercase; color:var(--steel); width:50px; }
  /* Sprint 13 - Factor exposures + Stress + Trajectory */
  .factorscard .fe-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .factorscard .fe-row:last-child { border-bottom:none; }
  .factorscard .fe-row.fe-composite { padding:var(--s35) 14px; margin:0 -14px 8px; background:color-mix(in srgb,var(--bear) 6%,transparent); border-left:2px solid var(--bear); border-radius:var(--r0); border-bottom:none; }
  .factorscard .fe-row.fe-composite .fe-name { font-weight:600; }
  .factorscard .fe-comp-note { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-top:var(--s15); line-height:1.45; font-style:italic; }
  .factorscard .fe-th { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:2px; padding:0 4px; background:color-mix(in srgb,var(--ink) 6%,transparent); border-radius:var(--r1); }
  .factorscard .fe-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .factorscard .fe-name { font-family:var(--fm); font-weight:500; font-size:var(--t-base); color:var(--ink); flex:1; }
  .factorscard .fe-pct { font-family:var(--fm); font-size:var(--t-base); font-weight:600; font-variant-numeric:tabular-nums; }
  .factorscard .fe-pct.high { color:var(--bear); }
  .factorscard .fe-pct.mid { color:var(--warn); }
  .factorscard .fe-pct.low { color:var(--acc); }
  .factorscard .fe-eur { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; min-width:75px; text-align:right; }
  .factorscard .fe-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:var(--s1) 0 6px; }
  .factorscard .fe-fill { height:100%; border-radius:var(--r1); }
  .factorscard .fe-fill.high { background:var(--bear); }
  .factorscard .fe-fill.mid { background:var(--warn); }
  .factorscard .fe-fill.low { background:var(--acc); }
  .factorscard .fe-tks { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; }
  .stresscard .st-row { display:flex; align-items:baseline; gap:var(--s35); padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .stresscard .st-row:last-child { border-bottom:none; }
  .stresscard .st-name { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); flex:1; }
  .stresscard .st-impact { display:flex; align-items:baseline; gap:var(--s3); }
  .stresscard .st-pct { font-family:var(--fm); font-size:var(--t-base); font-weight:600; font-variant-numeric:tabular-nums; min-width:60px; text-align:right; }
  .stresscard .st-pct.pos { color:var(--acc); }
  .stresscard .st-pct.danger { color:var(--bear); }
  .stresscard .st-pct.warn { color:var(--warn); }
  .stresscard .st-pct.neu { color:var(--steel); }
  .stresscard .st-eur { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; min-width:90px; text-align:right; }
  .stresscard .st-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); min-width:40px; text-align:right; font-variant-numeric:tabular-nums; }
  .trajcard .tr-hero { font-family:var(--fm); font-size:var(--t-h3); font-weight:500; color:var(--ink); padding:var(--s35) 0 16px; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); margin-bottom:var(--s2); display:flex; align-items:baseline; gap:var(--s2); }
  .trajcard .tr-row { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:var(--t-data2); }
  .trajcard .tr-row:last-child { border-bottom:none; }
  .trajcard .tr-key { font-family:var(--fm); color:var(--ink); flex:1; }
  .trajcard .tr-from, .trajcard .tr-to { font-variant-numeric:tabular-nums; color:var(--ink); opacity:.85; min-width:48px; text-align:right; }
  .trajcard .tr-arr { color:var(--steel); font-size:var(--t-data); }
  .trajcard .tr-delta { font-variant-numeric:tabular-nums; min-width:64px; text-align:right; font-weight:500; }
  .trajcard .tr-delta.pos { color:var(--acc); }
  .trajcard .tr-delta.neg { color:var(--bear); }
  .trajcard .tr-delta.neu { color:var(--steel); }
  /* Sprint 14 - SPOF + Mauboussin + Valo */
  .spofcard .sp-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .spofcard .sp-row:last-child { border-bottom:none; }
  .spofcard .sp-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .spofcard .sp-node { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); flex:1; }
  .spofcard .sp-pct { font-family:var(--fm); font-size:var(--t-base); font-weight:600; font-variant-numeric:tabular-nums; }
  .spofcard .sp-pct.high { color:var(--bear); }
  .spofcard .sp-pct.mid { color:var(--warn); }
  .spofcard .sp-pct.low { color:var(--acc); }
  .spofcard .sp-eur { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; min-width:80px; text-align:right; }
  .spofcard .sp-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; min-width:38px; text-align:right; }
  .spofcard .sp-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:var(--s1) 0 6px; }
  .spofcard .sp-fill { height:100%; border-radius:var(--r1); }
  .spofcard .sp-fill.high { background:var(--bear); }
  .spofcard .sp-fill.mid { background:var(--warn); }
  .spofcard .sp-fill.low { background:var(--acc); }
  .spofcard .sp-deps { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-row { display:grid; grid-template-columns:70px 50px 65px 75px 75px 75px 65px auto; align-items:center; gap:var(--s3); padding:var(--s2) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:var(--t-data2); }
  .mauboussincard .ms-frag { font-family:var(--fm); font-size:var(--t-data); padding:2px 7px; border-radius:var(--r1); background:color-mix(in srgb,var(--bear) 14%,transparent); color:var(--bear); letter-spacing:.03em; justify-self:start; }
  .mauboussincard .ms-stopd { font-family:var(--fm); color:var(--steel); }
  .mauboussincard .ms-stopd.outlier { color:var(--bear); font-weight:600; background:color-mix(in srgb,var(--bear) 10%,transparent); padding:1px 5px; border-radius:var(--r1); }
  .mauboussincard .ms-row:last-child { border-bottom:none; }
  .mauboussincard .ms-tk { font-family:var(--fm); font-weight:600; color:var(--ink); }
  .mauboussincard .ms-conv { font-family:var(--fm); color:var(--steel); }
  .mauboussincard .ms-fade { font-family:var(--fm); padding:1px 5px; border-radius:var(--r1); font-size:var(--t-data); text-align:center; }
  .mauboussincard .ms-fade.low { background:color-mix(in srgb,var(--acc) 12%,transparent); color:var(--acc); }
  .mauboussincard .ms-fade.mid { background:color-mix(in srgb,var(--warn) 12%,transparent); color:var(--warn); }
  .mauboussincard .ms-fade.high { background:color-mix(in srgb,var(--bear) 12%,transparent); color:var(--bear); }
  .mauboussincard .ms-target, .mauboussincard .ms-actual { font-family:var(--fm); color:var(--ink); opacity:.85; text-align:right; font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-gap { font-family:var(--fm); font-weight:600; text-align:right; font-variant-numeric:tabular-nums; }
  .mauboussincard .ms-gap.pos { color:var(--acc); }
  .mauboussincard .ms-gap.neg { color:var(--bear); }
  .mauboussincard .ms-gap.neu { color:var(--steel); }
  .valocard .vb-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .valocard .vb-row:last-child { border-bottom:none; }
  .valocard .vb-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .valocard .vb-tk { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .valocard .vb-pe { font-family:var(--fm); font-size:var(--t-data2); color:var(--bear); font-variant-numeric:tabular-nums; margin-left:auto; }
  .valocard .vb-priced { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); opacity:.9; line-height:1.45; margin-bottom:var(--s1); font-style:italic; }
  .valocard .vb-rat { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); line-height:1.4; }
  @media (max-width:980px) { .mauboussincard .ms-row { grid-template-columns:60px 40px 1fr 65px; } .mauboussincard .ms-target, .mauboussincard .ms-actual { display:none; } }
  /* Sprint 15 - Kill-criteria */
  .killcard .kc-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 5%,transparent); }
  .killcard .kc-row:last-child { border-bottom:none; }
  .killcard .kc-row.triggered { border-left:3px solid var(--bear); padding-left:var(--s3); margin-left:-12px; }
  .killcard .kc-row.at_risk { border-left:3px solid var(--warn); padding-left:var(--s3); margin-left:-12px; }
  .killcard .kc-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .killcard .kc-tk { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .killcard .kc-status { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.15em; text-transform:uppercase; font-weight:600; padding:2px 7px; border-radius:var(--r1); }
  .killcard .kc-status.triggered { background:color-mix(in srgb,var(--bear) 16%,transparent); color:var(--bear); }
  .killcard .kc-status.at_risk { background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }
  .killcard .kc-conf { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .killcard .kc-reason { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); opacity:.88; line-height:1.5; margin-bottom:var(--s1); }
  .killcard .kc-ev { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; }
  /* 30/05 nuit -- arc V2 panels (vigilance + cohorte + wire activity) */
  .vgcard .vg-row { padding:var(--s25) 12px; border-radius:var(--r1); margin-bottom:var(--s15); background:color-mix(in srgb,var(--ink) 2%,transparent); border-left:3px solid transparent; }
  .vgcard .vg-row.vg-ok { border-left-color:var(--acc); }
  .vgcard .vg-row.vg-info { border-left-color:var(--steel); opacity:.75; }
  .vgcard .vg-row.vg-warn { border-left-color:var(--warn); background:color-mix(in srgb,var(--warn) 6%,transparent); }
  .vgcard .vg-row.vg-alert { border-left-color:var(--bear); background:color-mix(in srgb,var(--bear) 8%,transparent); }
  .vgcard .vg-row.vg-wait { border-left-color:color-mix(in srgb,var(--steel) 40%,transparent); opacity:.6; }
  .vgcard .vg-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s1); }
  .vgcard .vg-emoji { font-size:var(--t-base); }
  .vgcard .vg-name { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.05em; text-transform:uppercase; font-weight:600; color:var(--ink); }
  .vgcard .vg-status { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-left:auto; }
  .vgcard .vg-msg { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); opacity:.85; line-height:1.5; }
  .v2cohortcard .v2-grid { display:grid; grid-template-columns:1fr 1fr; gap:var(--s35); margin-top:var(--s3); }
  .v2cohortcard .v2-side { padding:var(--s35); border:1px solid var(--line); border-radius:var(--r2); background:color-mix(in srgb,var(--ink) 2%,transparent); }
  .v2cohortcard .v2-current { border-left:3px solid var(--acc); }
  .v2cohortcard .v2-legacy { border-left:3px solid color-mix(in srgb,var(--steel) 50%,transparent); opacity:.85; }
  .v2cohortcard .v2-label { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; font-weight:600; color:var(--steel); margin-bottom:var(--s2); }
  .v2cohortcard .v2-stat-row { display:flex; gap:var(--s35); align-items:baseline; font-family:var(--fm); font-size:var(--t-base); font-variant-numeric:tabular-nums; }
  .v2cohortcard .v2-stat-n { font-weight:600; color:var(--ink); }
  .v2cohortcard .v2-stat-rg, .v2cohortcard .v2-stat-bk { color:var(--steel); font-size:var(--t-data2); }
  .v2cohortcard .v2-status.v2-empty { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); font-style:italic; line-height:1.4; }
  .wactcard .wact-grid { display:flex; gap:var(--s35); margin:var(--s3) 0 16px; }
  .wactcard .wact-cell { flex:1; padding:var(--s25) 14px; background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); }
  .wactcard .wact-label { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; margin-bottom:var(--s1); }
  .wactcard .wact-v { font-family:var(--fm); font-size:var(--t-base); color:var(--ink); }
  .wactcard .wact-recent-head { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); font-weight:600; margin-bottom:var(--s2); padding-top:var(--s15); border-top:1px solid var(--line); }
  .wactcard .wact-recent { display:flex; gap:var(--s3); align-items:baseline; padding:var(--s15) 0; font-family:var(--fm); font-size:var(--t-data2); border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .wactcard .wact-recent:last-child { border-bottom:none; }
  .wactcard .wact-tk { font-family:var(--fb); font-weight:600; min-width:60px; color:var(--ink); }
  .wactcard .wact-when { color:var(--steel); font-variant-numeric:tabular-nums; }
  .wactcard .wact-sev { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.14em; text-transform:uppercase; font-weight:600; padding:1px 6px; border-radius:var(--r1); }
  .wactcard .wact-sev.wact-catastrophic, .wactcard .wact-sev.wact-high { background:color-mix(in srgb,var(--bear) 16%,transparent); color:var(--bear); }
  .wactcard .wact-sev.wact-medium { background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }
  .wactcard .wact-sev.wact-low, .wactcard .wact-sev.wact-unknown { background:color-mix(in srgb,var(--steel) 12%,transparent); color:var(--steel); }
  .wactcard .wact-items { margin-left:auto; color:var(--steel); font-variant-numeric:tabular-nums; }
  @media (max-width:980px) {
    .v2cohortcard .v2-grid { grid-template-columns:1fr; }
    .wactcard .wact-grid { flex-direction:column; }
    .wactcard .wact-recent { flex-wrap:wrap; gap:var(--s15) 12px; }
    .wactcard .wact-items { margin-left:0; flex-basis:100%; font-size:var(--t-data); }
    /* wrappercard PEA/CTO alloc -- seul vrai panel a casser mobile (3-4 wrappers horizontal) */
    .wrappercard .wr-alloc { flex-direction:column; gap:var(--s3); }
    /* Note : autres panels (chatcard/chatsig/conversations/conceptions/preferences/axes/traj/fx)
       utilisent deja repeat(auto-fit, minmax(280px,1fr)) = responsive natif sans media query. */
  }
  /* Sprint 16 - Wrapper PEA/CTO + FX + Benchmark */
  .wrappercard .wr-alloc { display:flex; gap:var(--s4); margin:var(--s35) 0 18px; padding-bottom:var(--s35); border-bottom:1px solid var(--line); }
  .wrappercard .wr-row { flex:1; padding:var(--s3) var(--s35); background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); display:flex; flex-direction:column; gap:var(--s1); }
  .wrappercard .wr-key { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; }
  .wrappercard .wr-pct { font-family:var(--fm); font-size:var(--t-h2); font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .wrappercard .wr-eur { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); font-variant-numeric:tabular-nums; }
  .wrappercard .wr-section { margin-top:var(--s35); }
  .wrappercard .wr-sh { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .wrappercard .wr-mis { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 3%,transparent); font-size:var(--t-data2); }
  .wrappercard .wr-mis:last-child { border-bottom:none; }
  .wrappercard .wr-mis-tk { font-family:var(--fm); font-weight:600; color:var(--ink); min-width:80px; }
  .wrappercard .wr-mis-pct { font-family:var(--fm); color:var(--ink); margin-left:auto; font-variant-numeric:tabular-nums; min-width:55px; text-align:right; }
  .wrappercard .wr-mis-pct.neg { color:var(--bear); }
  .wrappercard .wr-mis-eur { font-family:var(--fm); color:var(--steel); font-variant-numeric:tabular-nums; min-width:80px; text-align:right; }
  .fxcard .fx-row { padding:var(--s3) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .fxcard .fx-row:last-child { border-bottom:none; }
  .fxcard .fx-head { display:flex; align-items:baseline; gap:var(--s3); margin-bottom:var(--s15); }
  .fxcard .fx-cur { font-family:var(--fm); font-weight:600; font-size:var(--t-base); color:var(--ink); }
  .fxcard .fx-pct { font-family:var(--fm); font-size:var(--t-base); font-weight:600; font-variant-numeric:tabular-nums; }
  .fxcard .fx-pct.high { color:var(--bear); }
  .fxcard .fx-pct.mid { color:var(--warn); }
  .fxcard .fx-pct.low { color:var(--acc); }
  .fxcard .fx-eur { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:auto; font-variant-numeric:tabular-nums; }
  .fxcard .fx-n { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); min-width:32px; text-align:right; font-variant-numeric:tabular-nums; }
  .fxcard .fx-bar { height:5px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r1); overflow:hidden; margin:var(--s1) 0 6px; }
  .fxcard .fx-fill { height:100%; border-radius:var(--r1); }
  .fxcard .fx-fill.high { background:var(--bear); }
  .fxcard .fx-fill.mid { background:var(--warn); }
  .fxcard .fx-fill.low { background:var(--acc); }
  .fxcard .fx-item { cursor:pointer; }
  .fxcard .fx-chev { color:var(--steel); margin-left:6px; transition:transform .2s ease; flex-shrink:0; }
  .fxcard .fx-item.open .fx-chev { transform:rotate(180deg); }
  .fxcard .fx-sub { max-height:0; overflow:hidden; opacity:0; transition:max-height .3s ease, opacity .2s ease, margin .3s ease; }
  .fxcard .fx-item.open .fx-sub { max-height:360px; opacity:1; margin:var(--s1) 0 6px; }
  .fxcard .fx-stk { display:flex; align-items:center; gap:var(--s3); padding:var(--s15) 6px 5px 16px; font-size:var(--t-data2); border-left:2px solid var(--line2); margin-left:3px; }
  .fxcard .fx-stk .gnm { color:var(--ink); }
  .fxcard .fx-stk .gtk { color:var(--steel); font-family:var(--fm); font-size:var(--t-data); }
  .fxcard .fx-stk .gpc { margin-left:auto; color:var(--steel); font-family:var(--fm); font-size:var(--t-data); font-variant-numeric:tabular-nums; }
  .fxcard .fx-stk .gw { color:var(--ink); font-family:var(--fm); min-width:62px; text-align:right; font-variant-numeric:tabular-nums; }
  .benchcard .bm-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:var(--s4); margin:var(--s35) 0; }
  .benchcard .bm-cell { padding:var(--s35) 18px; background:color-mix(in srgb,var(--ink) 3%,transparent); border:1px solid var(--line); border-radius:var(--r2); }
  .benchcard .bm-h { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); font-weight:600; margin-bottom:var(--s15); }
  .benchcard .bm-v { font-family:var(--fm); font-size:var(--t-h2); font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; }
  .benchcard .bm-v.pos { color:var(--acc); }
  .benchcard .bm-v.neg { color:var(--bear); }
  .benchcard .bm-v.neu { color:var(--steel); }
  .benchcard .bm-foot { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); margin-top:var(--s25); padding-top:var(--s25); border-top:1px solid var(--line); }
  .benchcard .bm-warn { font-family:var(--fm); font-size:var(--t-data2); color:var(--warn); background:color-mix(in srgb,var(--warn) 8%,transparent); padding:var(--s2) 12px; border-radius:var(--r2); margin:var(--s3) 0 0; }
  /* Sprint 17 - Data-defined clusters */
  .clustercard .dc-sub { margin-top:var(--s35); }
  .clustercard .dc-sh { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.18em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s2); }
  .clustercard .dc-row { display:flex; align-items:baseline; gap:var(--s3); padding:var(--s15) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); font-size:var(--t-data2); }
  .clustercard .dc-row:last-child { border-bottom:none; }
  .clustercard .dc-pair { font-family:var(--fm); font-weight:500; color:var(--ink); flex:1; }
  .clustercard .dc-corr { font-family:var(--fm); color:var(--bear); font-weight:600; font-variant-numeric:tabular-nums; }
  .clustercard .dc-mix { padding:var(--s25) 0; border-bottom:1px solid color-mix(in srgb,var(--ink) 4%,transparent); }
  .clustercard .dc-mix:last-child { border-bottom:none; }
  .clustercard .dc-mix-h { font-family:var(--fb); font-size:var(--t-data); letter-spacing:.14em; text-transform:uppercase; color:var(--steel); margin-bottom:var(--s15); }
  .clustercard .dc-mix-members { font-family:var(--fm); font-size:var(--t-data2); color:var(--ink); line-height:1.5; }
  .clustercard .dc-mf { color:var(--steel); font-size:var(--t-data); margin-left:2px; }
  /* Sprint 7 - Chat surface */
  .chatcard .chat-log { max-height:340px; overflow-y:auto; padding:var(--s3) 0; margin-bottom:var(--s35); display:flex; flex-direction:column; gap:var(--s3); }
  .chatcard .chat-log:empty { display:none; }
  .chatcard .chat-msg { font-family:var(--fm); font-size:var(--t-base); line-height:1.5; padding:var(--s25) 14px; border-radius:var(--r2); max-width:88%; }
  .chatcard .chat-user { align-self:flex-end; background:color-mix(in srgb,var(--id) 14%,transparent); color:var(--ink); }
  .chatcard .chat-assistant { align-self:flex-start; background:color-mix(in srgb,var(--ink) 5%,transparent); color:var(--ink); }
  .chatcard .chat-form { display:flex; gap:var(--s3); align-items:flex-start; }
  .chatcard .chat-input { flex:1; font-family:var(--fm); font-size:var(--t-base); padding:var(--s25) 12px; border:1px solid var(--line2); background:var(--panel); color:var(--ink); border-radius:var(--r2); resize:vertical; min-height:54px; }
  .chatcard .chat-input:focus { outline:none; border-color:var(--id); }
  .chatcard .chat-send { font-family:var(--fb); font-size:var(--t-data2); letter-spacing:.15em; text-transform:uppercase; padding:0 22px; height:54px; border-radius:var(--r2); border:1px solid var(--id); background:var(--id); color:var(--bg); cursor:pointer; transition:.15s; }
  .chatcard .chat-send:hover:not(:disabled) { opacity:.85; }
  .chatcard .chat-send:disabled { opacity:.5; cursor:default; }
  .chatcard .chat-foot { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-top:var(--s25); }
  .chatcard .chat-idle-clear { align-self:center; background:color-mix(in srgb,var(--steel) 8%,transparent); color:var(--steel); font-style:italic; font-size:var(--t-data2); padding:var(--s2) 14px; }
  /* CANONIQUE charte §15 : switch light/dark TOUJOURS visible bas-gauche.
     SEULE position:fixed est canonique (suit la vision user au scroll).
     L'esthetique reste soft/discrete (border 1px --line, color --steel,
     bg --bg). z-index 90 = au-dessus du tape (80) mais sous loupe (1000). */
  /* Mode toggle vit dans .foot comme un nitem regular (02/06 user). */
  .modetgl { display:flex; align-items:center; justify-content:center;
             width:48px; height:48px; border-radius:var(--r3);
             border:none; background:transparent; color:var(--steel);
             cursor:pointer; transition:.15s; padding:0; }
  .modetgl:hover { background:color-mix(in srgb,var(--ink) 4%,transparent); color:var(--ink); }
  .modetgl svg { width:26px; height:26px; }
  /* duplicate .modetgl:hover supprime 31/05 close W14b -- override la regle
     canonique §15 (background:var(--ink) color:var(--bg)) en noir-sur-noir.
     La regle canonique en haut du fichier est l'unique source de verite. */
  .hero, .pfcard { box-shadow:var(--elev); }
  .card, .kpi, .gauge, .plan { box-shadow:var(--elev); }
  .loupe-card { box-shadow:var(--elev3); }
  .nitem.on { box-shadow:inset 0 0 20px -10px color-mix(in srgb,var(--id) 55%,transparent); }
  .nitem.on svg { filter:drop-shadow(0 0 6px color-mix(in srgb,var(--id) 70%,transparent)); }
  .tape { box-shadow:none; }
  .row[data-tk]:hover, .dt tbody tr:hover td, .th-row:hover, .sbrow:hover { background:color-mix(in srgb,var(--ink) 3.5%,transparent); }
  .brk { margin-bottom:var(--s4); }
  .brk-h { display:flex; justify-content:space-between; align-items:baseline; margin:0 2px 10px; flex-wrap:wrap; gap:var(--s2); }
  .brk-n { font-family:var(--fm); font-weight:500; font-size:var(--t-h3); letter-spacing:-.01em; font-variant-numeric:tabular-nums; }
  .brk-note { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-left:var(--s2); }
  .brk-tot { font-family:var(--fm); font-size:var(--t-base); color:var(--ink); } .brk-tot span { color:var(--steel); font-size:var(--t-data2); }
  .brk-body { display:flex; gap:var(--s4); align-items:flex-start; flex-wrap:wrap; }
  .brk-viz { flex:0 0 320px; max-width:320px; }
  /* Pass 16-ter : retrait du mask fade qui effacait visuellement les graphs
     Progress quand ils etaient au bord droit visible. Juste overflow-x:auto
     propre. La scrollbar suffit pour signaler "il y a plus a droite". */
  .brk-tbl { flex:1 1 0; min-width:0; max-width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .brk-tbl table.dt { width:max-content; min-width:100%; }
  .brk-bars { display:flex; flex-direction:column; gap:2px; }
  .brk-row { display:grid; grid-template-columns:minmax(110px,1.3fr) minmax(60px,2.5fr) 42px 56px; align-items:center; gap:var(--s3); padding:var(--s2) 4px; border-radius:var(--r1); transition:background .15s; }
  .brk-row:hover { background:color-mix(in srgb,var(--ink) 3%,transparent); }
  .brk-row-name { display:flex; align-items:center; gap:var(--s2); min-width:0; }
  .brk-row-dot { width:8px; height:8px; border-radius:var(--r-circle); flex:0 0 auto; }
  .brk-row-label { font-family:var(--fb); font-weight:500; font-size:var(--t-data2); color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .brk-row-bar { height:4px; background:color-mix(in srgb,var(--ink) 5%,transparent); border-radius:var(--r0); overflow:hidden; }
  .brk-row-fill { height:100%; border-radius:var(--r0); transition:width .4s cubic-bezier(.2,.8,.2,1); }
  .brk-row-pct { font-family:var(--fm); font-weight:500; font-size:var(--t-data2); color:var(--ink); text-align:right; font-variant-numeric:tabular-nums; }
  .brk-row-val { font-family:var(--fm); font-weight:400; font-size:var(--t-data); color:var(--steel); text-align:right; font-variant-numeric:tabular-nums; }
"""

_DBA_CSS = r"""
<style>
  /* Unified avec .th-grp / .strat-sh / .vigie-sh : flex + after-line subtile */
  .dba-sh { font-family:var(--fm); font-weight:500; font-size:var(--t-data2); letter-spacing:.16em; text-transform:uppercase; color:var(--steel); margin:var(--s4) 2px var(--s3); display:flex; align-items:center; gap:var(--s3); }
  .dba-sh::after { content:""; flex:1; height:1px; background:var(--line); }
  .dba-sh-aside { text-transform:none; letter-spacing:0; color:var(--steel); font-weight:normal; font-size:var(--t-data); margin-left:6px; }
  /* DBA card harmonisee avec .page-star pattern (background panel + border line) */
  .dba-card { padding:var(--s4); border:1px solid var(--line); border-radius:var(--r2); background:var(--panel); margin-bottom:var(--s3); }
  .dba-chrow { display:flex; justify-content:space-between; align-items:baseline; gap:var(--s4); font-family:var(--fm); }
  .dba-chrow .lab { font-weight:600; color:var(--ink); font-size:var(--t-base); }
  .dba-chrow .stat { font-size:var(--t-data); letter-spacing:.06em; text-transform:uppercase; padding:2px 9px; border-radius:var(--r1); border:1px solid var(--line); white-space:nowrap; }
  .dba-chrow .stat.actif { color:var(--acc); border-color:color-mix(in srgb, var(--acc) 30%, var(--line)); }
  .dba-chrow .stat.veille { color:var(--warn); border-color:color-mix(in srgb, var(--warn) 30%, var(--line)); }
  .dba-chrow .stat.non-inst { color:var(--steel); opacity:.7; }
  .dba-meta { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-top:6px; line-height:1.5; }
  .dba-bars { margin-top:var(--s3); }
  /* Bars : couleur = SEVERITE (etat), pas presence. Label + count
     portent la couleur ; la fill l'amplifie. Row a 0 reste typee. */
  .dba-hbar { display:flex; align-items:center; gap:11px; font-family:var(--fm); font-size:var(--t-data2); margin:6px 0; }
  .dba-hbar.zero { opacity:.55; }
  .dba-hlab { width:80px; }
  .dba-haxis { flex:1; height:6px; background:color-mix(in srgb, var(--steel) 12%, transparent); border-radius:var(--r0); overflow:hidden; }
  .dba-hfill { height:100%; background:var(--steel); }
  .dba-hn { width:30px; text-align:right; font-weight:600; }
  .dba-hbar.dormant .dba-hlab,
  .dba-hbar.dormant .dba-hn { color:var(--steel); }
  .dba-hbar.dormant .dba-hfill { background:var(--steel); }
  .dba-hbar.at_risk .dba-hlab,
  .dba-hbar.at_risk .dba-hn { color:var(--warn); font-weight:700; }
  .dba-hbar.at_risk .dba-hfill { background:var(--warn); }
  .dba-hbar.triggered .dba-hlab,
  .dba-hbar.triggered .dba-hn { color:var(--bear); font-weight:700; }
  .dba-hbar.triggered .dba-hfill { background:var(--bear); }
  .dba-count { font-family:var(--fm); font-size:var(--t-base); color:var(--ink); margin-top:var(--s2); font-weight:600; }
  .dba-tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }
  .dba-tag { font-family:var(--fm); font-size:var(--t-data); padding:2px 8px; border-radius:var(--r1); background:color-mix(in srgb, var(--steel) 10%, transparent); color:var(--steel); }
  .dba-cond { font-family:var(--fm); font-size:var(--t-data); color:var(--steel); margin-top:8px; font-style:italic; }
  .dba-honest { font-family:var(--fm); font-size:var(--t-data); color:var(--warn); margin-top:8px; padding:7px 11px; background:color-mix(in srgb, var(--warn) 6%, transparent); border-left:2px solid var(--warn); border-radius:var(--r1); line-height:1.5; }
  .dba-arrow { font-family:var(--fm); font-size:var(--t-data2); color:var(--steel); margin-top:var(--s3); }
  .dba-arrow .v { color:var(--ink); font-weight:600; }

  /* DNA v2 surface d'honnetete : carte calibration Brier vs baseline */
  .calib-card { background:var(--bg); border:1px solid var(--line); border-radius:var(--r3); padding:18px 22px; }
  .calib-row { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  .calib-row .calib-lbl { font-family:var(--fb); font-size:var(--t-meta); letter-spacing:.12em; text-transform:uppercase; color:var(--steel); font-weight:500; }
  .calib-row .calib-val { font-family:var(--fm); font-size:var(--t-h1); font-weight:500; color:var(--ink); font-variant-numeric:tabular-nums; line-height:1; letter-spacing:-.01em; }
  .calib-row .calib-val.muted { color:var(--steel); opacity:.5; }
  .calib-row .calib-val.acc { color:var(--acc); }
  .calib-row .calib-val.warn { color:var(--warn); }
  .calib-row .calib-val.bear { color:var(--bear); }
  .calib-row .calib-baseline { font-family:var(--fm); font-size:var(--t-mini); color:var(--steel); }
  .calib-row .calib-delta { font-family:var(--fm); font-size:var(--t-small); margin-left:auto; padding:2px 9px; border-radius:var(--r-pill); border:1px solid currentColor; font-variant-numeric:tabular-nums; }
  .calib-row .calib-delta.acc { color:var(--acc); }
  .calib-row .calib-delta.bear { color:var(--bear); }
  .calib-axis { position:relative; height:34px; margin:18px 0 8px; }
  .calib-axis .calib-track { position:absolute; left:0; right:0; top:8px; height:4px; background:linear-gradient(90deg, var(--acc), color-mix(in srgb,var(--acc) 40%,var(--steel)) 40%, var(--steel) 50%, color-mix(in srgb,var(--bear) 40%,var(--steel)) 60%, var(--bear)); border-radius:var(--r0); }
  .calib-axis .calib-baseline-tick { position:absolute; top:4px; width:2px; height:12px; background:var(--ink); opacity:.6; border-radius:var(--r0); transform:translateX(-50%); }
  .calib-axis .calib-baseline-tick::after { content:"baseline"; position:absolute; bottom:-14px; left:50%; transform:translateX(-50%); font-family:var(--fm); font-size:var(--t-fine); color:var(--steel); white-space:nowrap; }
  .calib-axis .calib-mark { position:absolute; top:5px; width:10px; height:10px; background:var(--ink); border:2px solid var(--bg); border-radius:var(--r-circle); transform:translateX(-50%); box-shadow:0 0 0 1px var(--ink); }
  .calib-axis .calib-scale { display:flex; justify-content:space-between; position:absolute; left:0; right:0; top:24px; font-family:var(--fm); font-size:var(--t-fine); color:var(--steel); }
  .calib-axis .calib-scale span:nth-child(2) { visibility:hidden; }
  .calib-meta { margin-top:18px; }
  .calib-badge { display:inline-block; font-family:var(--fm); font-size:var(--t-meta); font-weight:500; letter-spacing:.04em; padding:3px 10px; border-radius:var(--r-pill); border:1px solid currentColor; }
  .calib-badge.acc { color:var(--acc); }
  .calib-badge.warn { color:var(--warn); }
  .calib-honest { font-family:var(--fb); font-size:var(--t-mini); color:var(--steel); margin-top:12px; padding:10px 12px; background:var(--panel); border-left:2px solid var(--line2); border-radius:var(--r1); line-height:1.55; }
</style>
"""
