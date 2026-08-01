# PRESAGE — REGISTRE DES HYPOTHÈSES (v1, 01/08/2026)

> La couche que les systèmes sophistiqués oublient : les **hypothèses implicites**
> sur lesquelles reposent règles et politiques. Une règle fausse se voit ; une
> hypothèse fausse détruit silencieusement toutes les règles qui en dépendent.
>
> Chaque hypothèse porte : identifiant · énoncé · domaine de validité · modules
> dépendants · **falsifieur** · conduite si elle échoue · **statut**.
> Statuts : `TENUE` · `SOUS TENSION` · `PARTIELLEMENT FALSIFIÉE` · `FALSIFIÉE`.
>
> Revue : trimestrielle, ET à chaque incident (un incident non expliqué par une
> règle est presque toujours une hypothèse qui a lâché).

---

## H-MARCHÉ

### H1 — Les corrélations observées restent un proxy utile du futur
- **Domaine** : régimes ordinaires. **Exclut** les épisodes de dé-levier forcé.
- **Dépendants** : `d_corrélation` de l'Allocation Solver · caps facteur · notion de ballast.
- **Falsifieur** : ≥3 « décorrélateurs » déclarés perdant simultanément >15 % dans une fenêtre de 10 jours.
- **STATUT : PARTIELLEMENT FALSIFIÉE (juillet 2026)** — dans l'unwind, la quasi-totalité du book a corrélé à 1 ; les décorrélations affichées se sont révélées conditionnelles (cf « faux décorrélateur »).
- **Conduite** : ne jamais compter sur la décorrélation *pendant* un choc de liquidité ; le ballast se juge sur la nature du cash-flow (contracté), pas sur une corrélation historique.

### H2 — Les marchés restent liquides aux tailles pratiquées
- **Domaine** : lignes cotées, tickets ≤ quelques k€.
- **Dépendants** : exécution des trims · échelle de drawdown · plafond de poche illiquide.
- **Falsifieur** : spread > 1 % ou impossibilité d'exécuter un ticket de 1 k€ en une séance.
- **STATUT : TENUE** — mais note d'humilité : la *classification* de liquidité a déjà été fausse (SPCX supposée illiquide, en réalité méga-cap ultra-liquide). L'erreur portait sur la donnée, pas sur l'hypothèse.
- **Conduite** : reclasser, ne jamais dimensionner sur une liquidité supposée sans l'avoir vérifiée.

### H3 — Le porteur peut tenir ses positions sans être forcé de vendre
- **Domaine** : absence de levier, absence d'appel de marge, besoins de liquidité couverts hors book.
- **Dépendants** : horizon long · thèses pluriannuelles · tolérance au drawdown · backstop.
- **Falsifieur** : toute vente motivée par un besoin de cash externe au book.
- **STATUT : SOUS TENSION** — non vérifiable : la couche vie est vide (besoins datés inconnus).
- **Conduite** : tant que `life.dated_liquidity_needs` est MISSING, considérer l'horizon comme non prouvé et ne pas maximiser l'illiquidité.

### H4 — Les publications d'entreprise sont suffisamment fiables
- **Domaine** : émetteurs cotés sur marchés régulés, comptes audités.
- **Dépendants** : hiérarchie d'évidence (niveau L1) · §XI · tous les triggers chiffrés.
- **Falsifieur** : fraude avérée, retraitement majeur, démission de l'auditeur sur une ligne détenue.
- **STATUT : TENUE** — c'est le risque **idiosyncratique** (Enron/Wirecard/Luckin) que la gestion en drivers rend invisible.
- **Conduite** : maintenir la couche résiduelle explicite ; plafond par ligne pour que la fraude d'un émetteur reste survivable.

## H-DONNÉES

### H5 — Les sources de prix/FX gratuites restent disponibles et exactes
- **Domaine** : fournisseur public, throttling respecté.
- **Dépendants** : valorisation du book · calcul des drawdowns · paliers R1/R2/R3 · dashboard.
- **Falsifieur** : écart >1 % vs le broker sur un contrôle ponctuel, ou indisponibilité >48 h.
- **STATUT : SOUS TENSION** — dépendance mono-source, sans réconciliation systématique avec le broker.
- **Conduite** : fail-closed déjà en place (pas de prix → pas de décision) ; réconciliation périodique à instaurer.

### H6 — Les faits extraits par le pipeline sont attribués au bon fait, à la bonne date
- **Domaine** : sources textuelles.
- **Dépendants** : digest · scoring · déclenchement mécanique des urgents.
- **Falsifieur** : ≥1 fait de plus de 30 jours présenté dans une fenêtre 24 h (déjà arrivé 2×) ; causalité inversée (déjà arrivé 1×).
- **STATUT : PARTIELLEMENT FALSIFIÉE** — trois audits l'ont prise en défaut.
- **Conduite** : `date_du_fait` + `evidence_origin` obligatoires ; aucun urgent sur évidence secondaire seule.

### H7 — Répétition ≠ confirmation
- **Énoncé** : plusieurs sources relayant une même dépêche constituent UN fait ; la confirmation exige des **chaînes causales indépendantes** (ex. dépêche + filing + contrat).
- **Dépendants** : anti-écho du digest · pondération de l'évidence.
- **Falsifieur** : un urgent construit sur N sources partageant la même origine.
- **STATUT : SOUS TENSION** — règle écrite (`evidence_origin`), non encore implémentée.

