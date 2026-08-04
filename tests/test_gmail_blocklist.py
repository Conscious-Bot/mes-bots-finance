"""Kill-list sources côté ingestion (audit 03/08, semaine de gel).

Les 8 sources à 0-25% de signal matériel sur 30j sont bloquées dans validate()
via le mécanisme noise existant. Hedgeye et The Defiant NE sont PAS bloquées
(interrupteurs ①/② en attente de décision explicite) — verrouillé ici.
"""
import pytest

from data_sources.gmail_ import _BLOCKED_SENDERS, _is_blocked_sender


@pytest.mark.parametrize(
    "from_addr",
    [
        "hello@moby.co",
        "Moby <hello@moby.co>",                                # format 'Nom <addr>'
        "Snowball - Yoann <yoann@media.snowball.xyz>",
        "The Substack Post <post+the-weekender@substack.com>",
        "All In Podcast LLC <info@allin.com>",
        "Unusual Whales Newsletter <unusualwhales@substack.com>",
        "MONEYRADARCRYPTO@SUBSTACK.COM",                       # casse ignorée
        "Hedgeye <hedgeye@hedgeye.com>",                       # ① tranché 04/08 : tué
        "Keith McCullough <hedgeye@hedgeye.com>",              # même adresse
        "The Defiant <no-reply@mail.thedefiant.io>",           # ② tranché 04/08 : tué
    ],
)
def test_blocked_senders_are_blocked(from_addr):
    assert _is_blocked_sender(from_addr)


@pytest.mark.parametrize(
    "from_addr",
    [
        "Torsten Slok <agm@apollo.com>",                # source à haute valeur
        "Matt Levine <noreply@news.bloomberg.com>",
        "Ben Thompson <email@stratechery.com>",
        "",                                             # vide = pas bloqué
    ],
)
def test_valuable_sources_pass(from_addr):
    assert not _is_blocked_sender(from_addr)


def test_blocklist_is_exactly_the_decided_ten():
    """Verrou : la liste ne grossit pas sans passer par ce test (décision consciente).
    8 (audit 03/08) + Hedgeye + The Defiant (interrupteurs ①② tranchés 04/08)."""
    assert len(_BLOCKED_SENDERS) == 10
