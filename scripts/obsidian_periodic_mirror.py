#!/usr/bin/env python3
"""Cron Mac periodic mirror Obsidian vault PRESAGE.

Run depuis launchd Mac chaque 30min. 3 actions :
  1. DIGEST : genere DIGEST_<date>.md basé sur état DB actuel (signaux 24h,
     macro, decisions du jour). Overwrite idempotent.
  2. FAIT chiffres position : refresh section "Chiffres position (FAIT — date)"
     sur les notes ticker.md pour toutes positions held (qty>0). Append-only
     (1 section par jour, idempotent par date).
  3. SNAPSHOT patrimoine : si Snapshot patrimoine — <date_today>.md n'existe
     pas encore, le créer avec book value + thèses actives + cluster top.

Cf memory project-obsidian-vault-primary-substrate (25/06/2026 doctrine).

Constraint architecture : Mac-side seulement (Obsidian REST API tourne sur
Mac 127.0.0.1, VM ne peut pas atteindre). Donc le cron qui mirror est Mac.

Sortie : log stdout + exit code 0 si OK, !=0 sur erreur. Soft-fail par
section (un fail FAIT ne casse pas le mirror DIGEST).
"""
from __future__ import annotations

import contextlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def mirror_digest(cx: sqlite3.Connection) -> str | None:
    """Mirror digest current state into journal/digests/DIGEST_<date>.md.

    Genere a partir de l'etat DB live (signaux 24h, macro, decisions).
    """
    try:
        from shared import obsidian as obs
    except Exception as e:
        return f"obsidian module import failed: {e}"
    date_iso = _now_iso()
    cx.row_factory = sqlite3.Row
    n_24h_scored = cx.execute(
        "SELECT COUNT(*) c, COUNT(DISTINCT src.name) src FROM signals s "
        "LEFT JOIN sources src ON s.source_id = src.id "
        "WHERE s.timestamp >= datetime('now', '-24 hours') AND COALESCE(s.impact_magnitude, 0) >= 2.0"
    ).fetchone()
    n_24h_raw = cx.execute(
        "SELECT COUNT(*) FROM signals WHERE timestamp >= datetime('now', '-24 hours')"
    ).fetchone()[0]
    top_signals = cx.execute(
        "SELECT s.title, s.impact_magnitude, src.name as source, s.timestamp "
        "FROM signals s LEFT JOIN sources src ON s.source_id = src.id "
        "WHERE s.timestamp >= datetime('now', '-24 hours') "
        "ORDER BY COALESCE(s.impact_magnitude, 0) DESC LIMIT 10"
    ).fetchall()
    dec_today = cx.execute(
        "SELECT id, ticker, decision_type, confidence_pre, substr(reasoning, 1, 120) as r FROM decisions "
        "WHERE date(created_at) = date('now') ORDER BY id DESC"
    ).fetchall()
    pred_resolved_24h = cx.execute(
        "SELECT COUNT(*) FROM predictions WHERE resolved_at >= datetime('now', '-24 hours')"
    ).fetchone()[0]
    pred_due_7d = cx.execute(
        "SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL "
        "AND date(target_date) BETWEEN date('now') AND date('now', '+7 days')"
    ).fetchone()[0]
    n_active = cx.execute("SELECT COUNT(*) FROM theses WHERE status='active'").fetchone()[0]

    regime = "?"
    triggers: list[str] = []
    score = 0.0
    composite_phase = 0
    try:
        from shared.macro_state import current_macro_state
        macro = current_macro_state()
        regime = macro.get("regime", "?")
        triggers = macro.get("regime_triggers", []) or []
        score = float(macro.get("score", 0) or 0)
        composite_phase = int(macro.get("composite_phase", 0) or 0)
    except Exception:
        pass

    tickers_today = sorted({d["ticker"] for d in dec_today})
    candidates = [
        "Concentration — grappe AI-compute",
        "Grille de Conviction",
        "World Model — le modèle causal (apex)",
    ]
    try:
        existing, _ = obs.filter_existing_links(candidates)
    except Exception as e:
        return f"filter_existing_links failed: {e}"

    fm = obs.frontmatter(
        type_="digest",
        date_iso=date_iso,
        aliases=[f"digest_bot_{date_iso}"],
        tickers=tickers_today,
        theses_touchees=[],
        noms_propres=[],
        hubs=existing,
        status="archive",
    )
    content = fm + (
        f"\n# Digest bot — {date_iso}\n\n"
        f"Mirror cron Mac periodic (auto-refresh 30min depuis script "
        f"`scripts/obsidian_periodic_mirror.py`).\n\n"
        f"## 📊 Métriques 24h\n\n"
        f"- **Signaux ingérés** : {n_24h_raw} raw, dont **{n_24h_scored['c']} scored** "
        f"(impact≥2.0) sur {n_24h_scored['src']} sources distinctes\n"
        f"- **Predictions résolues 24h** : {pred_resolved_24h}\n"
        f"- **Predictions dues prochains 7j** : {pred_due_7d}\n"
        f"- **Thèses actives** : {n_active}\n"
        f"- **Decisions journalées aujourd'hui** : {len(dec_today)}\n\n"
        f"## 🌐 Macro state\n\n"
        f"- **Régime** : `{regime}` (composite_phase {composite_phase}/4, score {score})\n"
        f"- **Triggers actifs** : {', '.join(triggers) if triggers else 'aucun'}\n\n"
        f"## 📰 Top 10 signaux scorés (24h, impact≥2.0)\n\n"
    )
    for s in top_signals:
        ts = (s["timestamp"] or "?")[:16]
        src = s["source"] or "?"
        title = (s["title"] or "?")[:100]
        impact = s["impact_magnitude"] or 0
        content += f"- **[{src}]** ({ts}, impact={impact:.1f}) {title}\n"
    content += "\n## ⚖️ Decisions journalées aujourd'hui\n\n"
    if dec_today:
        for d in dec_today:
            content += (
                f"- decision#{d['id']} {d['ticker']} **{d['decision_type']}** "
                f"(conv={d['confidence_pre']}) — {d['r']}...\n"
            )
    else:
        content += "  (aucune decision aujourd'hui)\n"
    content += (
        "\n## 🔗 Rattachements\n\n"
        + ", ".join(f"[[{h}]]" for h in existing)
        + "\n\n## [À COMPLÉTER PAR O.] — distillation\n\n"
        "Patterns à graver ? Signaux à promouvoir en thèse ? : —\n"
    )

    try:
        obs.write_note(f"journal/digests/DIGEST_{date_iso}.md", content, overwrite=True)
        return None
    except Exception as e:
        return f"write_note DIGEST failed: {e}"


