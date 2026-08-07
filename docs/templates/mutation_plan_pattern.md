# Pattern canonique — bloc de mutation PLAN/APPLY (protocole de maintenance des thèses)

> Né le 07/08/2026 (audit cards, dialogue gérant). Toute écriture DB non-triviale
> collée côté Mac instancie ce protocole. Doctrine complète :
> `docs/audit_cards_2026-08-07.md` § mutations de thèse.

## Les cinq propriétés (non négociables)

1. **Taxonomie fermée** — cinq classes autorisées : `correction`, `clarification`,
   `datation`, `photographie` (remplacée, jamais éditée), `remplacement` (trigger
   consommé). La REQUALIFICATION **n'existe pas dans l'outil** (Tribunal seul) :
   un outil qui ne peut pas accomplir une action interdite est supérieur à un
   outil qui rappelle qu'elle l'est.
2. **Orthogonalité** — une mutation = UNE classe. Deux natures = deux mutations
   successives (ex. : remplacement + datation SPCX, 07/08).
3. **PLAN = document auditable, APPLY = opération mécanique** — toute
   l'intelligence vit dans la phase PLAN (résolution des ancrages, construction
   des payloads) ; la branche APPLY ne contient aucune décision, elle matérialise
   des payloads déjà construits et revus.
4. **PLAN-ID = hash de la représentation auditée** — l'identifiant est dérivé du
   TEXTE imprimé que l'humain relit (pas de la structure source). Si le contenu
   change entre lecture et APPLY, le hash diverge et rien ne s'écrit.
5. **Atomicité stricte** — un ancrage en échec = zéro écriture. Une moitié de
   mise à jour est pire qu'aucune (famille : fail-closed, gate digest, [CLOSE]).

## Squelette

```python
APPLY = ""   # 1er passage : vide -> PLAN. 2e passage : APPLY="PLAN-..." et recoller.

import sqlite3, json, hashlib, datetime
cx = sqlite3.connect("data/bot.db")

CLASSES = {
    "correction":    "minimale — rétablit un fait",
    "clarification": "sémantique — même falsifieur, ambiguïté réduite",
    "datation":      "horloge — ajoute une échéance",
    "photographie":  "photo — l'ancienne est archivée (le texte garde « remplace X »)",
    "remplacement":  "MAXIMALE autorisée — consommation d'invalidateur",
}
# REQUALIFICATION : absente à dessein. Tribunal uniquement.

MUTATIONS = [
    # (ticker, classe, raison, ancrage_old | None, texte_new)
    # old=None => append (avec garde anti-doublon)
]
assert all(m[1] in CLASSES for m in MUTATIONS), "classe hors taxonomie fermée"

# ── Phase PLAN : résoudre les ancrages, CONSTRUIRE les payloads ─────────────
fails, staged = [], []
for tk, classe, why, old, new_txt in MUTATIONS:
    row = cx.execute("SELECT id, invalidation_triggers FROM theses "
                     "WHERE ticker=? AND status='active'", (tk,)).fetchone()
    if not row: fails.append(f"{tk}: thèse active introuvable"); continue
    tid, raw = row
    trigs = json.loads(raw or "[]")
    if old is None:
        if any(new_txt[:30] in t for t in trigs):
            fails.append(f"{tk}: append déjà présent"); continue
        trigs.append(new_txt)
    else:
        hits = [i for i, t in enumerate(trigs) if old in t]
        if len(hits) != 1:
            fails.append(f"{tk}: ancrage '{old[:40]}' trouvé {len(hits)}x"); continue
        trigs[hits[0]] = trigs[hits[0]].replace(old, new_txt)
    staged.append((tid, tk, classe, why, old, new_txt,
                   json.dumps(trigs, ensure_ascii=False)))

# ── Représentation AUDITÉE : c'est ELLE qui est hashée ──────────────────────
lines = []
for _, tk, classe, why, old, new_txt, _ in staged:
    lines.append(f"{tk}  [{classe}]  portée: {CLASSES[classe]}")
    lines.append(f"  raison: {why}")
    if old: lines.append(f"  old: {old}")
    lines.append(f"  new: {new_txt}")
plan_text = "\n".join(lines)
plan_id = ("PLAN-" + datetime.date.today().isoformat() + "-"
           + hashlib.sha256(plan_text.encode()).hexdigest()[:8])

print(f"═══ {plan_id} ═══\n{plan_text}")
if fails:
    print("\n⛔ ANCRAGES EN ÉCHEC — rien ne s'écrira :")
    [print("  ", f) for f in fails]
elif APPLY == plan_id:
    # ── Phase APPLY : mécanique pure, AUCUNE décision ici ──
    for tid, *_, payload in staged:
        cx.execute("UPDATE theses SET invalidation_triggers=?, "
                   "last_reviewed=datetime('now') WHERE id=?", (payload, tid))
    cx.commit()
    print(f"\nOK — {plan_id} appliqué : {len(staged)} mutations, identité conservée")
elif APPLY:
    print(f"\n⛔ APPLY ≠ {plan_id} — le contenu a changé depuis ta lecture, rien n'est écrit")
else:
    print(f"\n{len(staged)} mutations prêtes — APPLY=\"{plan_id}\" pour matérialiser")
```

## Adaptation à d'autres stores

Le pattern se transpose à tout store (policy.yaml exclu — L17, un YAML se PR-ise) :
remplacer la résolution d'ancrage (`invalidation_triggers` JSON) par celle du
store cible, conserver les cinq propriétés. Le journal des PLAN-ID appliqués vit
dans l'historique de conversation + git blame de la DB exportée ; si un jour un
journal dédié devient nécessaire, c'est une table append-only (L17) — post-gel.
