# DESIGN SYSTEM — PRESAGE (canonique)

> Source unique. Toute carte/vue/composant consomme ces tokens. **Zéro style inline ad-hoc.** `render.py` applique, ne réinvente pas. Charte alignée sur le brand 28/05/2026 (palette parchemin warm + Geist), enrichie avec font-size tokens + états canoniques + ergonomie.

**Direction** : observatoire de veille souveraine. Densité honnête, signal-subtil. Le carré (Bloomberg-dense, Linear-clean) vaut plus que l'attrayant. Pour un pro : *clarté + densité = attrait*. L'amateur empile les effets ; le pro pose l'info.

**Principe-roi** : *Couleur = fait. Jamais jugement.* La sémantique (danger/warn/calm) vient du **gradient sous-jacent** ou du **tag séparé**, pas du marker.

---

## 1. Tokens canoniques

### 1.1 Palette parchemin (default) — `:root`

```css
--bg:    #F9F6F3;   /* fond, papier warm */
--panel: #F9F6F3;   /* cards (flat, pas d'élévation chromatique) */
--ink:   #1A1814;   /* encre primaire warm-black */
--ink2:  #3A352D;   /* encre secondaire */
--steel: #7E7770;   /* texte tertiaire (caption, mono dim) */
--line:  #E5E0DB;   /* hairline standard */
--line2: #CFC7BF;   /* hairline marquée (séparateurs) */
--line3: #B5ABA0;   /* bordure marquée (focus, outline TOP) */

/* Accents print-grade */
--acc:   #5F9A4D;   /* vert olive (positif, bullish) */
--acc2:  #5F9A4D;   /* alias --acc */
--bear:  #C24332;   /* oxblood (négatif, bearish) */
--warn:  #C8862F;   /* ochre (vigilance) */
--gold:  #D4A040;   /* OR — réservé strict, 1 spark / viewport max */
--id:    #1A1814;   /* identité (= ink) */
```

### 1.2 Palette midnight (`body.midnight`)

```css
--bg:    #0E0D0B;   /* warm noir, jamais bleu */
--panel: #16140F;
--ink:   #F1ECE3;   /* ivoire sur noir */
--ink2:  #CFC6B5;
--steel: #8C8273;
--line:  #2A2520;   --line2: #3D362E;   --line3: #5A5046;
/* Accents adoucis pour le contraste sur fond noir */
--acc: #9DC07F;   --bear: #DD6655;   --warn: #E5B05D;   --gold: #E0B85A;
```

### 1.3 Spacing (base 4, généreux)

```css
--s1:4px; --s15:6px; --s2:8px; --s25:10px; --s3:12px;
--s35:16px; --s4:20px; --s5:32px; --s6:52px;
```

Padding card standard : `--s4` ou `--s5`. Gap entre rows : `--s2` à `--s35`. Section spacing : `--s5` à `--s6`.

### 1.4 Typographie tokens (NOUVEAUX — à ajouter en CSS)

```css
/* Échelle ratio ~1.2, base 14px */
--t-caption: 12px;   /* labels secondaires, axe */
--t-body:    14px;   /* corps standard (DEFAULT) */
--t-base:    15px;   /* corps lisibilité ++ */
--t-h3:      18px;   /* titre de block (colhead) */
--t-h2:      24px;   /* titre de section (phead) */
--t-h1:      32px;   /* titre de page */
--t-hero:    44px;   /* hero number (KPI principal) */
```

**Important** : aujourd'hui plein de `font-size: 10px / 11px / 13px` inline. À migrer progressivement vers ces tokens. **Toute nouvelle écriture utilise les tokens.**

### 1.5 Rayon + ombre

```css
--r-sm: 4px;  --r: 6px;  --r-lg: 10px;  --r-pill: 999px;
--elev: none;            /* PAS de box-shadow par défaut */
--ease: cubic-bezier(.22,.61,.36,1);
```

Cards = border 1px hairline `--line`. **Jamais de drop-shadow.** Élévation = contraste de bordure (`--line2` / `--line3`), pas d'effet d'ombre.

---

## 2. Polices

| Usage | Police | Poids | Token |
|---|---|---|---|
| Wordmark PRESAGE | Geist | 200 (hairline) | `--font-mark` |
| Tout texte UI | Geist | 400-500 (corps), 600 (titres) | `--font-ui` |
| Chiffres / tickers | Geist Mono `tabular-nums` | 500 | `--font-num` |