# Mapping explicite ticker -> note vault canonical.
# Important : SI un ticker a une note "TICKER.md" stub vide ET une note longue
# "TICKER — description.md" (cas Olivier vault), il FAUT mapping override
# pour ne PAS appender sur le stub. Audit 25/06 a revele 5 stubs auto-match
# en erreur (AVGO/KLAC/GOOGL/LNG/MU).
# A jour 25/06/2026 — etendre si nouvelle note vault avec nom non-standard.
TICKER_TO_VAULT_NOTE = {
    "ASML.AS": "ASML.md",
    "TSM": "TSMC.md",
    "SNPS": "SYNOPSYS.md",
    "MU": "MICRON.md",  # MU.md = stub vide
    "AVGO": "BROADCOM - AVGO.md",  # AVGO.md = stub vide
    "KLAC": "KLA CORPORATION.md",  # KLAC.md = stub vide
    "GOOGL": "GOOGL — hyperscaler côté demande, le client-chokepoint.md",  # GOOGL.md = stub vide
    "LNG": "LNG — export GNL, le décorrélateur authentique.md",  # LNG.md = stub vide
    "SAF.PA": "SAF — aéro civil, ballast à rente d'après-vente (hors-IA).md",
    "HO.PA": "HO — défense, le ballast authentique (réarmement, hors-IA).md",
    "SU.PA": "SU — électrification, le faux décorrélateur (AI-capex déguisé).md",
    "STMPA.PA": "STM — généraliste cyclique, le miroir négatif (PAS un chokepoint).md",
    "BESI.AS": "BESI — chokepoint en formation, le pari hybrid bonding.md",
    "000660.KS": "SK Hynix.md",
    "4063.T": "SHIN-ETSU.md",
    "6857.T": "6857 (Advantest) — duopole du test, le 3e goulot WFE.md",
    "6920.T": "6920 (Lasertec) — monopole fragile de l'inspection EUV.md",
    "7011.T": "7011 (Mitsubishi Heavy) — conglomérat hybride, à cheval grappe ballast.md",
    # 6324.T (HARMONIC DRIVE) : no vault note yet, will skip
    # GEV, MP, CCJ, COHR, ENTG, ALAB, AMZN, SPCX : auto-match OK (pas de doublon stub)
}

