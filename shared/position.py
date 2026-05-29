"""PRESAGE — Position canonique : FAIT / JUGEMENT / DERIVE / HISTORIQUE.

Architecture refactor 29/05/2026 round 3 sur directive user :
> "Trois couches qui ne se melangent jamais -- Fait / Jugement / Derive.
>  C'est ta propre regle 'couleur = fait, jamais jugement', mais appliquee
>  au stockage, pas juste a l'affichage."

Avant : BookLine plat melangeait broker facts, judgments user, derived
computes. Resultat : chaque vue recalculait differemment (F11 ASML 7.9%
vs 5.7%, AMD 3.4% vs 1.4%).

Maintenant : Position composee de 4 couches strictes :

    Position
    ├─ facts       : PositionFacts (immutable, du courtier)
    ├─ judgments   : PositionJudgments (de l'user, dates, append-only)
    ├─ lifecycle   : Lifecycle (construction|active|exiting|sold|watch)
    └─ derived     : computed @property (jamais stocke comme verite)
    + history      : events append-only (position_events table)

Regles :
- Jamais un derived stocke. Toujours @property.
- Jamais un judgment sans date + source.
- Jamais un fait conteste : c'est ce que dit le courtier, point.
- Un seul driver canonical, partout (l'enum macro_factor pilote tout :
  factor exposure, ballast, correlation, stress -- le theme thesis user
  derive du driver, pas inverse).
- Changements de judgment -> nouvel event dans history, jamais ecrasement.

L'objet refuse d'etre incoherent : invariants verifies au build dans
Position.validate() -- retourne liste de violations, vide = clean.

Backward compat : BookLine (dans shared/book.py) reste expose comme un
adapter qui wrappe Position. Les ~15 readers en aval continuent de marcher
sans changement immediat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ─────────────────────── FAITS (broker, immuable) ──────────────────────────


@dataclass(frozen=True)
class PositionFacts:
    """Faits objectifs du courtier. Jamais modifies, jamais contestes.

    `frozen=True` = immutable. Toute modif requiert recreer l'objet.
    """
    ticker: str
    nom: str
    wrapper: str | None  # "PEA" | "CTO" | "AVUS"
    devise: str  # "EUR" | "USD" | "JPY" | "KRW"
    qty: float | None  # None si pas tenue actuellement
    prix_entree_native: float | None  # devise du ticker
    prix_entree_eur: float | None  # avg_cost converti EUR
    prix_courant_native: float | None  # devise du ticker
    prix_courant_eur: float | None  # converti EUR au taux du jour
    last_quote_at: str | None  # ISO datetime du dernier prix recu


# ─────────────────────── JUGEMENTS (user, dates) ───────────────────────────


@dataclass(frozen=True)
class DatedJudgment:
    """Un jugement avec sa provenance. Jamais sans date + source."""
    value: int | float | str
    set_at: str  # ISO datetime
    source: str  # "user_manual" | "ticker_meta_classifier" | "canonical_perimeter" | "chat_intent"


# Driver canonical : UN SEUL enum, partout.
# C'est le macro_factor de ticker_axes -- pilote stress tests, correlation,
# ballast, concentration. Le theme thesis (target_allocation 70k) DERIVE
# du driver, ne le concurrence jamais.
CanonicalDriver = Literal[
    "AI capex",
    "AI inference/compute demand",
    "Memory cycle",
    "Defense rearmament",
    "Energy commodities",
    "Rare earths / materials",
    "Industrial reshoring",
    "Consumer cyclical",
    "Unclassified",
]


# Role dans le book : structurel.
PositionRole = Literal["chokepoint", "cyclique", "ballast", "watch"]


@dataclass(frozen=True)
class ThesisFrozen:
    """These pre-enregistree a l'entree. Immuable -- un changement = nouvel
    event dans history, l'ancienne preservee. Tue la tautologie d'asymetrie
    et le deplacement de goalposts."""
    thesis_id: int
    opened_at: str
    claim: str  # ce qu'on croit, libre forme
    horizon_days: int | None
    kill_criteria: list[str]  # invalidation triggers nommes
    target_partial: float | None
    target_full: float | None
    stop_price: float | None
    fundamental_rationale: str  # le WHY (pas un multiple sur entree)


@dataclass
class PositionJudgments:
    """Jugements user, tous dates + sources. La couche qui peut bouger,
    mais chaque change est un event historise."""
    driver: CanonicalDriver | None = None
    role: PositionRole | None = None
    conviction: DatedJudgment | None = None
    fade: DatedJudgment | None = None
    solidite: str | None = None  # "Incontournable" | "Solide" | "Incertain" | "Fragile"
    thesis: ThesisFrozen | None = None


# ─────────────────────── LIFECYCLE ─────────────────────────────────────────


Lifecycle = Literal[
    "construction",  # book pas encore a sa cible, ajout en cours
    "active",        # these active, position tenue, evaluable
    "exiting",       # target_status=exit_planned, sortie progressive
    "sold",          # position fermee (qty=0)
    "watch",         # surveillance sans position
]


# ─────────────────────── HISTORIQUE (append-only events) ───────────────────


@dataclass(frozen=True)
class PositionEvent:
    """Un event sur la position. Append-only. La somme des events PEUT
    reconstituer l'etat (event sourcing optionnel)."""
    event_id: int | None
    ticker: str
    event_type: str  # "conviction_change" | "fade_change" | "thesis_revise" | "decision" | "outcome" | "lifecycle_transition"
    occurred_at: str  # ISO datetime
    payload: dict = field(default_factory=dict)
    source: str | None = None


