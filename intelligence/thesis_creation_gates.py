"""Gates de creation thèse — Mentor heuristiques mecanisées (M-B pillar).

Encodage des principes mentors battle-tested en gates deterministes (cf
docs/LESSONS.md L14 anti-pattern #1 : on NE clone PAS de personas LLM qui
debattent ; on encode la regle directement).

Gates implementes (Phase post-J-day, doctrine "mesure-passe pas predit-futur") :

- **M1 Buffett/Munger quality** : conviction >= 4 EXIGE solidité ∈
  {Incontournable, Solide}. Catch : "tu te survends sur du Fragile".
  Source solidité : canonical_perimeter.json (user-tagged).
  Si ticker hors canonical -> warning only (pas hard block, on n'a pas de signal).

- **M2 Taleb/Pabrai asymmetry** : conviction >= 4 EXIGE
  asymmetry_ratio = (target_full - entry) / (entry - stop_price) >= 2.0
  pour long, et la symetrique pour short. Catch : "convaincu mais
  upside ridicule vs downside accepte".
  Necessite stop_price + target_full. Si manquant -> warning only
  (pas de stop = autre invariant pris ailleurs, cf shared/thesis_invariants).

Style :
- Validators retournent (passed: bool, message: str). Pas d'exception (le
  caller `intelligence.thesis.add_thesis` decide bloquant ou warning).
- Strict mode = parametre `strict_creation=True` qui transforme en
  exception ; defaut = warning seulement (preserve compat retro).
- Pas de LLM call, pas de DB write -- pure logique deterministe.

Tests :
- M1 : conviction 4 + solidité Solide -> pass
- M1 : conviction 5 + solidité Fragile -> fail
- M1 : conviction 3 + solidité Fragile -> pass (gate ne fire que conviction>=4)
- M2 : conviction 4 long upside=15 downside=5 -> pass (ratio=3)
- M2 : conviction 4 long upside=8 downside=5 -> fail (ratio=1.6)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


# === Constantes encodees ===================================================

SOLIDITE_ACCEPTABLE_HIGH_CONVICTION = {"Incontournable", "Solide"}
CONVICTION_HIGH_THRESHOLD = 4
ASYMMETRY_MIN_RATIO = 2.0

# M11 Ackman concentration check : a conviction 5, on attend la position dans
# le top-5 par poids du book. En dessous = sous-dimensionnement vs conviction
# affichee (Ackman pattern : si tu CROIS, joue gros ; sinon baisse conviction).
ACKMAN_MAX_RANK = 5
ACKMAN_CONVICTION_THRESHOLD = 5

# M5 Lynch clarity : conviction 5 attend une these formulable en 1 phrase.
# Patterns acceptes (case-insensitive) qui marquent une these structuree.
LYNCH_CONVICTION_THRESHOLD = 5
LYNCH_CLARITY_PATTERNS = (
    "because", "parce que", "ten_x_path", "tenx", "10x_path",
    "ten-x", "->", "→", "drives", "driver:",
)

# M9 Damodaran story->numbers : conviction >=4 attend au moins 1 driver avec
# une metric quanti chiffree (sinon = narrative pur, pas falsifiable).
DAMODARAN_CONVICTION_THRESHOLD = 4
# Regex compiles au load (lazy via _DAMODARAN_RE)
_DAMODARAN_PATTERNS = (
    r"\d+\s*%",            # 30%
    r"\$\s*\d+",           # $15B, $50
    r"€\s*\d+|\d+\s*€",    # 5000€
    r"\d+\s*x\b",          # 10x
    r"\bP/E\s*\d+",        # P/E 25
    r"\bROIC\s*\d+",       # ROIC 18
    r"\bEPS\s*\d+",        # EPS 2.5
    r"\d+\s*[BMK]\b",      # 50B, 200M, 100K
    r"\d+\s*bps\b",        # 350 bps
    r"\bCAGR\s*\d+",       # CAGR 25
)
_DAMODARAN_RE = None  # lazy init

# M12 Pabrai downside floor : conviction 4 attend une mention explicite du
# downside chiffre dans notes (Pabrai Dhandho : "heads I win, tails I don't
# lose much" -- "much" doit etre quantifie).
PABRAI_CONVICTION_THRESHOLD = 4
_PABRAI_PATTERNS = (
    r"downside\s*[:=]\s*[-\$€\d]",      # "downside: 5000€" / "downside = -20%"
    r"max[_ ]loss\s*[:=]\s*[-\$€\d]",   # "max_loss: 3000"
    r"worst[_ ]case\s*[:=]\s*[-\$€\d]", # "worst_case: -25%"
    r"floor\s*[:=]\s*[-\$€\d]",         # "floor: 5000€"
    r"perte\s*max\s*[:=]\s*[-\$€\d]",   # "perte max: ..."
)
_PABRAI_RE = None  # lazy init


@dataclass(frozen=True, slots=True)
class GateResult:
    """Resultat d'un check de gate. passed=True quand satisfait."""
    gate_name: str
    passed: bool
    message: str