# Stubs vides connus a IGNORER absolument (jamais appender sur eux meme
# si l'auto-match les attrape). Defense in depth contre regression mapping.
KNOWN_EMPTY_STUBS_TO_SKIP = {
    "AVGO.md", "KLAC.md", "GOOGL.md", "LNG.md", "MU.md",
    "Snapshot patrimoine.md",  # canonical sans date = stub Olivier
}


def mirror_chiffres_position() -> tuple[int, int]:
    """Append section "Chiffres position (FAIT — date)" sur notes ticker.md pour
    held positions. Idempotent : si meme date deja appended, skip.

    Mapping ticker -> note vault : TICKER_TO_VAULT_NOTE override prioritaire,
    sinon auto-match (TICKER.md exact -> TICKER prefix).
    Returns (n_updated, n_skipped).
    """
    try:
        from shared import obsidian as obs
        from shared.position_view import get_all_positions_views
    except Exception as e:
        print(f"  FAIT skip (import err): {e}", file=sys.stderr)
        return 0, 0

    date_iso = _now_iso()
    views = get_all_positions_views()
    n_updated = n_skipped = 0

    # Cache des notes vault root pour matching
    try:
        root_entries = obs.list_notes()
    except Exception as e:
        print(f"  FAIT skip (list_notes err): {e}", file=sys.stderr)
        return 0, 0

    cx = sqlite3.connect(REPO / "data" / "bot.db")
    cx.row_factory = sqlite3.Row

    # Pour chaque held position, trouver la note correspondante + append FAIT si pas encore
    for tk, v in views.items():
        if not v or not v.price_native:
            continue
        # Identifier la note canonical via mapping ou auto-match
        note_path = None
        # Match 0 : override mapping explicite
        if tk in TICKER_TO_VAULT_NOTE:
            override = TICKER_TO_VAULT_NOTE[tk]
            if override in root_entries:
                note_path = override
        # Match 1 : exact "TICKER.md"
        if not note_path:
            for entry in root_entries:
                if entry == f"{tk}.md":
                    note_path = entry
                    break
        # Match 2 : "TICKER — description.md" ou "TICKER ..md" (preserver tirets)
        if not note_path:
            for entry in root_entries:
                stripped = entry.replace(".md", "")
                if stripped.lower().startswith(tk.lower() + " ") or stripped.lower().startswith(tk.lower() + "—"):
                    note_path = entry
                    break
        if not note_path:
            n_skipped += 1
            continue

        # Defense in depth : skip stubs vides connus (regression mapping override)
        if note_path in KNOWN_EMPTY_STUBS_TO_SKIP:
            n_skipped += 1
            continue

        # Check si section deja appended pour cette date
        try:
            existing_content = obs.read_note(note_path)
            marker = f"## Chiffres position (FAIT — {date_iso})"
            if marker in existing_content:
                n_skipped += 1
                continue
        except Exception:
            n_skipped += 1
            continue

        # Get thesis data
        th = cx.execute(
            "SELECT entry_price, target_partial, target_full, stop_price, conviction, position_type "
            "FROM theses WHERE ticker=? AND status='active'",
            (tk,),
        ).fetchone()
        if not th:
            n_skipped += 1
            continue

        pos = cx.execute("SELECT qty FROM positions WHERE ticker=?", (tk,)).fetchone()
        qty = pos[0] if pos else 0
        if qty <= 0:
            n_skipped += 1
            continue

        cur_native = v.price_native
        value_eur = None
        with contextlib.suppress(Exception):
            value_eur = float(v.value_eur_datum.value.amount) if v.value_eur_datum else None

        dist_full = (cur_native / th["target_full"] - 1) * 100 if th["target_full"] else None
        dist_partial = (cur_native / th["target_partial"] - 1) * 100 if th["target_partial"] else None
        margin_stop = (th["stop_price"] / cur_native - 1) * 100 if th["stop_price"] else None

        section = (
            f"\n## Chiffres position (FAIT — {date_iso})\n\n"
            f"> Source : DB transactions append-only + book.value_eur Datum canonique + "
            f"yfinance live. Auto-refresh via `scripts/obsidian_periodic_mirror.py`.\n\n"
            f"- Position : **{qty:.4f} sh** détenues\n"
            f"- Cours actuel : **{cur_native:.2f}** (price_native live)\n"
        )
        if value_eur is not None:
            section += f"- Valeur position EUR : **€{value_eur:.0f}**\n"
        if th["entry_price"]:
            section += f"- Entry (thèse) : {th['entry_price']:.2f}\n"
        if dist_partial is not None:
            section += f"- Partial : {th['target_partial']:.2f} (distance current : {dist_partial:+.1f}%)\n"
        if dist_full is not None:
            section += f"- Full : {th['target_full']:.2f} (distance current : {dist_full:+.1f}%)\n"
        if margin_stop is not None:
            section += f"- Stop : {th['stop_price']:.2f} (margin sous current : {margin_stop:.1f}%)\n"
        section += f"- Conviction DB : c{th['conviction']} ({th['position_type']})\n"
        if v.pnl_position_pct is not None:
            section += f"- PnL position EUR : **{v.pnl_position_pct:+.2f}%** (vs cost basis PMP rolling)\n"
        section += "\n(Append automatique FAIT. JUGEMENT inchangé.)\n"

        try:
            obs.append_to_note(note_path, section)
            n_updated += 1
        except Exception as e:
            print(f"  FAIT {tk} -> {note_path} append failed: {e}", file=sys.stderr)
            n_skipped += 1

    cx.close()
    return n_updated, n_skipped