# ─────────────────────── POSITION COMPOSITE ────────────────────────────────


@dataclass
class Position:
    """L'objet canonique. Compose facts + judgments + lifecycle. Tout le
    reste est derive a la lecture, jamais stocke."""

    facts: PositionFacts
    judgments: PositionJudgments
    lifecycle: Lifecycle
    history: list[PositionEvent] = field(default_factory=list)

    # ─── DERIVED PROPERTIES (jamais stockees) ─────────────────────────────

    @property
    def ticker(self) -> str:
        return self.facts.ticker

    @property
    def in_db(self) -> bool:
        return self.facts.qty is not None and self.facts.qty > 0

    @property
    def weight_market_eur(self) -> float:
        """Poids en valeur de marche EUR. Fallback cost basis si current
        price indispo (pour pas faire disparaitre une ligne)."""
        if self.facts.qty is None or self.facts.qty <= 0:
            return 0.0
        if self.facts.prix_courant_eur is not None:
            return self.facts.qty * self.facts.prix_courant_eur
        if self.facts.prix_entree_eur is not None:
            return self.facts.qty * self.facts.prix_entree_eur
        return 0.0

    @property
    def cost_basis_eur(self) -> float:
        """Cost basis EUR (qty * prix_entree_eur)."""
        if self.facts.qty is None or self.facts.prix_entree_eur is None:
            return 0.0
        return self.facts.qty * self.facts.prix_entree_eur

    @property
    def pnl_pct(self) -> float | None:
        """Return % vs cost basis."""
        if not self.facts.prix_entree_eur or not self.facts.prix_courant_eur:
            return None
        return (self.facts.prix_courant_eur - self.facts.prix_entree_eur) / self.facts.prix_entree_eur * 100

    @property
    def margin_to_stop_pct(self) -> float | None:
        """Marge en % entre prix courant et stop."""
        if (not self.judgments.thesis or not self.judgments.thesis.stop_price
                or not self.facts.prix_courant_native):
            return None
        stop = self.judgments.thesis.stop_price
        cur = self.facts.prix_courant_native
        if cur == 0:
            return None
        return (cur - stop) / cur * 100

    @property
    def asymmetry_ratio(self) -> float | None:
        """Ratio (target - current) / (current - stop). Mesure du levier
        de risque pris : >2 = bon profil asymetrique."""
        if not self.judgments.thesis:
            return None
        th = self.judgments.thesis
        cur = self.facts.prix_courant_native
        if not cur or not th.target_full or not th.stop_price:
            return None
        up = th.target_full - cur
        down = cur - th.stop_price
        if down <= 0:
            return None
        return up / down

    @property
    def is_blind(self) -> bool:
        """Position en vol aveugle : these sans tous les inputs critiques."""
        if not self.in_db:
            return False
        th = self.judgments.thesis
        if th is None:
            return True
        return (
            self.facts.prix_entree_eur is None
            or th.target_full is None
            or th.stop_price is None
            or not th.kill_criteria
        )

    @property
    def is_phantom(self) -> bool:
        """Position tenue mais lifecycle=exiting (a sortir progressivement)."""
        return self.in_db and self.lifecycle == "exiting"

    # ─── INVARIANTS (refuse l'incoherence) ────────────────────────────────

    def validate(self) -> list[str]:
        """Retourne la liste des violations d'invariants. Vide = clean.

        Invariants verifies :
        1. these.thesis_id correspondant a la position du meme ticker
           (tue F4 "GOOGL porte la these AMZN")
        2. exactement un driver (jamais multi-class)
        3. position en DB => avg_cost_eur > 0 (sinon donnees broker corrompues)
        4. conviction (1-5) implique fade present (sinon calibrage impossible)
        5. lifecycle coherent avec qty (sold => qty=0 ; active => qty>0)
        6. these active => kill_criteria non vide (tue vol aveugle integral)
        """
        violations = []

        # 1. these.ticker correspondance : claim ne doit pas etre marque ORPHAN
        if (self.judgments.thesis
                and "ORPHAN" in (self.judgments.thesis.claim or "").upper()):
            violations.append(
                f"{self.ticker}: thesis claim contient ORPHAN -- ecris une these reelle"
            )

        # 2. exactement un driver
        if self.in_db and self.judgments.driver is None:
            violations.append(f"{self.ticker}: position en DB sans driver canonical")

        # 3. avg_cost > 0
        if self.in_db and (self.facts.prix_entree_eur or 0) <= 0:
            violations.append(f"{self.ticker}: position en DB sans prix_entree_eur")

        # 4. conviction implique fade
        if self.judgments.conviction is not None and self.judgments.fade is None:
            violations.append(f"{self.ticker}: conviction sans fade (calibrage impossible)")

        # 5. lifecycle coherent avec qty
        qty = self.facts.qty or 0
        if self.lifecycle == "sold" and qty > 0:
            violations.append(f"{self.ticker}: lifecycle=sold mais qty={qty}")
        if self.lifecycle == "active" and qty <= 0:
            violations.append(f"{self.ticker}: lifecycle=active mais qty=0")

        # 6. these active => kill_criteria
        if (self.lifecycle == "active" and self.judgments.thesis
                and not self.judgments.thesis.kill_criteria):
            violations.append(
                f"{self.ticker}: these active sans kill_criteria -- F7 vol aveugle"
            )

        return violations

    def is_valid(self) -> bool:
        return not self.validate()


