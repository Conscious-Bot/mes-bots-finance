# Terminologie canonique — bias_events (français)

> Triage #16 31/05 close-session. Réconciliation avec [[glossaire-canonique]] memory (5 axes portefeuille) + charte §6 (français impersonnel, no anglicismes).

## Principe

**DB et code interne** : valeurs anglaises lowercase_snake (convention SQL universelle, matching pattern existant `outcome IN ('correct','incorrect','neutral')`).

**Toute surface user-facing** (dashboard label, Telegram reply, /resisted command output) : **français impersonnel**, via mapping ci-dessous. JAMAIS de label anglais brut affiché à l'user.

## Mapping enum `bias`

| Valeur DB | Label dashboard | Description courte |
|---|---|---|
| `lock_in` | **Verrouillage** | Verrouille un gain trop tôt (winner vendu prématurément). Biais #1 mécanisé. |
| `fomo_greed` | **Peur / cupidité** | Achat sur momentum, vente sur panique. Biais #2 dormant (cf [[presage-biais-1-only]]). |
| `other` | **Autre** | Biais cognitif non-canonique (sunk cost, recency, etc.) |

## Mapping enum `action`

| Valeur DB | Label dashboard | Description |
|---|---|---|
| `acted_on_bias` | **A cédé** | Le biais a piloté la décision |
| `resisted` | **A résisté** | La discipline a tenu, donnée la plus précieuse |

## Mapping enum `status`

| Valeur DB | Label dashboard | Description |
|---|---|---|
| `open` | **En attente** | Événement créé, résolution future |
| `resolved` | **Résolu** | Coût-de-biais calculé |
| `void` | **Annulé** | Marquage manuel (erreur de capture, doublon) |
| `thesis_invalidated` | **Thèse invalidée** | Thèse fermée avant resolve_at → référentiel parti |
| `reentered` | **Re-position** | User a re-pris la position → contrefactuel cassé |
| `missing_data` | **Données manquantes** | Prix au resolve indisponible. JAMAIS default silencieux. |

## Mapping enum `source`

| Valeur DB | Label dashboard | Description |
|---|---|---|
| `auto_detected` | **Détecté auto** | bias_tagger ou règle d'inférence |
| `telegram_tap` | **/resisted** | Un tap Telegram (auto-déclaré) |
| `manual` | **Saisi à la main** | Insert manuel (rare, audit) |

## Termes du panneau discipline (Pile 1.1)

| Terme spec | Label dashboard canonique | Justification |
|---|---|---|
| Cost of bias | **Coût-de-biais** | Standard, factuel |
| Counterfactual | **Contrefactuel** | Universel (épistémo, pas anglicisme) |
| Anchor | **Ancre** | Direct, prix-ancre |
| Path taken / avoided | **Chemin pris / chemin évité** | Standard décision |
| Resolution | **Résolution** | OK universel, technique |
| Horizon | **Horizon** | OK universel |
| Reliability diagram | **Courbe de fiabilité** | "Courbe" plus français que "diagramme" pour ce contexte |
| Bias | **Biais** | Direct |
| Discipline | **Discipline** | Direct, contraste explicite avec biais |

## Alignement avec glossaire canonique (5 axes portefeuille)

Le glossaire canonique [[glossaire-canonique]] couvre les **axes portefeuille** (Solidité / Pari / Doublon / Santé / Calibrage). Le module bias_events couvre une **dimension orthogonale** (méta-mesure du comportement). **Pas de conflit terminologique direct** — domaines distincts.

Lien d'analogie subtil :
- Glossaire "Calibrage" (ma taille colle à ma conviction ?) → axe portefeuille
- Track record / coût-de-biais → axe méta (ma conviction est-elle juste ? ma discipline tient-elle ?)

Les deux peuvent coexister sans collision.

## Notes structurées du `note_tags_json` (français)

```json
{
  "trigger": "rappel_discipline|alerte_telegram|spontane|autre",
  "ce_qui_m_a_tire": ["graphe_fomo", "peur_macro", "fil_twitter", "fragilite_these"],
  "ce_qui_m_a_retenu": ["regle:calibrage_c4", "memoire_biais_passe", "note_friction_md"]
}
```

**Tag enum strict** (max ~6 valeurs / champ), français impersonnel, jamais verbatim libre.

## Verdict

- **Track record refonte** : aucune divergence critique avec glossaire. Pas de modif requise.
- **bias_events DB schema** : valeurs anglaises lowercase_snake conservées (commit `6d3a487`). Pas de modif requise.
- **Future Pile 1.1 panneau discipline + handler `/resisted`** : utiliser le mapping ci-dessus pour TOUS labels user-facing.

Triage close (< 30 min). #16 sort du chemin critique : pas de blocage sur build #20.
