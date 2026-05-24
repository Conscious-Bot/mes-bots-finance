# DESIGN SYSTEM — HEIMDALL Sentinel (canonique)

Source unique de l'esthétique. Toute carte/vue consomme ces tokens — **zéro style inline ad-hoc**. `render.py` applique, ne réinvente pas.

**Direction** : minimalisme raffiné, observatoire / veille souveraine. Clair, visible, **ça respire**. Le luxe = le vide maîtrisé, pas l'accumulation d'effets.

---

## 1. La règle qui gouverne tout : le modèle en couches

Trois plans de profondeur. Chaque élément appartient à UN plan.

- **Fond** — grain + grille radar subtile, immobile. C'est le champ.
- **Midground** — les cards : mates, posées, hairline. 90 % de l'UI vit ici.
- **Foreground** — 1-2 héros seulement (Sentinel Score, alerte active). Seul plan autorisé à *briller*.

Ce layering justifie le glassmorphism (il faut le fond à flouter) et rend la profondeur crédible.

## 2. La règle du « vivant »

`--live` (bleu électrique), glow et bloom sont réservés aux éléments **vivants** : signal actif, anomalie, IA en cours, Sentinel Score. **Si tout brille, rien ne brille** — c'est le tell amateur. Tout le reste est mat.

## 3. Tokens `:root`

```css
:root {
  /* — Fond (observatoire, jamais noir pur), plans de profondeur — */
  --bg:            #0A0E16;   /* champ, le plus profond */
  --surface:       #121826;   /* cards (midground) */
  --surface-hi:    #1A2234;   /* héros (foreground) */
  --border:        rgba(255,255,255,.07);   /* hairline, jamais lourd */

  /* — Encre (hiérarchie texte) — */
  --ink:      #E8ECF4;   /* primaire */
  --ink-dim:  #99A3B8;   /* secondaire */
  --ink-faint:#5C6678;   /* tertiaire */

  /* — Accents sémantiques — */
  --live:     #3D8BFF;   /* bleu électrique : VIVANT uniquement */
  --gold:     #C9A86A;   /* or pâle : highlight premium statique */
  --titanium: #B8C0CC;   /* métal neutre, discret */
  --up:       #3FB984;   /* P&L + */
  --down:     #E5654B;   /* P&L - */
  --warn:     #E0A33A;   /* vigilance */

  /* — Rayon (angles arrondis) — */
  --r-sm: 8px;  --r: 12px;  --r-lg: 16px;  --r-pill: 999px;

  /* — Spacing (base 8, généreux) — */
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --s7:48px; --s8:64px;

  /* — Échelle typo (ratio ~1.25), canonique — */
  --t-caption:12px; --t-body:14px; --t-base:16px;
  --t-h3:20px; --t-h2:28px; --t-h1:40px; --t-hero:56px;

  /* — Polices — */
  --font-mark: "Orbitron", sans-serif;              /* WORDMARK uniquement */
  --font-ui:   "Satoshi", "Inter", system-ui, sans-serif;  /* tout le reste */
  --font-num:  "Geist Mono", "IBM Plex Mono", monospace;   /* chiffres/tickers, tabular */

  /* — Effets (sous discipline §1-2) — */
  --grain:     .035;   /* opacité grain dark ; light = .018 max */
  --glow:      0 0 24px rgba(61,139,255,.35);   /* VIVANT only */
  --shadow:    0 8px 30px -14px rgba(0,0,0,.55); /* doux, froid, bas */
  --glass-blur: 14px;  /* héros only, au-dessus du grain/radar */
  --ease: cubic-bezier(.22,.61,.36,1);   /* sortie naturelle */
}
```


## 4. Typographie (hiérarchie canonique)

| Niveau | Token | Police | Poids |
|---|---|---|---|
| Wordmark | — | `--font-mark` | 600 |
| Titre section (H1/H2) | `--t-h1` / `--t-h2` | `--font-ui` | **700** |
| Sous-section (H3) | `--t-h3` | `--font-ui` | 600 |
| Corps | `--t-base` / `--t-body` | `--font-ui` | 450-500 |
| Secondaire | `--t-caption` | `--font-ui` | 450, `--ink-dim` |
| Chiffres / tickers | — | `--font-num` | 500, `tabular-nums` |

Règles : titres importants = +poids **et** +contraste ; secondaires = plus petits **et** atténués en couleur (pas que la taille). **Orbitron jamais hors wordmark** (largeur + faible hauteur d'x → date + illisible en titres FR). Chiffres en mono tabulaire → colonnes alignées, sensation instrument.

Wordmark : `HEIMDALL` en `--font-mark`, `Sentinel` en `--font-ui` 500 lettres espacées (caps), top-left.

## 5. Cards & effets (sous discipline §1-2)

- Rayon `--r-lg` (16px), padding `--s5`+ (généreux), bordure `--border` hairline. **Pas** de bordure marquée.
- Profondeur : `--shadow` doux OU inner-glow léger — **jamais les deux** sur la même carte.
- Glassmorphism (`backdrop-filter: blur(var(--glass-blur))` + surface @70 %) : **1-2 cards héros seulement**, posées sur le grain/radar.
- Gradients : froids, dans ~8 % de variation de luminosité, sur headers / barres de progression uniquement.
- Glow / bloom : `--glow`, **vivant uniquement**.
- Hover : `translateY(-2px)` + bord qui s'éclaircit ; glow réservé au vivant.

## 6. Grain & light mode

Grain : overlay SVG turbulence, `opacity: var(--grain)`. **Light mode : .018 max** + vérifier le contraste texte (le grain sur fond clair mange la lisibilité). Light tokens : `--bg:#F4F6FB; --surface:#FFFFFF; --surface-hi:#FFFFFF; --border:rgba(10,14,22,.08); --ink:#0E1422; --ink-dim:#51607A; --ink-faint:#8A94A8;` accents identiques.

## 7. Motion (un seul moment orchestré)

- **Chargement** : reveal en cascade (`animation-delay` échelonné, `--ease`), une fois. C'est LE moment.
- **Ambiant** : un sweep radar lent en fond (géométrie dérivée du rune ᚺ), ~8-12 s/tour, quasi-invisible.
- Pas de pile d'animations. 60 fps, courbes `--ease`. Le micro-pulse `--live` est la seule micro-interaction (sur le vivant).

## 8. Icônes & langue

- Icônes : **Lucide, stroke 1.5px**, cohérentes partout. Jamais remplies.
- Langue : **français canonique** sur toute string UI (labels, sections, tooltips, états).

---

## Identité ᚺ (le rare)

Le rune devient géométrie UX : son angle = la forme du sweep radar et du loading state. Dosé — pas « chaque séparateur est un rune ». Logo et dashboard = même système nerveux (mêmes angles, arcs, rythmes).