# === M1 Buffett/Munger quality =============================================


def check_m1_buffett_quality(
    ticker: str,
    conviction: int,
    solidite: str | None,
) -> GateResult:
    """Conviction >= 4 exige solidité ∈ {Incontournable, Solide}.

    Args:
        ticker : pour le message uniquement.
        conviction : 1-5.
        solidite : "Incontournable" / "Solide" / "Incertain" / "Fragile" / None.

    Returns:
        GateResult. passed=False si conviction >=4 ET solidité tagged comme
        Incertain ou Fragile. Si solidité None (hors canonical_perimeter),
        passed=True avec message warning (on ne bloque pas sur absence).
    """
    if conviction < CONVICTION_HIGH_THRESHOLD:
        return GateResult(
            gate_name="M1_buffett_quality",
            passed=True,
            message=f"conviction {conviction} < {CONVICTION_HIGH_THRESHOLD} -- gate ne fire pas",
        )
    if solidite is None:
        return GateResult(
            gate_name="M1_buffett_quality",
            passed=True,
            message=(
                f"warning : {ticker} pas dans canonical_perimeter.json -- "
                "solidité inconnue, ne peut pas verifier M1 Buffett quality"
            ),
        )
    if solidite in SOLIDITE_ACCEPTABLE_HIGH_CONVICTION:
        return GateResult(
            gate_name="M1_buffett_quality",
            passed=True,
            message=f"solidité {solidite!r} compatible conviction {conviction}",
        )
    return GateResult(
        gate_name="M1_buffett_quality",
        passed=False,
        message=(
            f"M1 Buffett FAIL : {ticker} conviction {conviction} demande solidité "
            f"∈ {sorted(SOLIDITE_ACCEPTABLE_HIGH_CONVICTION)} mais ticker tagué "
            f"{solidite!r}. Soit baisse conviction ≤ 3, soit re-tag canonical "
            "(rare, justifie). Catch Buffett : 'on ne paye pas pour low-quality '"
            "'with high conviction'."
        ),
    )


# === M2 Taleb/Pabrai asymmetry =============================================


def _compute_asymmetry_ratio(
    direction: str,
    entry: float | None,
    target_full: float | None,
    stop_price: float | None,
) -> float | None:
    """Calcule (upside/downside) ratio. Devises ASSUMEES natives consistantes
    (gate cf shared/thesis_invariants verifie ca separement). None si
    impossible (manque entry / target / stop).
    """
    if entry is None or target_full is None or stop_price is None:
        return None
    if entry <= 0:
        return None
    if direction == "long":
        upside = target_full - entry
        downside = entry - stop_price
    elif direction == "short":
        upside = entry - target_full
        downside = stop_price - entry
    else:
        return None
    if downside <= 0:
        return None  # symmetric : downside doit etre positif (stop sous entry pour long)
    if upside <= 0:
        return None  # target dans le mauvais sens
    return upside / downside