Règles :
- **Pas d'Orbitron** (ancien doc). Geist couvre tout.
- Chiffres = TOUJOURS `--font-num` + `tabular-nums` (colonnes qui s'alignent).
- Titres : +poids ET +contraste (pas que la taille). Secondaires : +petits ET `--steel` (pas que la taille).

---

## 3. Composants canoniques

### 3.1 Card

```html
<div class="card pad">…</div>
```

Padding `--s4`/`--s5`, border 1px `--line`, `border-radius: --r-lg`, `--bg`/`--panel` fond, **pas d'ombre**. Hover : aucun effet sauf si action cliquable (translateY -1px + border `--line2`).

### 3.2 Axis + needle (CANONIQUE)

Pattern unique pour TOUTE barre de progression / position dans une plage :

```html
<div class="axis">
  <div class="axis-mark" style="left:42.3%"
       title="42.3% (valeur exacte au hover)"></div>
</div>
```

**Règles dures** :
- `.axis-mark` = needle 4-points losange concave, **noir (light) / blanc (midnight) PARTOUT**. Pas de variante sémantique colorée par défaut.
- L'info danger/safe passe par le **gradient sous-jacent** de `.axis` (red→neutral→green selon le sens) ou par un **tag séparé**, pas par la couleur du needle.
- **`title="X.X%"` OBLIGATOIRE** = valeur exacte au hover. Toutes les barres doivent répondre à "quelle est la valeur exacte ?" instantanément.

Cf [[needle-canonical]] memory pour l'arc d'itération.

### 3.3 Horizontal bars list (proportions)

Pour TOUTE viz de répartition / part / concentration : **horizontal bars list**, JAMAIS donut/camembert/radial.

```
[dot color] [label]  [───── fill proportionnel ─────]  [%.X%]  [valeur]
```

Trié desc par valeur. Bar height fine (4px), `border-radius: 2px`. Cf [[viz-horizontal-bars]] memory.

### 3.4 Ticker badge

```html
<span class="tk tkc" data-tk="AAPL">AAPL</span>
```

`tabular-nums`, padding `--s1 --s15`, border `--line`, `--font-num`. Click ouvre drill ticker (data-tk).

### 3.5 Tags sémantiques (couleur = fait, pas jugement)

```html
<span class="tag acc">+5.2%</span>     <!-- gain mesuré -->
<span class="tag bear">-3.8%</span>    <!-- perte mesurée -->
<span class="tag warn">stale 14j</span><!-- état dégradé factuel -->
<span class="tag calm">live</span>     <!-- état sain factuel -->
```

Pas de tag rouge "AVERTISSEMENT" ou vert "BIEN". Toujours une donnée mesurée derrière.

---

## 4. États canoniques (zéro état cassé)

Tout composant qui charge ou agrège des données DOIT designer 4 états :

| État | HTML | Style | Quand |
|---|---|---|---|
| **Loading** | `<div class="loading">…</div>` | skeleton shimmer mat 200ms, pas spinner | requête en vol |
| **Vide** | `<div class="empty">aucun X sur Y</div>` | `--steel`, padding `--s4`, texte précis (pas "no data") | requête OK, résultat vide |
| **Stale** | `<span class="tag warn">stale Xh</span>` + valeur grise | tag explicite à côté de la valeur (pas écran rouge) | cache > TTL ou source dégradée |
| **Erreur** | `<div class="empty">Requête à ajuster <span class="mono">TypeName: msg</span></div>` | mono pour le type, message court | exception caught |

**Règle absolue** : jamais un état blanc / "—" / vide sans label. Toujours dire ce qu'on attendait + ce qui s'est passé.

---

## 5. Ergonomie (precisions partout)

### 5.1 Tooltip valeur exacte au hover

Toute info numérique compressée (barre, jauge, badge) DOIT exposer la valeur exacte via `title="X.XX"`. Le user qui survole sait précisément, le user qui survole pas voit la forme.

### 5.2 Descriptions complètes, pas tronquées avec "..."

Bannir les `text[:N] + "..."` pour les descriptions d'entreprise / signaux / theses dans les vues de DÉTAIL. La troncature reste OK pour les LISTES denses (résumé en row) — mais le détail doit être complet.

### 5.3 Navigation clavier

- `Tab` cycle les éléments interactifs (cards, ticker badges, boutons).
- `Enter` active l'élément focalisé.
- `Esc` ferme les overlays / drills.
- `focus-visible` : outline `--line3`, jamais effet glow.

### 5.4 Single reading model

Une métaphore visuelle par axe, appliquée partout. Exemple : axe stop→cible avec needle à la position du prix = même grammaire pour "proche cible" et "proche stop", lue une fois, valable deux fois.

---

## 6. Voice / copy (français canonique)

- **Français impersonnel** (no tutoiement, no anglicismes : "haut rendement" pas "junk bonds", "largeur du marché" pas "breadth").
- **Impératif sec** ("laisser courir", "tenir le cap"), pas coach-bro ("execute ton plan").
- **Densité par signes typographiques** : `marge < 12%` plutôt que "moins de 12% de marge".
- **Termes canoniques** : "Première ligne" / "En gain" / "Marges faibles" / "Dérogation" / "Non-action documentée".

Cf glossaire 5 axes ([[glossaire-canonique]]) pour les axes user-facing : Solidité / Pari / Doublon / Santé / Calibrage + notes Construction / Fragilité.

---

## 7. Règles d'or (anti-amateur, anti-AI-generic)

1. **Zéro style inline ad-hoc** au-delà de positionnement strict (`left:X%` ok ; `font-size:10px` non — utiliser tokens).
2. **Couleur = fait, jamais jugement.** Le marker reste neutre, la sémantique vient du gradient/tag.
3. **Un seul élément vivant** par viewport (or `--gold` ou anim subtle). Si tout brille, rien ne brille.
4. **Pas de drop-shadow.** Élévation = bordure, pas effet.
5. **Pas de donut/camembert.** Horizontal bars list pour proportions.
6. **Pas d'Orbitron / sans-serif déco.** Geist couvre tout.
7. **Valeur exacte au hover** sur tout chiffre compressé.
8. **Densité honnête > vernis.** Bloomberg-dense, Linear-clean.
9. **Toujours en français impersonnel canonique.**
10. **Chaque état designé.** Loading / vide / stale / erreur. Jamais un blanc anonyme.
11. **Un seul modèle de lecture partout.** L'axe stop→target (needle + gradient) est l'unique grammaire visuelle pour position dans une plage — lue une fois, valide partout (positions, prédictions, calibration, marges). Pas de métaphore secondaire pour le même concept.
12. **États honnêtes-tôt.** Quand N est trop petit pour conclure, l'AVOUER explicitement (`INSUFFISANT — N<10 pour conclure`) plutôt que d'afficher un chiffre nu qui prétend tenir. L'aveu vaut mieux qu'une fausse précision. Cf `_track_record_panel()` : Wilson IC + verdict-d'attente cohabitent, le verdict s'active quand le seuil tombe.
13. **Self-evident : chaque élément libellé.** Pas de "100°" nu, pas de point coloré sans tooltip, pas de barre sans légende sous ou au hover. Un user qui regarde le widget pour la première fois doit comprendre ce qu'il représente sans lire un guide.
14. **Accordéons : clic seulement, jamais hover.** Le hover dans une page dense déclenche des ouvertures intempestives quand le pointeur traverse l'UI. Le clic = intention explicite. CSS canonique : `.foo.open .bar { … }` (jamais `.foo:hover .bar`). Le click handler JS toggle la classe `.open` sur le parent.

---

## 8. Process

- Modification d'un token → coordonner light + midnight (jamais l'un sans l'autre).
- Nouveau composant → vérifier qu'il consomme tokens + respecte règles d'or AVANT merge.
- Audit régulier : `grep "style=\"font-size:" dashboard/render.py` doit décroître. Idem `background:` (sauf gradients axis), `color:` (sauf `var(--…)`).
- Refonte structurelle → tag git `pre-{topic}-{YYYYMMDD}` AVANT (rollback safety).

## 9. Références

- Memory [[presage-brand]] : brand identity 28/05 (parchemin + Geist + DNA signal-subtil)
- Memory [[needle-canonical]] : axis-mark noir/blanc dur, arc 6 commits
- Memory [[viz-horizontal-bars]] : horizontal bars > donut, arc 5+ commits
- Memory [[glossaire-canonique]] : 5 axes user-facing
- ADR-001 : PIT bitemporal credibility ledger
- ADR-003 : Portfolio targets PIT multi-account
