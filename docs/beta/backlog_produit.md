# Backlog produit — capacités d'analyse (capturé 09/08, write-don't-build)

> Demande gérant : cycle par titre · prix vs ATH/1an · timing trim/bump vs
> consensus · sizing intelligent · targets proposés. TRIÉE en 5 statuts.
> Déclenchement : demandé par cobayes (×2 candidat, ×3 conception) OU validé
> sur le book Olivier d'abord.

| capacité | statut | note |
|---|---|---|
| prix vs ATH / vs 1 an / percentile historique | **FAISABLE-FACTUEL** | trivial (yfinance), contexte pur, conforme. Ajoutable au book Olivier dès maintenant (price_history 1316 j) |
| analyse de cycle par titre | **EXIGE MÉTHODOLOGIE** | sans méthode définie = « analytique pour impressionner » (retiré de la remise A pour ça). Méthode candidate : percentile distribution LT + proxies sectoriels — à spécifier AVANT d'afficher |
| sizing intelligent (conviction-normalisé) | **EXISTE** (steer engine, caps, binding) | généralisable à un tiers SI il déclare ses convictions — sinon non calculable (fail-honest) |
| targets proposés | **CONTREDIT LA DOCTRINE** en l'absence de thèse | les cibles découlent des thèses, jamais l'inverse. Proposer des targets sans thèse = fabriquer des nombres |
| « bon moment de trim/bump » (timing) | **CONTREDIT LA DOCTRINE + RÉGLEMENTAIRE** | (a) le tribunal SOX a montré que notre lecture de cycle était ~60e percentile d'un random walk — on ne vend pas aux autres ce qu'on s'interdit ; (b) pour un TIERS : trim/bump/targets personnalisés = conseil en investissement (MiFID/CIF) — statut requis avant le premier euro |
| vs consensus | **EXIGE DATA PROVIDER** | consensus analystes = donnée payante ; sans elle, on improvise |