def check_m2_taleb_asymmetry(
    ticker: str,
    conviction: int,
    direction: str,
    entry: float | None,
    target_full: float | None,
    stop_price: float | None,
) -> GateResult:
    """Conviction >= 4 exige asymmetry_ratio >= 2.0 (upside vs downside).

    Args:
        ticker : pour message.
        conviction : 1-5.
        direction : 'long' / 'short' / 'watch'. 'watch' -> gate ne fire pas.
        entry / target_full / stop_price : meme devise native, deja valides
          par shared/thesis_invariants upstream.

    Returns:
        GateResult. passed=False si conviction >=4 ET asymmetry_ratio < 2.0
        et calculable. Si manque entry/target/stop -> passed=True avec warning
        (un autre invariant signalera l'absence de stop).
    """
    if conviction < CONVICTION_HIGH_THRESHOLD:
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message=f"conviction {conviction} < {CONVICTION_HIGH_THRESHOLD} -- gate ne fire pas",
        )
    if direction == "watch":
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message="direction=watch -- asymmetry non applicable",
        )
    ratio = _compute_asymmetry_ratio(direction, entry, target_full, stop_price)
    if ratio is None:
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message=(
                "warning : asymmetry_ratio non calculable (entry/target/stop "
                "manquants ou incoherents)"
            ),
        )
    if ratio >= ASYMMETRY_MIN_RATIO:
        return GateResult(
            gate_name="M2_taleb_asymmetry",
            passed=True,
            message=f"asymmetry_ratio={ratio:.2f} >= {ASYMMETRY_MIN_RATIO} (Taleb compat)",
        )
    return GateResult(
        gate_name="M2_taleb_asymmetry",
        passed=False,
        message=(
            f"M2 Taleb FAIL : {ticker} conviction {conviction} demande "
            f"asymmetry_ratio >= {ASYMMETRY_MIN_RATIO} mais calcul donne "
            f"{ratio:.2f}. (upside {direction}={target_full}-{entry} vs "
            f"downside {entry}-{stop_price}). Catch Taleb : 'high conviction "
            "+ low asymmetry = sous-paye par le risque'."
        ),
    )


# === M11 Ackman concentration check ========================================


def check_m11_ackman_concentration(
    ticker: str,
    conviction: int,
    book_ranks: dict[str, int] | None = None,
) -> GateResult:
    """Conviction 5 EXIGE position dans le top-5 par poids du book.

    Logique Ackman : si tu te dis ULTRA-convaincu (conviction max), tu joues
    gros. Si tu joues petit malgre conviction max, c'est qu'au fond tu n'es
    pas si convaincu, ou que la sizing trahit la conviction affichee.

    Args:
        ticker : pour le message + lookup dans book_ranks.
        conviction : 1-5.
        book_ranks : dict {ticker: rank_by_weight} ou None. Si None,
          le helper essaie de fetch via shared.book (peut crash en test).
          Rank 1 = plus gros poids du book.

    Returns:
        GateResult. Gate fire seulement si conviction == 5 ET ticker present
        en book ET rank > 5. Si ticker absent du book (these en cours de
        creation = pas encore en DB), passed=True avec note neutre."""
    if conviction < ACKMAN_CONVICTION_THRESHOLD:
        return GateResult(
            gate_name="M11_ackman_concentration",
            passed=True,
            message=(
                f"conviction {conviction} < {ACKMAN_CONVICTION_THRESHOLD} -- "
                "gate ne fire pas"
            ),
        )
    if book_ranks is None:
        try:
            book_ranks = _fetch_book_ranks_by_weight()
        except Exception as e:
            return GateResult(
                gate_name="M11_ackman_concentration",
                passed=True,
                message=f"warning : book_ranks indisponible ({type(e).__name__}: {e})",
            )
    rank = book_ranks.get(ticker)
    if rank is None:
        return GateResult(
            gate_name="M11_ackman_concentration",
            passed=True,
            message=(
                f"warning : {ticker} pas (encore) en DB book -- "
                "M11 ne peut pas verifier rang"
            ),
        )
    if rank <= ACKMAN_MAX_RANK:
        return GateResult(
            gate_name="M11_ackman_concentration",
            passed=True,
            message=(
                f"{ticker} rang #{rank} dans top-{ACKMAN_MAX_RANK} "
                "(conviction 5 coherent avec sizing)"
            ),
        )
    return GateResult(
        gate_name="M11_ackman_concentration",
        passed=False,
        message=(
            f"M11 Ackman FAIL : {ticker} conviction 5 mais rang #{rank} "
            f"par poids (top-{ACKMAN_MAX_RANK} attendu). Catch Ackman : "
            "'si t'es vraiment convaincu max, joue gros; sizing petit + "
            "conviction max = incoherence ou conviction surevaluee'."
        ),
    )