def mirror_transactions(cx: sqlite3.Connection) -> tuple[int, str | None]:
    """Mirror les transactions des 30 derniers jours, groupees par date.

    Crée 1 fichier par jour avec tx : journal/transactions/TX_<date>.md.
    Overwrite idempotent (chaque run regenere le fichier du jour).

    Returns (n_days_written, err_msg_or_None).
    """
    try:
        from shared import obsidian as obs
    except Exception as e:
        return (0, f"obsidian import: {e}")

    cx.row_factory = sqlite3.Row
    txs_all = cx.execute(
        "SELECT id, ticker, side, qty, price_native, currency, fx_at_trade, "
        "trade_date, source, notes "
        "FROM transactions "
        "WHERE trade_date >= datetime('now', '-30 days') "
        "  AND source NOT LIKE 'smoke_test%' "
        "  AND ticker NOT LIKE 'SMOKE%' "
        "  AND ticker NOT LIKE 'SMK%' "
        "ORDER BY trade_date, id"
    ).fetchall()

    # Group by date
    by_date: dict[str, list] = {}
    for tx in txs_all:
        d_iso = (tx["trade_date"] or "")[:10]
        if d_iso:
            by_date.setdefault(d_iso, []).append(tx)

    if not by_date:
        return (0, None)

    # Cache root entries for ticker → note resolution
    try:
        all_root = obs.list_notes()
    except Exception:
        all_root = []

    def resolve_ticker_note(tk: str) -> str:
        override = TICKER_TO_VAULT_NOTE.get(tk)
        if override and override in all_root:
            return override.replace(".md", "")
        for e in all_root:
            if e == f"{tk}.md" or e.replace(".md", "").startswith(tk + " "):
                return e.replace(".md", "")
        return tk

    candidates = ["Concentration — grappe AI-compute", "Grille de Conviction"]
    try:
        hubs, _ = obs.filter_existing_links(candidates)
    except Exception:
        hubs = []

    n_written = 0
    for d_iso, txs in by_date.items():
        tickers_day = sorted({t["ticker"] for t in txs})
        ticker_to_note = {tk: resolve_ticker_note(tk) for tk in tickers_day}

        fm = obs.frontmatter(
            type_="transactions-log",
            date_iso=d_iso,
            aliases=[f"transactions_{d_iso}"],
            tickers=tickers_day,
            theses_touchees=list(set(ticker_to_note.values())),
            noms_propres=[],
            hubs=hubs,
            status="archive",
        )

        content = fm + (
            f"\n# Transactions — {d_iso}\n\n"
            f"Mirror auto via `scripts/obsidian_periodic_mirror.py`. "
            f"{len(txs)} transaction(s) ce jour.\n\n"
        )
        for tx in txs:
            ticker = tx["ticker"]
            thesis_link = f"[[{ticker_to_note[ticker]}]]"
            eur_value = float(tx["qty"]) * float(tx["price_native"]) * float(tx["fx_at_trade"])
            notes_excerpt = (tx["notes"] or "")[:150]
            content += (
                f"## tx#{tx['id']} — {ticker} {tx['side']}\n\n"
                f"- **Ticker** : {thesis_link}\n"
                f"- **Side** : {tx['side']}\n"
                f"- **Quantité** : {tx['qty']:.6f} sh\n"
                f"- **Prix natif** : {tx['price_native']:.2f} {tx['currency']} "
                f"(fx {tx['fx_at_trade']:.4f} → ~€{eur_value:.0f})\n"
                f"- **Date** : {tx['trade_date'][:19]}\n"
                f"- **Source** : `{tx['source']}`\n"
                f"- **Notes** : {notes_excerpt}\n\n"
            )

        content += (
            "## 🔗 Rattachements\n\n"
            + ", ".join(f"[[{h}]]" for h in hubs)
            + "\n\n## [À COMPLÉTER PAR O.] — distillation\n\n"
            "Pattern observé ? Cohérence avec la doctrine ? : —\n"
        )

        try:
            obs.write_note(f"journal/transactions/TX_{d_iso}.md", content, overwrite=True)
            n_written += 1
        except Exception as e:
            return (n_written, f"write tx {d_iso}: {e}")

    return (n_written, None)


