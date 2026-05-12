"""Source credibility scoring engine.

Credibility = belief that signals from this source are useful.
Updates from two channels:
- User feedback (subjective, fast signal)
- Outcome resolution (objective, slow signal - Chunk 5)

Asymmetric updates: 'down' feedback weighs 2x more than 'up'
(info content higher when user pushes back).
"""
from shared import storage

FEEDBACK_DELTA = {
    'up': 0.05,
    'down': -0.10,
}


def apply_feedback(signal_id, rating):
    """Apply user feedback to a signal. Updates source credibility.

    Returns dict with old/new credibility for display.
    """
    sig = storage.get_signal(signal_id)
    if not sig:
        raise ValueError(f"Signal {signal_id} not found")
    if rating not in FEEDBACK_DELTA:
        raise ValueError(f"rating must be 'up' or 'down', got {rating}")

    storage.set_signal_feedback(signal_id, rating)
    delta = FEEDBACK_DELTA[rating]
    new_cred = storage.update_source_credibility(sig['source_id'], delta)

    return {
        'signal_id': signal_id,
        'source_id': sig['source_id'],
        'source_name': sig.get('source_name'),
        'old_credibility': sig.get('source_credibility'),
        'new_credibility': new_cred,
        'rating': rating,
        'delta': delta,
    }


def list_top_sources(n=10):
    """Format top sources for Telegram display."""
    sources = storage.get_top_sources(n=n, min_signals=3)
    if not sources:
        return "Pas assez de donnees (min 3 signaux par source)."
    lines = [f"Top {len(sources)} sources par credibility:"]
    for i, s in enumerate(sources, 1):
        lines.append(f"  {i}. {s['name'][:40]} - cred {s['credibility']:.2f} ({s['n_signals']} sig)")
    return "\n".join(lines)


def list_worst_sources(n=5):
    """Format worst sources for display (candidates to drop)."""
    sources = storage.get_worst_sources(n=n, min_signals=5)
    if not sources:
        return "Pas assez de donnees (min 5 signaux par source)."
    lines = [f"Bottom {len(sources)} sources par credibility:"]
    for i, s in enumerate(sources, 1):
        lines.append(f"  {i}. {s['name'][:40]} - cred {s['credibility']:.2f} ({s['n_signals']} sig)")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Test credibility ===")
    print(list_top_sources())
    print()
    print(list_worst_sources())