def _fetch_book_ranks_by_weight() -> dict[str, int]:
    """Helper : rang par market value (weight_market_eur) des positions
    ouvertes via shared.book. Rang 1 = plus gros poids."""
    from shared.book import get_canonical_book
    book = get_canonical_book(with_prices=True)
    # Filter positions open + weight_market > 0
    active = [bl for bl in book if bl.in_db and bl.weight_market_eur > 0]
    active.sort(key=lambda bl: bl.weight_market_eur, reverse=True)
    return {bl.ticker: i + 1 for i, bl in enumerate(active)}


# === M5 Lynch thesis clarity ===============================================


def check_m5_lynch_clarity(
    ticker: str,
    conviction: int,
    key_drivers: list[str] | None,
    notes: str | None = None,
) -> GateResult:
    """Conviction 5 EXIGE these formulable en 1 phrase claire.

    Lynch catch : "si tu sais pas dire pourquoi en 1 phrase, t'as pas de
    these". On accepte les patterns : 'because', 'parce que', 'ten_x_path',
    '->', 'drives', 'driver:', etc. case-insensitive.

    Args:
        ticker, conviction
        key_drivers : list de drivers structures
        notes : free text complementaire

    Returns:
        Pass si conviction < 5 OU au moins 1 driver/notes contient pattern
        clarity. FAIL sinon.
    """
    if conviction < LYNCH_CONVICTION_THRESHOLD:
        return GateResult(
            gate_name="M5_lynch_clarity",
            passed=True,
            message=f"conviction {conviction} < {LYNCH_CONVICTION_THRESHOLD} -- gate ne fire pas",
        )
    corpus = " ".join(filter(None, (key_drivers or []))) + " " + (notes or "")
    corpus_lc = corpus.lower()
    matched = [p for p in LYNCH_CLARITY_PATTERNS if p.lower() in corpus_lc]
    if matched:
        return GateResult(
            gate_name="M5_lynch_clarity",
            passed=True,
            message=f"{ticker} clarity OK (patterns: {matched[:3]})",
        )
    return GateResult(
        gate_name="M5_lynch_clarity",
        passed=False,
        message=(
            f"M5 Lynch FAIL : {ticker} conviction 5 mais aucun pattern de "
            "clarte dans drivers/notes. Catch Lynch : 'tu sais pas dire en "
            "1 phrase pourquoi tu es a fond ? alors t'es pas a fond'. Ajoute "
            "clause 'because:' ou 'ten_x_path:' ou '->' dans tes drivers."
        ),
    )


# === M9 Damodaran story -> numbers =========================================


def _damodaran_re():
    global _DAMODARAN_RE
    if _DAMODARAN_RE is None:
        import re
        _DAMODARAN_RE = re.compile("|".join(_DAMODARAN_PATTERNS), re.IGNORECASE)
    return _DAMODARAN_RE


def check_m9_damodaran_quantitative(
    ticker: str,
    conviction: int,
    key_drivers: list[str] | None,
) -> GateResult:
    """Conviction >= 4 EXIGE au moins 1 driver avec metric chiffree.

    Damodaran : "story without numbers is fiction, numbers without story
    is accounting" -- on enforce le cote chiffre. Au moins 1 driver doit
    matcher une metric quanti (%, $, €, x, P/E N, EPS N, N B/M/K, bps, CAGR).

    Returns:
        Pass si conviction < 4 OU au moins 1 driver contient pattern numerique.
        FAIL sinon avec liste des drivers analyses.
    """
    if conviction < DAMODARAN_CONVICTION_THRESHOLD:
        return GateResult(
            gate_name="M9_damodaran_quantitative",
            passed=True,
            message=f"conviction {conviction} < {DAMODARAN_CONVICTION_THRESHOLD} -- gate ne fire pas",
        )
    drivers = key_drivers or []
    rx = _damodaran_re()
    matched_drivers = [d for d in drivers if rx.search(d)]
    if matched_drivers:
        return GateResult(
            gate_name="M9_damodaran_quantitative",
            passed=True,
            message=f"{ticker} {len(matched_drivers)} driver(s) chiffres trouves",
        )
    return GateResult(
        gate_name="M9_damodaran_quantitative",
        passed=False,
        message=(
            f"M9 Damodaran FAIL : {ticker} conviction {conviction} mais "
            "aucun driver ne contient de metric chiffree (regex %, $, €, x, "
            "P/E N, EPS N, N B/M/K, bps, CAGR N). Catch Damodaran : 'story "
            "without numbers is fiction'. Ajoute au moins 1 driver chiffre."
        ),
    )