def mirror_decisions(cx: sqlite3.Connection) -> tuple[int, int]:
    """Mirror chaque decision dans journal/decisions/DECISION_<id>_<ticker>.md.

    Idempotent par decision_id. Chaque decision = 1 note avec :
      - frontmatter avec bias_tags + thesis_id + decision_type
      - reasoning [STRUCTURED] parsé (these / invalidation / conviction)
      - lien vers note thèse + bias hub + counterfactual si présent
    Returns (n_created, n_skipped).
    """
    try:
        from shared import obsidian as obs
    except Exception:
        return (0, 0)

    cx.row_factory = sqlite3.Row
    # Decisions créées dans les derniers 30 jours (limite raisonnable)
    decs = cx.execute(
        "SELECT id, ticker, decision_type, created_at, confidence_pre, reasoning, "
        "thesis_id, bias_tags, price_at_decision "
        "FROM decisions "
        "WHERE created_at >= datetime('now', '-30 days') "
        "ORDER BY id"
    ).fetchall()

    try:
        all_root = obs.list_notes()
    except Exception:
        all_root = []

    n_created = n_skipped = 0
    for d in decs:
        ticker = d["ticker"]
        # Path canonical
        date_iso = (d["created_at"] or "")[:10]
        note_path = f"journal/decisions/DECISION_{d['id']:03d}_{ticker}_{date_iso}.md"
        if obs.note_exists(note_path):
            n_skipped += 1
            continue

        # Find thesis note link
        thesis_note_link = ticker
        override = TICKER_TO_VAULT_NOTE.get(ticker)
        if override and override in all_root:
            thesis_note_link = f"[[{override.replace('.md', '')}]]"
        else:
            for e in all_root:
                if e == f"{ticker}.md" or e.replace(".md", "").startswith(ticker + " "):
                    thesis_note_link = f"[[{e.replace('.md', '')}]]"
                    break

        # Parse [STRUCTURED] reasoning
        reasoning = d["reasoning"] or ""
        is_structured = reasoning.startswith("[STRUCTURED]")
        is_quick = reasoning.startswith("[QUICK_UNJOURNALED]")

        # Bias tags
        bias_tags = []
        if d["bias_tags"]:
            try:
                import json as _json
                bias_tags = _json.loads(d["bias_tags"])
            except Exception:
                bias_tags = []

        candidates = ["Biais", "Grille de Conviction", "Concentration — grappe AI-compute"]
        try:
            hubs, _ = obs.filter_existing_links(candidates)
        except Exception:
            hubs = []

        fm = obs.frontmatter(
            type_="decision",
            date_iso=date_iso,
            aliases=[f"decision_{d['id']}_{ticker}"],
            tickers=[ticker],
            theses_touchees=[],
            noms_propres=[],
            hubs=hubs,
            status="archive",
        )

        struct_indicator = "✅ STRUCTURED" if is_structured else ("⚠️ QUICK_UNJOURNALED" if is_quick else "⚠️ legacy/incomplete")

        content = fm + (
            f"\n# Decision #{d['id']} — {ticker} {d['decision_type']}\n\n"
            f"- **Date** : {d['created_at']}\n"
            f"- **Ticker** : {thesis_note_link}\n"
            f"- **Type** : `{d['decision_type']}`\n"
            f"- **Conviction (pre-decision)** : c{d['confidence_pre']}\n"
            f"- **Prix at decision** : {d['price_at_decision']}\n"
            f"- **Format reasoning** : {struct_indicator}\n"
            f"- **Thesis ID DB** : {d['thesis_id']}\n\n"
            "## 🧠 Reasoning structuré\n\n"
            f"```\n{reasoning}\n```\n\n"
        )

        if bias_tags:
            content += "## 🎭 Bias tags (auto-detected via bias_tagger LLM)\n\n"
            for tag in bias_tags:
                content += f"- `{tag}`\n"
            content += "\nCf [[Biais]] pour la doctrine de mitigation.\n\n"

        content += (
            "## 🔗 Rattachements\n\n"
            + ", ".join(f"[[{h}]]" for h in hubs)
            + "\n\n## [À COMPLÉTER PAR O.] — distillation\n\n"
            "Decision rétro : ai-je bien fait ? Quel biais à monitorer next ? : —\n"
        )

        try:
            obs.write_note(note_path, content)
            n_created += 1
        except Exception:
            n_skipped += 1
    return (n_created, n_skipped)


