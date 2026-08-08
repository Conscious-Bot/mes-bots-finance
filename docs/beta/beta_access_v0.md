# Beta Access v0 — portail privé STATIQUE (spec, 09/08/2026)

> ⚠ **STATUT : READY ≠ WARRANTED — NON DÉPLOYÉ.** Décision finale du gérant
> (09/08, gravée au registre ZERO_TO_BOOK) : le premier cobaye reçoit un
> book.html par email, PAS ce portail. Cette spec est une hypothèse prête,
> activable UNIQUEMENT sur observation utilisateur (A demande spontanément un
> lieu persistant/une mise à jour — P-BETA-3). Un dry-run technique ne vaut
> pas validation produit. Ne pas déployer par envie de rendre PRESAGE plus réel.
>
> Principe directeur (le jour où l'observation l'active) : le portail est un
> LIEU, pas une application. Toute l'intelligence reste concierge ; le serveur
> ne fait que servir des fichiers. Budget build : ≤1 j.

## Architecture — statique-token, zéro code applicatif exposé

```
Mac (source de vérité)                    VM Hetzner (déjà existante)
beta/<prenom>/                            /srv/presage-beta/
├── original/      (immutable)              └── p/
├── portfolio.csv          rsync                ├── <token-A>/index.html
├── theses.json      ──────────────▶            ├── <token-B>/index.html
├── book.html   (= le portail)                  └── <token-C>/index.html
└── friction_log.md                … + Caddy : HTTPS auto, access logs
```

- **Aucune base de données sur le serveur.** Le serveur détient des RENDUS,
  jamais de données primaires (originaux, thèses, logs de friction restent
  sur le Mac). Serveur compromis = des HTML fuient, pas des fixtures.
- **Token = nom de dossier** : 32+ chars aléatoires (`secrets.token_urlsafe(24)`),
  non listable (Caddy : pas d'autoindex), révocation = `rm -r` du dossier,
  rotation = nouveau dossier + email.
- **Mise à jour** = régénérer book.html (concierge) + rsync. L'URL ne change
  jamais : A revient demain, c'est à jour. Le « living book » est vivant par
  la main, invisible pour lui — exactement le rideau du protocole.
- **Backup/restore** : le serveur est JETABLE (tout est régénérable depuis
  beta/ local + le tool). Restore testé = re-rsync, 30 secondes.
- **Observabilité** = access logs Caddy (IP anonymisable, path, timestamp).
  La métrique du pari (≥3 visites spontanées/30 j) se lit dans les logs —
  visites ≤48 h après un email de refresh comptées à part (relances).
- **HTTPS** : Caddy + Let's Encrypt, automatique.

## Ce que voit A

`https://<domaine>/p/<token>/` → son book : header overview (total, positions,
n thèses, n INDÉFINI, verdicts 🟢🟠🔴 agrégés, next facts datés) + ses Position
Cards V3.1, les mêmes qu'aujourd'hui. En pied de page : une ligne privacy
(« vos données : ce rendu, hébergé en Allemagne (Hetzner), supprimé sur simple
demande ») + le disclaimer non-conseil existant.

## Ce qui N'EXISTE PAS en v0 (frontière dure)

Auth/login (le token EST l'accès) · comptes · base multi-tenant · upload web ·
édition · admin web (la commande `build_book.py` + rsync EST l'admin) ·
notifications · analytics au-delà des logs · API. Toute envie d'en ajouter
un = friction log, ×3 avant conception (règle du protocole).

## Build (≤1 journée, dans l'ordre)

1. **Tool** : étendre `build_book.py` — header overview (total, counts
   verdicts, next facts triés) au-dessus des cartes. ~1 h, testable en local.
2. **VM** : installer Caddy (ou réutiliser s'il y est), un `Caddyfile` de
   6 lignes (root, HTTPS, logs, pas d'index). ~1 h.
3. **Domaine** : au choix d'Olivier — un sous-domaine d'un domaine existant
   ou un domaine neuf (~10 €/an). DNS → VM. ~30 min + propagation.
4. **Publication** : `scripts` une ligne rsync par user. Test de bout en
   bout avec le book fictif du dry-run AVANT tout cobaye réel. ~30 min.
5. **Révocation testée** (rm + 404) et **restore testé** (re-rsync). ~15 min.

## Ce que ça préserve du protocole

Tout le reste est INCHANGÉ : email d'entrée, fichier original immutable,
interview, restitution-avant-structure, chronométrage, friction log, débrief
différé, jamais de correction en séance, K/I/S/A, fixtures. Le portail ne
change que la RESTITUTION (URL au lieu de pièce jointe) et le pari 3
(usage au lieu de pull). La clause d'irréversibilité reprend effet à la
publication de cette spec : prochain arrêt, les logs d'A.