# === M12 Pabrai Dhandho downside floor =====================================


def _pabrai_re():
    global _PABRAI_RE
    if _PABRAI_RE is None:
        import re
        _PABRAI_RE = re.compile("|".join(_PABRAI_PATTERNS), re.IGNORECASE)
    return _PABRAI_RE


def check_m12_pabrai_downside(
    ticker: str,
    conviction: int,
    notes: str | None,
) -> GateResult:
    """Conviction >= 4 EXIGE mention explicite du downside chiffre.

    Pabrai Dhandho : "heads I win, tails I don't lose much" -- "much" doit
    etre quantifie en EUR / USD / %. Pattern recherche dans notes :
    'downside: ...', 'max_loss: ...', 'worst_case: ...', 'floor: ...',
    'perte max: ...'.

    Returns:
        Pass si conviction < 4 OU pattern downside present.
        FAIL sinon.
    """
    if conviction < PABRAI_CONVICTION_THRESHOLD:
        return GateResult(
            gate_name="M12_pabrai_downside",
            passed=True,
            message=f"conviction {conviction} < {PABRAI_CONVICTION_THRESHOLD} -- gate ne fire pas",
        )
    if not notes:
        return GateResult(
            gate_name="M12_pabrai_downside",
            passed=False,
            message=(
                f"M12 Pabrai FAIL : {ticker} conviction {conviction} mais "
                "notes vide. Catch Pabrai : 'heads I win, tails I don't lose "
                "MUCH' -- much doit etre chiffre. Ajoute 'downside: X €' "
                "dans notes."
            ),
        )
    rx = _pabrai_re()
    if rx.search(notes):
        return GateResult(
            gate_name="M12_pabrai_downside",
            passed=True,
            message=f"{ticker} downside explicite dans notes",
        )
    return GateResult(
        gate_name="M12_pabrai_downside",
        passed=False,
        message=(
            f"M12 Pabrai FAIL : {ticker} conviction {conviction} mais notes "
            "ne mentionne pas de downside chiffre. Pattern attendu : "
            "'downside: X €' / 'max_loss: X' / 'worst_case: X%' / "
            "'floor: X'. Catch Pabrai Dhandho."
        ),
    )


# === Aggregator ============================================================


def run_creation_gates(
    ticker: str,
    direction: str,
    conviction: int,
    solidite: str | None = None,
    entry: float | None = None,
    target_full: float | None = None,
    stop_price: float | None = None,
    book_ranks: dict[str, int] | None = None,
    key_drivers: list[str] | None = None,
    notes: str | None = None,
) -> list[GateResult]:
    """Lance tous les gates de creation thèse.

    Returns liste de GateResult. Caller decide bloquant ou warning.
    """
    return [
        check_m1_buffett_quality(ticker, conviction, solidite),
        check_m2_taleb_asymmetry(
            ticker, conviction, direction, entry, target_full, stop_price
        ),
        check_m5_lynch_clarity(ticker, conviction, key_drivers, notes),
        check_m9_damodaran_quantitative(ticker, conviction, key_drivers),
        check_m11_ackman_concentration(ticker, conviction, book_ranks),
        check_m12_pabrai_downside(ticker, conviction, notes),
    ]


def fetch_solidite_for_ticker(ticker: str) -> str | None:
    """Helper : lookup solidité dans canonical_perimeter.json via shared.book.
    Returns None si ticker hors perimeter (signal pour M1 warning-only)."""
    try:
        from shared.book import _load_canonical
        canonical = _load_canonical()
        for pos in canonical.get("positions") or []:
            if pos.get("ticker") == ticker:
                return pos.get("solidite")
    except Exception as e:
        log.warning(f"fetch_solidite_for_ticker {ticker} failed: {e}")
    return None