## H-INFRASTRUCTURE

### H8 — Un seul écrivain par store, sur le bon nœud
- **Dépendants** : intégrité du ledger · track record · toute mesure du système.
- **Falsifieur** : une écriture réussie hors du nœud déclaré (L34).
- **STATUT : FALSIFIÉE PUIS CORRIGÉE (30/07)** — 13 transactions correctes écrites sur la réplique, détruites par le sync. L'hypothèse n'était pas écrite, donc invérifiable.
- **Conduite** : topologie gravée (CANONICAL_MAP §11) ; garde `ROLE=replica` à implémenter (mécanique > vigilance).

### H9 — L'infrastructure reste disponible et sauvegardée
- **Dépendants** : crons, digest, monitors, backups offsite.
- **Falsifieur** : service de backup en échec >24 h, ou sync muet >6 h sans alerte.
- **STATUT : SOUS TENSION** — service de sauvegarde offsite actuellement en échec ; un sync a déjà été muet 7 jours sans alerte.
- **Conduite** : tout échec silencieux est un défaut de conception, pas un incident isolé.

## H-HUMAIN

### H10 — Le décideur reste unique, disponible et capable
- **Dépendants** : la totalité du système (décisions, overrides, revues, exécution).
- **Falsifieur** : indisponibilité prolongée · revue trimestrielle sautée · décisions prises sans passer par le cycle.
- **STATUT : SOUS TENSION** — aucun plan de continuité. Personne d'autre ne sait exécuter le système.
- **Conduite** : le handoff méthode est un premier pas ; une procédure de continuité (que faire du book si le décideur est indisponible 6 mois) reste à écrire.

### H11 — Le coût d'attention du système reste inférieur à l'erreur qu'il évite
- **Dépendants** : tout (tribunal 6, parcimonie).
- **Falsifieur** : règles écrites non appliquées · documents non relus depuis >6 mois · digests non lus.
- **STATUT : SOUS TENSION** — ~20 documents de doctrine pour ~22 lignes ; la doctrine croît plus vite que le nombre de décisions.
- **Conduite** : à chaque ajout, se demander ce qu'on supprime. En cas d'égalité, supprimer.

### H12 — Les apports futurs continueront
- **Dépendants** : cliquet descendant du cap facteur (il descend PAR dilution) · construction de la manche démographie · backstop en règle.
- **Falsifieur** : arrêt des apports >6 mois.
- **STATUT : INCONNU** — `life.monthly_contribution_eur` est MISSING. **Le mécanisme central de correction de la concentration repose sur une hypothèse jamais énoncée.**
- **Conduite** : si les apports cessent, le cliquet ne peut plus descendre que par vente — il faut alors soit accepter la concentration, soit amender la règle « jamais de vente forcée ».

## H-MÉTHODE

### H13 — Les probabilités sont estimables avec une erreur acceptable
- **Dépendants** : Allocation Solver (Kelly fractionnaire) · sizing venture · toute future calibration.
- **Falsifieur** : score de Brier ne s'améliorant pas après N≥100 résolutions, ou biais de calibration >20 points persistant.
- **STATUT : NON TESTABLE AUJOURD'HUI** — N insuffisant. C'est précisément pourquoi la fraction de Kelly est à 0,25.
- **Conduite** : la fraction reste basse tant que la calibration est inconnue ; elle ne peut monter que sur preuve empirique.

### H14 — Les triggers pré-enregistrés capturent les vrais modes de rupture
- **Dépendants** : Q1 (thèse intacte ?) · tout le cycle de décision.
- **Falsifieur** : un drawdown majeur sans qu'aucun trigger n'ait fired.
- **STATUT : PARTIELLEMENT FALSIFIÉE (juillet 2026)** — −25 % avec zéro trigger déclenché. Les triggers surveillaient les arbres, l'incendie était la forêt.
- **Conduite** : c'est l'origine de la couche facteur et de l'échelle de drawdown ; les triggers de thèse ne suffisent pas, il faut des rails de portefeuille.

### H15 — Le passé du système informe son futur (le resolver a un sens)
- **Dépendants** : boucle d'apprentissage · scoring des overrides · doctrines L#.
- **Falsifieur** : régime durablement différent rendant les leçons inapplicables.
- **STATUT : TENUE avec réserve** — biais du survivant : les doctrines sont écrites après les incidents, jamais avant.

---

## SYNTHÈSE — CE QUE LE REGISTRE RÉVÈLE IMMÉDIATEMENT

| Statut | Hypothèses |
|---|---|
| **Partiellement falsifiées** | H1 (corrélations), H6 (extraction des faits), H14 (triggers) |
| **Falsifiée puis corrigée** | H8 (single-writer) |
| **Sous tension** | H3, H5, H7, H9, H10, H11 |
| **Inconnue** | H12 (apports — soutient pourtant le mécanisme anti-concentration) |
| **Non testable** | H13 (calibration) |
| **Tenues** | H2, H4, H15 |

**Trois d'entre elles sont structurellement plus graves que n'importe quelle règle du système** : H12 (le cliquet repose sur des apports jamais énoncés), H10 (aucun plan de continuité), H11 (la doctrine croît plus vite que les décisions). Aucune n'était écrite avant aujourd'hui.