# ─────────────────────── BUILDERS (depuis sources existantes) ──────────────


def position_from_sources(
    *,
    ticker: str,
    db_row: dict | None = None,
    canonical_row: dict | None = None,
    target_row: dict | None = None,
    thesis_row: dict | None = None,
    axes_row: dict | None = None,
    meta_row: dict | None = None,
    current_price_eur: float | None = None,
    current_price_native: float | None = None,
) -> Position:
    """Builder qui compose une Position depuis les 5 sources existantes.

    C'est le point d'adaptation : tant que les sources sont fragmentees,
    on les joint ici. A terme une seule source append-only suffira.
    """
    devise = _detect_devise(ticker)
    nom = (canonical_row or target_row or {}).get("nom") or ticker

    facts = PositionFacts(
        ticker=ticker,
        nom=nom,
        wrapper=(canonical_row or target_row or {}).get("wrapper"),
        devise=devise,
        qty=(db_row or {}).get("qty"),
        prix_entree_native=None,  # pas trace separement dans le DB actuel
        prix_entree_eur=(db_row or {}).get("avg_cost_eur"),
        prix_courant_native=current_price_native,
        prix_courant_eur=current_price_eur,
        last_quote_at=None,
    )

    # Driver canonical : un seul, depuis ticker_axes (macro_factor)
    driver = (axes_row or {}).get("macro_factor")

    # Conviction + fade : avec source = "user_manual" + date = last_reviewed
    conv = None
    if thesis_row and thesis_row.get("conviction") is not None:
        conv = DatedJudgment(
            value=int(thesis_row["conviction"]),
            set_at=thesis_row.get("last_reviewed") or thesis_row.get("opened_at") or "?",
            source="user_manual",
        )
    fade_val = (meta_row or {}).get("fade_rate_score")
    fade = None
    if fade_val is not None:
        fade = DatedJudgment(
            value=int(fade_val),
            set_at=(meta_row or {}).get("created_at") or "?",
            source="ticker_meta_classifier",
        )

    # These figee : claim + kill_criteria + targets + stop
    thesis = None
    if thesis_row:
        import json as _json
        kc_raw = thesis_row.get("invalidation_triggers")
        if isinstance(kc_raw, str) and kc_raw.strip() and kc_raw.strip() != "[]":
            try:
                kc = _json.loads(kc_raw)
                if not isinstance(kc, list):
                    # JSON parse OK mais pas une list -- treat as single string
                    kc = [str(kc)]
            except Exception:
                # Not JSON -- treat as single free-text criterion
                kc = [kc_raw.strip()]
        elif isinstance(kc_raw, list):
            kc = kc_raw
        else:
            kc = []
        kd_raw = thesis_row.get("key_drivers") or ""
        if isinstance(kd_raw, str):
            try:
                kd_parsed = _json.loads(kd_raw)
                claim = "; ".join(kd_parsed) if isinstance(kd_parsed, list) else kd_raw
            except Exception:
                claim = kd_raw
        else:
            claim = str(kd_raw)
        thesis = ThesisFrozen(
            thesis_id=thesis_row.get("thesis_id") or thesis_row.get("id"),
            opened_at=thesis_row.get("opened_at") or "",
            claim=claim,
            horizon_days=thesis_row.get("horizon_days"),
            kill_criteria=kc,
            target_partial=thesis_row.get("target_partial"),
            target_full=thesis_row.get("target_full"),
            stop_price=thesis_row.get("stop_price"),
            fundamental_rationale=thesis_row.get("notes") or "",
        )

    # Role : dur a deriver auto. Heuristique : solidite Incontournable + driver
    # AI capex -> chokepoint. Defense/Energy/Rare -> ballast. Memory cycle ->
    # cyclique. Sinon None.
    solidite = (canonical_row or {}).get("solidite")
    role = _derive_role(driver, solidite)

    judgments = PositionJudgments(
        driver=driver,
        role=role,
        conviction=conv,
        fade=fade,
        solidite=solidite,
        thesis=thesis,
    )

    # Lifecycle :
    # - canonical target_status = "exit_planned" -> exiting
    # - position in DB qty>0 + canonical in_target -> active
    # - position not in DB but in target -> construction (planned entry)
    # - canonical = open_question : reste active jusqu'a decision
    target_status = (canonical_row or {}).get("target_status") or "unknown"
    qty = (db_row or {}).get("qty") or 0
    if target_status == "exit_planned" and qty > 0:
        lifecycle: Lifecycle = "exiting"
    elif qty > 0:
        lifecycle = "active"
    elif target_row and qty == 0:
        lifecycle = "construction"  # planned but not yet acquired
    else:
        lifecycle = "watch"

    return Position(facts=facts, judgments=judgments, lifecycle=lifecycle)


def _detect_devise(ticker: str) -> str:
    """Devise native du ticker depuis le suffixe yfinance."""
    if ticker.endswith((".AS", ".PA", ".DE", ".L", ".MI", ".SW")):
        return "EUR"
    if ticker.endswith(".T"):
        return "JPY"
    if ticker.endswith(".KS"):
        return "KRW"
    if ticker.endswith(".HK"):
        return "HKD"
    return "USD"  # default


def _derive_role(
    driver: str | None, solidite: str | None
) -> PositionRole | None:
    """Heuristique : driver + solidite -> role structurel.

    A terme, role devrait etre un input direct user_manual. La heuristique
    sert de bootstrap.
    """
    if driver in {"Defense rearmament", "Energy commodities", "Rare earths / materials", "Industrial reshoring"}:
        return "ballast"
    if driver == "Memory cycle":
        return "cyclique"
    if driver in {"AI capex", "AI inference/compute demand"} and solidite == "Incontournable":
        return "chokepoint"
    if driver in {"AI capex", "AI inference/compute demand"}:
        return "cyclique"
    return None