def mirror_snapshot_patrimoine() -> str | None:
    """Cree Snapshot patrimoine — <date>.md si pas deja existant aujourd'hui.

    Idempotent : un seul snapshot par jour, le premier wins.
    """
    try:
        from shared import obsidian as obs
        from shared.position_view import get_all_positions_views
    except Exception as e:
        return f"snapshot skip (import err): {e}"

    date_iso = _now_iso()
    note_path = f"Snapshot patrimoine — {date_iso}.md"

    try:
        if obs.note_exists(note_path):
            return None  # idempotent : already exists
    except Exception as e:
        return f"snapshot note_exists err: {e}"

    views = get_all_positions_views()
    total = 0.0
    n_held = 0
    for v in views.values():
        if v and v.value_eur_datum:
            try:
                total += float(v.value_eur_datum.value.amount)
                n_held += 1
            except Exception:
                pass

    cx = sqlite3.connect(REPO / "data" / "bot.db")
    n_active = cx.execute("SELECT COUNT(*) FROM theses WHERE status='active'").fetchone()[0]
    conv_dist = cx.execute(
        "SELECT conviction, COUNT(*) FROM theses WHERE status='active' GROUP BY conviction ORDER BY conviction DESC"
    ).fetchall()
    cx.close()

    candidates = ["Concentration — grappe AI-compute", "Grille de Conviction"]
    try:
        existing, _ = obs.filter_existing_links(candidates)
    except Exception:
        existing = []

    fm = obs.frontmatter(
        type_="snapshot-patrimoine",
        date_iso=date_iso,
        aliases=[f"snapshot_{date_iso}"],
        tickers=[],
        theses_touchees=[],
        noms_propres=[],
        hubs=existing,
        status="archive",
    )
    content = fm + (
        f"\n# Snapshot patrimoine — {date_iso}\n\n"
        f"Snapshot auto-genere par `scripts/obsidian_periodic_mirror.py` "
        f"(idempotent, premier du jour wins).\n\n"
        f"## 📊 Book\n\n"
        f"- **Book value total EUR** : **€{total:.0f}**\n"
        f"- **Positions held** : {n_held}\n"
        f"- **Thèses actives** : {n_active}\n\n"
        f"## ⚖️ Distribution par conviction\n\n"
    )
    for r in conv_dist:
        content += f"- c{r[0]} : {r[1]} thèses\n"
    content += (
        "\n## 🔗 Rattachements\n\n"
        + (", ".join(f"[[{h}]]" for h in existing) if existing else "  (aucun hub)")
        + "\n\n## [À COMPLÉTER PAR O.] — distillation\n\n"
        "Évolution depuis le snapshot précédent ? : —\n"
    )

    try:
        obs.write_note(note_path, content, overwrite=False)
        return None
    except Exception as e:
        return f"snapshot write failed: {e}"


