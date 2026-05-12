"""Phase Digestion 3a — Classify signals into 4 types (catalyst / data / narrative / opinion).

catalyst: specific upcoming event (earnings, FOMC, M&A announcement, product launch)
data: published numbers/metrics (CPI, jobs report, company earnings figures released)
narrative: story-driven thematic piece (AI hype, China decoupling, structural change)
opinion: commentary/analysis without new info (column, prediction, opinion piece)
"""
import logging
log = logging.getLogger(__name__)

VALID_TYPES = ('catalyst', 'data', 'narrative', 'opinion')


def classify_signal_type(title, summary=None, content=None):
    """Single Haiku call. Returns one of catalyst/data/narrative/opinion or None on failure."""
    from shared import llm
    title = (title or '')[:200]
    summary = (summary or '')[:400] if summary else ''
    content_snippet = (content or '')[:600] if content else ''

    prompt = (
        "Classify this finance/markets signal into EXACTLY ONE category:\n\n"
        "- catalyst: specific upcoming or just-happened event (earnings, FOMC decision, M&A announcement, product launch, ruling, sanction)\n"
        "- data: published numbers/metrics (CPI release, jobs report, company earnings figures, economic data)\n"
        "- narrative: story-driven thematic piece (AI hype, China decoupling, sector rotation, structural shift)\n"
        "- opinion: commentary/analysis without new specific info (predictions, op-eds, general takes)\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n"
        f"Content: {content_snippet}\n\n"
        "Output ONLY one word from: catalyst, data, narrative, opinion. No punctuation, no explanation."
    )
    try:
        result = llm.call(prompt, tier='extract', max_tokens=10)
        t = (result or '').strip().lower().replace('.', '').replace(',', '')
        if t in VALID_TYPES:
            return t
        # Fuzzy fallback
        for cat in VALID_TYPES:
            if cat in t:
                return cat
    except Exception as e:
        log.warning(f"classify_signal_type failed: {e}")
    return None


def classify_pending_signals(limit=50):
    """Run classifier on signals with signal_type=NULL. Returns count classified."""
    from shared import storage
    pending = storage.get_unclassified_signals(limit=limit)
    classified = 0
    type_counts = {}
    for sig in pending:
        t = classify_signal_type(sig.get('title'), sig.get('summary'), sig.get('content'))
        if t:
            storage.set_signal_type(sig['id'], t)
            classified += 1
            type_counts[t] = type_counts.get(t, 0) + 1
    log.info(f"signal classifier: {classified}/{len(pending)} classified, types={type_counts}")
    return classified, type_counts
