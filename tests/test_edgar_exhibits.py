"""Fixture regression : SEC EDGAR exhibit extractor -> V2 sortie attendue.

L'arc bug audit 30/05 (decision log #01 iter 5) : filing_url pointait vers
cover page, V2 sortait 100% watch ev=none sur boilerplate. Fix iter 6 :
edgar_exhibits.extract_filing_content() resout vers les exhibits materials.
DoD verifiee sur NVDA Q1 FY27 8-K -> V2 prob=0.750 bullish strong.

Cette fixture rend le bug d'origine BRUYANT a la prochaine regression :
- Si l'extracteur regresse (cover page only), V2 redescend a watch ev=none
- Si V2 perd sa capacite a discriminer sur contenu strong, prob descend
- Le test fail loud sur ces 2 cas

Pourquoi network-dependent (pas pure unit) : la chaine entiere SEC -> extract
-> V2 est ce qu'on protege. Mock = on protege l'illusion.

Marker : `slow` -- skip par defaut en CI rapide, run en pre-release.
"""

import pytest

pytestmark = pytest.mark.slow


def test_extract_filing_content_returns_substantial_text():
    """Sur une 8-K NVDA Q1 FY27 reelle, l'extracteur doit retourner
    au moins 5000 chars de contenu (vs ~300 si bug regression cover page).
    """
    from shared.edgar_exhibits import extract_filing_content

    NVDA_8K_INDEX = (
        "https://www.sec.gov/Archives/edgar/data/1045810/"
        "000104581026000051/nvda-20260520.htm"
    )
    content = extract_filing_content(NVDA_8K_INDEX)
    assert len(content) >= 5000, (
        f"Extract returned only {len(content)} chars -- regression vers cover page?"
    )
    # Doit contenir un mot-cle revenu/earnings reel (pas que boilerplate)
    assert "revenue" in content.lower() or "earnings" in content.lower(), (
        "Extract ne contient pas mots-cles revenue/earnings -- bon exhibit fetched?"
    )


def test_v2_on_extracted_nvda_earnings_returns_strong():
    """E2E : extracteur NVDA 8-K Q1 FY27 -> V2 -> doit sortir strong bullish >= 0.65.
    Le bug d'origine etait silencieux (sortait watch ev=none). Cette fixture le
    rend bruyant : si V2 ou extracteur regresse, le test fail explicitement.
    """
    from intelligence import signal_scorer_v2
    from shared.edgar_exhibits import extract_filing_content

    NVDA_8K_INDEX = (
        "https://www.sec.gov/Archives/edgar/data/1045810/"
        "000104581026000051/nvda-20260520.htm"
    )
    body = extract_filing_content(NVDA_8K_INDEX)
    assert len(body) >= 5000, "extract pre-condition fail"

    result = signal_scorer_v2.score_directional_probability(
        title="NVDA 8-K filed -- SEC Item 2.02 Results of Operations",
        summary=body[:800],
        ticker="NVDA",
        horizon_days=30,
        content=body[800:4500],
        entities=["NVDA"],
        source_name=None,
    )
    assert result is not None, "V2 returned None"
    # DoD verifiee 30/05 : prob=0.750 bullish strong sur ce filing precis.
    # Marge tolerance : prob >= 0.65 (call directional fort) ET ev=strong.
    assert result["direction"] == "bullish", (
        f"NVDA earnings 8-K doit etre bullish, got {result['direction']}"
    )
    assert result["evidence_strength"] == "strong", (
        f"NVDA earnings 8-K doit etre strong, got {result['evidence_strength']}"
    )
    assert result["probability"] >= 0.65, (
        f"NVDA earnings 8-K doit produire prob >= 0.65, got {result['probability']}"
    )


def test_v2_on_extracted_boilerplate_8k_stays_watch():
    """Une 8-K de routine (debt issuance Notes) doit RESTER en watch ev=none
    meme avec l'extracteur actif. V2 doit discriminer le boilerplate du material.
    """
    from intelligence import signal_scorer_v2
    from shared.edgar_exhibits import extract_filing_content

    # GOOGL 8-K 2026-05-21 = debt notes issuance (boilerplate)
    GOOGL_8K_INDEX = (
        "https://www.sec.gov/Archives/edgar/data/1652044/"
        "000119312526234488/d144566d8k.htm"
    )
    body = extract_filing_content(GOOGL_8K_INDEX)
    if len(body) < 1000:
        pytest.skip("extract returned too little content -- network issue?")

    result = signal_scorer_v2.score_directional_probability(
        title="GOOGL 8-K filed -- SEC Item 8.01 Other Events",
        summary=body[:800],
        ticker="GOOGL",
        horizon_days=30,
        content=body[800:4500],
        entities=["GOOGL"],
        source_name=None,
    )
    assert result is not None
    # Boilerplate debt -> watch ou prob <= 0.55
    assert result["direction"] == "watch" or result["probability"] <= 0.55, (
        f"Boilerplate 8-K (debt notes) ne devrait pas produire de call directionnel fort, "
        f"got dir={result['direction']} prob={result['probability']}"
    )