def main() -> int:
    print(f"[obsidian_periodic_mirror] start {datetime.now().isoformat()}")

    # Check Obsidian reachable
    try:
        from shared import obsidian as obs
        obs.list_notes()
    except Exception as e:
        print(f"  Obsidian unreachable, abort: {e}", file=sys.stderr)
        return 1

    # 1. DIGEST
    cx = sqlite3.connect(REPO / "data" / "bot.db")
    err_digest = mirror_digest(cx)
    if err_digest:
        print(f"  DIGEST : FAIL {err_digest}", file=sys.stderr)
    else:
        print(f"  DIGEST : OK (DIGEST_{_now_iso()}.md updated)")

    # 2. FAIT chiffres position
    try:
        n_up, n_skip = mirror_chiffres_position()
        print(f"  FAIT : {n_up} notes updated, {n_skip} skipped (already updated today or no thesis)")
    except Exception as e:
        print(f"  FAIT : FAIL {e}", file=sys.stderr)

    # 3. SNAPSHOT
    err_snap = mirror_snapshot_patrimoine()
    if err_snap:
        print(f"  SNAPSHOT : {err_snap}", file=sys.stderr)
    else:
        print("  SNAPSHOT : OK (created or already exists today)")

    # 4. TRANSACTIONS 30j (groupees par date)
    n_tx_days, err_tx = mirror_transactions(cx)
    if err_tx:
        print(f"  TRANSACTIONS : FAIL {err_tx}", file=sys.stderr)
    else:
        print(f"  TRANSACTIONS : OK ({n_tx_days} days mirrored)")

    # 5. DECISIONS (30j window, idempotent par id)
    try:
        n_dec_new, n_dec_skip = mirror_decisions(cx)
        print(f"  DECISIONS : {n_dec_new} créées, {n_dec_skip} déjà mirrorées")
    except Exception as e:
        print(f"  DECISIONS : FAIL {e}", file=sys.stderr)
    cx.close()

    # NOTE 25/06 : RETIRE app:reload. Constate qu'il casse le plugin Local REST API
    # post-execution (le plugin ne se re-init pas correctement). Obsidian file watcher
    # detecte les changes file system de facon native, donc UI rafraichit toute seule
    # sans avoir besoin de reload programmatique.

    print(f"[obsidian_periodic_mirror] done {datetime.now().isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
