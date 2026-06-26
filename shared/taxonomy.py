"""Single source of truth for ticker categorization (layer, driver, geo, status).

Cure 26/06/2026 — supersède 5 sources qui divergeaient :
  A) shared/sector_taxonomy.py:TICKER_SECTOR  (mort en Phase 1)
  B) config.yaml:concentration.clusters.compute_ai  (dérivée en Phase 4 — kill_switch)
  C) config/sectors.yaml  (vue dérivée via sector_highlevel() en Phase 3)
  D) config.yaml:sectors_taxonomy + sectors:  (survit pour caps, usages dashboard morts)
  E) dashboard/render.py:_sectors/_sector_blocks/...  (mort en Phase 2)

Source unique = config/presage_taxonomy.yaml. Toute catégorisation dashboard/risk
passe par ce module. Validations strictes au premier accès (raise sur incohérence —
CONVENTIONS §6, jamais de défaut silencieux).
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

import yaml

_YAML_PATH = Path(__file__).parent.parent / "config" / "presage_taxonomy.yaml"


class TaxonomyError(Exception):
    """Catégorisation incohérente ou ticker manquant. Jamais de défaut silencieux."""


def _layer_full(category: str, sub: str) -> str:
    return f"{category}/{sub}"


@functools.lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    if not _YAML_PATH.exists():
        raise TaxonomyError(f"YAML absent : {_YAML_PATH}")
    with open(_YAML_PATH, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    layers_vocab = {
        _layer_full(cat, sub)
        for cat, subs in (data.get("layers") or {}).items()
        for sub in (subs or [])
    }
    drivers_vocab = set(data.get("drivers") or [])
    geos_vocab = set(data.get("geos") or [])
    statuses_vocab = set(data.get("statuses") or [])

    positions = data.get("positions") or {}
    if not positions:
        raise TaxonomyError("positions block empty in YAML")

    for slug, p in positions.items():
        tk = p.get("ticker")
        if not tk:
            raise TaxonomyError(f"position {slug} : missing ticker field")
        lp = p.get("layer_primary")
        layers = p.get("layer") or []
        if lp not in layers:
            raise TaxonomyError(
                f"position {slug} ({tk}) : layer_primary={lp!r} not in layer list {layers!r}"
            )
        for lr in layers:
            if lr not in layers_vocab:
                raise TaxonomyError(
                    f"position {slug} ({tk}) : layer {lr!r} not in vocabulary"
                )
        if p.get("driver") not in drivers_vocab:
            raise TaxonomyError(
                f"position {slug} ({tk}) : driver={p.get('driver')!r} not in vocab"
            )
        if p.get("geo") not in geos_vocab:
            raise TaxonomyError(
                f"position {slug} ({tk}) : geo={p.get('geo')!r} not in vocab"
            )
        if p.get("status") not in statuses_vocab:
            raise TaxonomyError(
                f"position {slug} ({tk}) : status={p.get('status')!r} not in vocab"
            )

    return data


@functools.lru_cache(maxsize=1)
def _by_ticker() -> dict[str, dict[str, Any]]:
    raw = _load_raw()
    out: dict[str, dict[str, Any]] = {}
    for slug, p in (raw.get("positions") or {}).items():
        tk = p["ticker"]
        if tk in out:
            raise TaxonomyError(f"duplicate ticker {tk!r} in mapping (slug {slug})")
        out[tk] = p
    return out


def get_taxonomy(ticker: str) -> dict[str, Any]:
    """Returns {ticker, name, layer, layer_primary, driver, geo, status}.

    Raises TaxonomyError if ticker absent (jamais de défaut silencieux).
    """
    idx = _by_ticker()
    if ticker not in idx:
        raise TaxonomyError(
            f"ticker {ticker!r} absent du mapping (config/presage_taxonomy.yaml). "
            f"Ajouter la position ou exclure du book."
        )
    return idx[ticker]


def by_driver(driver: str, status: str = "held") -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["driver"] == driver and p["status"] == status]


def by_geo(geo: str, status: str = "held") -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["geo"] == geo and p["status"] == status]


def by_layer_primary(layer_primary: str, status: str = "held") -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["layer_primary"] == layer_primary and p["status"] == status]


def held_tickers() -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["status"] == "held"]


def planned_tickers() -> list[str]:
    return [tk for tk, p in _by_ticker().items() if p["status"] == "planned"]


def coverage_holes(status: str = "held") -> list[str]:
    """Sous-couches du vocabulaire absentes de la liste `layer` du périmètre demandé.

    status='held'     → trous = sous-couches non couvertes par tes 26 held.
    status='planned'  → trous = sous-couches non couvertes par held ∪ planned (trous ouverts).
    """
    raw = _load_raw()
    vocab = {
        _layer_full(cat, sub)
        for cat, subs in (raw.get("layers") or {}).items()
        for sub in (subs or [])
    }
    if status == "held":
        scope = {"held"}
    elif status == "planned":
        scope = {"held", "planned"}
    else:
        scope = {status}
    covered = set()
    for _tk, p in _by_ticker().items():
        if p["status"] not in scope:
            continue
        for lr in p.get("layer") or []:
            covered.add(lr)
    return sorted(vocab - covered)


def sector_highlevel(ticker: str) -> str | None:
    """Bucket high-level Brier-side (semis / energy_commodities / defense_industrials_eu / tech_mega / auto_ev).

    Logique (Phase 3, 26/06/2026 — supersède config/sectors.yaml) :
      1. Si ticker ∈ bucket.tickers d'un bucket → return ce bucket (overrides + historiques).
      2. Sinon, layer-mère du mapping ∈ bucket.by_category → return bucket par défaut.
      3. Sinon None (ticker hors-mapping et hors-overrides).

    Préserve l'historique Brier : AMZN/GOOGL → tech_mega (pas semis), MP → energy_commodities, etc.
    """
    info = sector_highlevel_info(ticker)
    return info["id"] if info else None


def sector_highlevel_info(ticker: str) -> dict[str, Any] | None:
    """Bucket high-level RICHE (Phase 3) : {id, label, index, cycle_phase, cycle_note}.

    Source unique post-cure : presage_taxonomy.yaml:sector_highlevel_buckets.
    Replace shared/sectors.py:sector_for_ticker (façade conservée, mais lit ici).
    """
    raw = _load_raw()
    buckets = raw.get("sector_highlevel_buckets") or {}
    # 1. Override / explicit tickers list (priorité au 1er bucket qui le mentionne)
    for bid, bdef in buckets.items():
        if ticker in (bdef.get("tickers") or []):
            return _build_sector_info(bid, bdef)
    # 2. Résolution par catégorie-mère via mapping principal
    try:
        tax = get_taxonomy(ticker)
    except TaxonomyError:
        return None
    lp = tax.get("layer_primary") or ""
    if "/" not in lp:
        return None
    category = lp.split("/", 1)[0]
    for bid, bdef in buckets.items():
        if category in (bdef.get("by_category") or []):
            return _build_sector_info(bid, bdef)
    return None


def _build_sector_info(bid: str, bdef: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": bid,
        "label": bdef.get("label", bid),
        "index": bdef.get("index", ""),
        "cycle_phase": bdef.get("cycle_phase", "unknown"),
        "cycle_note": bdef.get("cycle_note", ""),
    }


def cycle_phase_for(ticker: str) -> str:
    """Cycle phase courante du bucket Brier d'un ticker. 'unknown' si non-catalogué.

    Equivalent à shared/sectors.py:cycle_phase_for_ticker (façade canonique
    conservée mais sa source bascule ici).
    """
    info = sector_highlevel_info(ticker)
    return info["cycle_phase"] if info else "unknown"


def same_sector_tickers(ticker: str, status: str = "held") -> list[str]:
    """Tickers in the same high-level sector bucket (Brier-side), excluding the input.

    Used by adversarial co-pilot for "adjacent signals" lookup. Maps to
    `sector_highlevel(ticker)` — broad bucket (semis / energy_commodities /
    defense_industrials_eu) — which best matches the legacy TICKER_SECTOR
    grouping ("AI Compute" → multiple semis sub-layers were grouped together).
    Returns [] if ticker has no bucket.
    """
    bucket = sector_highlevel(ticker)
    if not bucket:
        return []
    return [
        tk
        for tk, p in _by_ticker().items()
        if tk != ticker
        and p["status"] == status
        and sector_highlevel(tk) == bucket
    ]


class SectorLabel(str):
    """Display label porteur de la mère ET de la sous-couche (Phase 2, 26/06/2026).

    Sous-classe de str : sa VALEUR string EST la catégorie-mère (compatibilité
    descendante avec tout caller qui fait `sectors.get(tk, "Other")` ou compare
    par égalité). L'attribut `.sub` porte la sous-couche pour un affichage
    hiérarchique (sous-ligne sous la mère dans la page Positions).

    Usage :
        s = SectorLabel('Compute', sub='Hyperscaler')
        s == 'Compute'           # True (string compare)
        f"{s}"                   # 'Compute'
        s.sub                    # 'Hyperscaler'

    Réserve 2 du red-team 26/06 : le tissu liant (mère) doit apparaître à l'écran
    sans sacrifier la précision (sous-couche). Le dict source porte les deux.
    """

    sub: str | None

    def __new__(cls, group: str, sub: str | None = None) -> SectorLabel:
        instance = super().__new__(cls, group)
        instance.sub = sub
        return instance


def make_sector_label(layer_primary: str | None) -> SectorLabel:
    """Build a SectorLabel from a layer_primary (group=mère, sub=sous-couche)."""
    return SectorLabel(category_label(layer_primary), sub=layer_label(layer_primary))


def layer_label(layer_primary: str | None) -> str:
    """Format a layer_primary 'category/sub' into a display label.

    'compute/hyperscaler'         → 'Hyperscaler'
    'manufacturing/foundry_leading'→ 'Foundry Leading'
    'memory/hbm'                  → 'HBM'
    'capital_equipment/litho'     → 'Litho'
    None                          → 'Sans thesis'

    On affiche la SOUS-couche (plus informative que la mère). Pour la mère,
    cf `category_label(layer_primary)`. Cure 26/06/2026 — Phase 2.
    """
    if not layer_primary or "/" not in layer_primary:
        return clean_sector(layer_primary)
    sub = layer_primary.split("/", 1)[1]
    return clean_sector(sub)


def category_label(layer_primary: str | None) -> str:
    """Format the catégorie-mère of a layer_primary into a display label.

    'compute/hyperscaler'         → 'Compute'
    'manufacturing/foundry_leading'→ 'Manufacturing'
    """
    if not layer_primary or "/" not in layer_primary:
        return clean_sector(layer_primary)
    cat = layer_primary.split("/", 1)[0]
    return clean_sector(cat)


def driver_label(driver: str | None) -> str:
    """Format a driver enum into a display label.

    'ai_capex'         → 'AI Capex'
    'resources_energy' → 'Resources Energy'
    """
    return clean_sector(driver)


def clean_sector(sid: str | None) -> str:
    """Format a sector_id (snake_case with optional trailing year) into a display label.

    'ai_compute_2026' → 'AI Compute' ; 'mag7' → 'MAG 7' ; None → 'Sans thesis'.
    Migrée depuis shared/sector_taxonomy.py:clean_sector lors de la cure
    5 sources → 1 (Phase 1, 26/06/2026). Pure formatting, ne dépend d'aucune
    table — sert au rendu de tout label catégoriel hérité.
    """
    if not sid:
        return "Sans thesis"
    s = re.sub(r"_20\d\d$", "", sid).replace("_", " ").title()
    return (
        s.replace(" Ai", " AI")
        .replace("Ai ", "AI ")
        .replace("Hpq", "HPQ")
        .replace("Eu ", "EU ")
        .replace("Mag7", "MAG 7")
        # Acronymes du vocabulaire taxonomy (26/06/2026) — Phase 2.
        # KNOWN-GAP P3 : cascade .replace fragile (chaque acronyme = ligne) +
        # risque de frappe sur sous-chaîne innocente. Refonte cible : dict
        # ACRONYMS appliqué par lookup sur token (split sur ' '), pas par
        # substitution globale. Réserve 1 du red-team 26/06.
        .replace("Hbm", "HBM")
        .replace("Eda", "EDA")
        .replace("Lng", "LNG")
        .replace("Asic", "ASIC")
        .replace("Cpu", "CPU")
        .replace("Gpu", "GPU")
        .replace("Cowos", "CoWoS")
        .replace("Idm Analog", "IDM Analog")
        .replace("Ip Cores", "IP Cores")
    )


def assert_held_cluster_consistency() -> None:
    """Phase 4 — kill_switch contract (27/06/2026).

    Vérifie l'égalité scopée au held entre :
      - B  : config.yaml:concentration.clusters.compute_ai (univers étendu)
      - M  : mapping ai_capex held (presage_taxonomy.yaml)

    Sur le périmètre DÉTENU (qty>0 en DB), B∩held DOIT être égal à M∩held.
    Sinon → TaxonomyError (fail-closed, ne pas armer le disjoncteur sur un
    périmètre faux). Cf brief Phase 4.

    Cette assertion est exécutée à chaque appel de _cluster_membership() côté
    kill_switch quand cluster_source='taxonomy_ai_capex_held' — coût négligeable
    et garantie de cohérence à chaque inspection live.
    """
    from pathlib import Path

    from shared import storage

    with storage.db() as cx:
        db_held = {
            row[0]
            for row in cx.execute("SELECT ticker FROM positions WHERE qty>0").fetchall()
        }
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    cluster_b = set(cfg.get("concentration", {}).get("clusters", {}).get("compute_ai") or [])
    held_in_b = {t for t in db_held if t in cluster_b}
    held_ai_mapping: set[str] = set()
    for t in db_held:
        try:
            if get_taxonomy(t).get("driver") == "ai_capex":
                held_ai_mapping.add(t)
        except TaxonomyError:
            pass
    if held_in_b != held_ai_mapping:
        b_only = sorted(held_in_b - held_ai_mapping)
        m_only = sorted(held_ai_mapping - held_in_b)
        raise TaxonomyError(
            f"divergence cluster B ↔ taxonomy mapping sur held (kill_switch contract Phase 4) : "
            f"B\\map={b_only}, map\\B={m_only}. "
            f"Aligner config.yaml:concentration.clusters.compute_ai et "
            f"presage_taxonomy.yaml driver=ai_capex avant d'armer le disjoncteur."
        )


def validate_against_db(*, raise_on_missing: bool = True) -> dict[str, list[str]]:
    """Cross-check : every DB held ticker (qty>0) ∈ mapping.

    Returns {"missing_in_mapping": [...], "in_db_not_held_in_map": [...]}.
    raise_on_missing=True (default) → TaxonomyError si DB held - mapping ≠ ∅.
    """
    from shared import storage

    with storage.db() as cx:
        db_held = {
            row[0] for row in cx.execute(
                "SELECT ticker FROM positions WHERE qty > 0"
            ).fetchall()
        }
    mapping_held = set(held_tickers())
    mapping_all = set(_by_ticker().keys())
    missing = sorted(db_held - mapping_all)
    in_db_not_held_in_map = sorted(db_held - mapping_held)
    result = {"missing_in_mapping": missing, "in_db_not_held_in_map": in_db_not_held_in_map}
    if raise_on_missing and missing:
        raise TaxonomyError(
            f"DB held tickers absent du mapping : {missing}. "
            f"Ajouter au YAML ou exclure du book."
        )
    return result
