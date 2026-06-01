"""Ticker -> brand logo URL helper. Google favicon API + fallback graceful.

Pattern TR/Robinhood : logo carre/rond ~22-28px a cote du ticker.
Source primaire : google.com/s2/favicons?domain={domain}&sz=64
  - Clearbit logo API mort (HubSpot acquisition 2023, deprecated)
  - DuckDuckGo icons fonctionne aussi mais qualite plus faible
  - Brandfetch / Logo.dev requierent token
  - Google favicon : gratuit, sans auth, multi-size, fiable
Fallback (onerror) : cercle gris + initiale du ticker via CSS.

Limite Google favicon : favicons typiquement carres 64x64, parfois plus
petits ou simples. Pour quality logos pro plus tard : self-host SVGs dans
dashboard/static/brand/logos/{ticker}.svg.
"""

from __future__ import annotations

from pathlib import Path

# Self-hosted SVG logos directory : dashboard/static/brand/logos/{TICKER}.svg
# Servi par serve.py via directory="dashboard" -> URL "/static/brand/logos/X.svg"
_LOGO_LOCAL_DIR = (Path(__file__).resolve().parent.parent / "dashboard" / "static" / "brand" / "logos")


def _scan_local_logos() -> dict[str, str]:
    """Scan logos dir, returns {TICKER_UPPER: filename}. Pas de cache module-level :
    re-scan a chaque appel pour picker up les fichiers ajoutes via download_logos.py
    sans avoir a reload le module (40 fichiers ~= 5ms disque)."""
    out: dict[str, str] = {}
    if _LOGO_LOCAL_DIR.exists():
        for f in _LOGO_LOCAL_DIR.iterdir():
            if f.suffix.lower() in (".svg", ".png", ".jpg", ".webp"):
                out[f.stem.upper()] = f.name
                out[f.stem] = f.name
    return out


def local_logo_url(ticker: str) -> str | None:
    """Si un SVG/PNG self-host existe pour ce ticker, retourne URL relative."""
    fname = _scan_local_logos().get(ticker.upper()) or _scan_local_logos().get(ticker)
    if not fname:
        return None
    return f"/static/brand/logos/{fname}"

# Mapping ticker -> domain pour Clearbit. Construit manuellement pour les
# tickers du book PRESAGE actuel + futurs candidats fiables.
# Coverage : 30 tickers actifs au 01/06/2026 + extras populaires.
TICKER_DOMAIN: dict[str, str] = {
    # ---- US large tech / semis ----
    "AAPL": "apple.com",
    "MSFT": "microsoft.com",
    "GOOGL": "google.com",
    "GOOG": "google.com",
    "AMZN": "amazon.com",
    "META": "meta.com",
    "NVDA": "nvidia.com",
    "TSLA": "tesla.com",
    "AMD": "amd.com",
    "AVGO": "broadcom.com",
    "MU": "micron.com",
    "MRVL": "marvell.com",
    "TSM": "tsmc.com",
    "KLAC": "kla.com",
    "TER": "teradyne.com",
    "SNPS": "www.synopsys.com",
    "SNOW": "snowflake.com",
    "ENTG": "entegris.com",
    "COHR": "coherent.com",
    "ALAB": "asteralabs.com",
    "VRT": "vertiv.com",
    "LNG": "cheniere.com",
    "CCJ": "cameco.com",
    "MP": "mpmaterials.com",
    # ---- Europe ----
    "ASML.AS": "asml.com",
    "BESI.AS": "besi.com",
    "STMPA.PA": "st.com",
    "SAF.PA": "safran-group.com",
    "HO.PA": "thalesgroup.com",
    "SU.PA": "se.com",
    # ---- Japan / Korea ----
    "4063.T": "shinetsuamerica.com",
    "6857.T": "advantest.com",
    "6920.T": "lasertec.co.jp",
    "7011.T": "mhi.com",
    "8035.T": "tel.com",
    "6890.T": "ferrotec.com",
    "6273.T": "smcworld.com",
    "6324.T": "harmonicdrive.net",
    "000660.KS": "skhynix.com",
    # ---- HK / China ----
    "1347.HK": "hhgrace.com",
    "0388.HK": "hkex.com.hk",
    "0700.HK": "tencent.com",
    # ---- Netherlands (ASM International, distinct de ASML) ----
    "ASM.AS": "asm.com",
    # ---- India ----
    "HDB": "hdfcbank.com",
    "INFY": "infosys.com",
    # ---- US extras ----
    "ACMR": "acmrcsh.com",
    "GEV": "gevernova.com",
    "BWXT": "bwxt.com",
    "CEG": "constellationenergy.com",
}


def domain_for(ticker: str) -> str | None:
    """Lookup domain pour Clearbit. Return None si pas dans le map."""
    return TICKER_DOMAIN.get(ticker.upper()) or TICKER_DOMAIN.get(ticker)


def logo_html(ticker: str, size: int = 22) -> str:
    """Retourne <img favicon /> avec cascade de fallbacks : Google -> DuckDuckGo -> initiale.

    Cascade 01/06 :
     1. Google favicon API (`google.com/s2/favicons?domain=X&sz=64`)
     2. Si Google fail -> DuckDuckGo icons (`icons.duckduckgo.com/ip3/X.ico`)
     3. Si tout fail -> cercle gris + initiale du ticker via CSS

    `loading=eager` (pas lazy) car tape ticker scroll dynamique + viewport intent.
    `&amp;` escape HTML stricte pour eviter parsing edge cases browser.
    """
    # Priorite 1 : SVG/PNG self-host (controle full quality, indispensable
    # pour tickers asiatiques que Google favicon API ne couvre pas).
    local = local_logo_url(ticker)
    if local:
        initial_local = ticker[0].upper() if ticker else "?"
        fb_local = (
            f"this.outerHTML='<span class=&quot;tklogo tkfb&quot;>{initial_local}</span>'"
        )
        return (
            f'<img class="tklogo" src="{local}" alt="" onerror="{fb_local}">'
        )
    dom = domain_for(ticker)
    initial = ticker[0].upper() if ticker else "?"
    if not dom:
        return f'<span class="tklogo tkfb">{initial}</span>'
    # Fallback cascade : DuckDuckGo en step 2, initial-circle en step 3.
    # &quot; pour escape les " inner dans attribute string.
    ddg = f"https://icons.duckduckgo.com/ip3/{dom}.ico"
    fb_final = (
        f"this.outerHTML='<span class=&quot;tklogo tkfb&quot;>{initial}</span>'"
    )
    fb_step2 = (
        f"this.onerror=function(){{{fb_final}}};this.src='{ddg}'"
    )
    return (
        f'<img class="tklogo" '
        f'src="https://www.google.com/s2/favicons?domain={dom}&amp;sz=64" '
        f'alt="" onerror="{fb_step2}">'
    )
