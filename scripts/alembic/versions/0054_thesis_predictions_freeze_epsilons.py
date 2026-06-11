"""Cure P0 audit (2) 11/06/2026 — freeze ε constantes À LA POSE (les deux).

DRIFT SURFACE 12 MOIS catchée à l'audit post-livraison du chantier :
- `epsilon_delta_pct` et `epsilon_neutral_pct` hardcodés en 3 sites
  (shared/thesis_alpha.py defaults, shared/thesis_predictions_writer.py
  DEFAULT_EPSILON_DELTA_PCT, bot/jobs/thesis_alpha_resolver.py defaults).
- JAMAIS stockés dans la pose → si on change ε entre pose et résolution
  (12 mois), le verdict est calculé sur une doctrine que les poseurs
  n'avaient pas en tête. Pollution silencieuse du track-record.

Cure cohérente avec SPEC §0 décision B « Freeze PT à asof, pas live
update ». Les ε ont la même fonction structurale que le PT : cible
figée pour mesure. Le poseur accepte une doctrine ε au moment de la
pose ; la classification au resolve doit utiliser CETTE doctrine, pas
celle qui sera live à t+12m.

🔴 FREEZE-POINT CRITIQUE : les DEUX ε sont stockés AT_POSE, pas at_resolve.
   Stocker at_resolve enregistre le drift au lieu de l'empêcher (red-team
   Olivier 11/06 soir : « ça documente le mensonge, pas l'empêche »).
   Le resolver LIT les ε figés dans la pose, jamais les defaults code live.

Architecture :
- `epsilon_delta_pct_at_pose REAL`   : ε pour le gate no_bet à la pose
  (stocké INSERT, figé immuable trigger 1 ensuite).
- `epsilon_neutral_pct_at_pose REAL` : ε pour la zone neutral au resolve
  (stocké INSERT, figé immuable trigger 1, LU par le resolver à t+12m).

Backfill in-migration des poses pre-0054 (SK ID 1 + CCJ ID 2 posées dans
cette même session sous ε=1.0, doctrine juin 2026) : UPDATE entre ADD
COLUMN et DROP/CREATE trigger 1 (trigger ne protège pas encore les
nouvelles cols à ce moment). Toutes les poses ont leurs ε stockés
post-migration ; le resolver garde néanmoins un fallback loggé défensif
(`thesis_resolve_legacy_epsilon_fallback`) pour le cas pathologique où
un futur pred apparaîtrait avec ε NULL — pas un mensonge silencieux mais
une traçabilité explicite à auditer.

Pattern ADD COLUMN + UPDATE backfill + DROP/CREATE trigger 1 :
- ADD COLUMN = O(1) métadonnée, NULL pour rows existantes
- UPDATE backfill = SK + CCJ → ε=1.0 (doctrine connue de la session juin 2026)
- DROP+CREATE trigger 1 (pose_writeonce) ÉTEND la liste UPDATE OF aux 2
  nouvelles colonnes pour les figer immuables ensuite (sinon mutable
  post-pose → bug schéma identique à 0053 sur resolution_status)
- Trigger 2 (resolve_writeonce) INCHANGÉ : ε sont pose-side, pas resolve-side

Downgrade STRICT :
1. Garde Python : refuse si lignes avec ε non-NULL existent (perte interdite
   = perte de la doctrine figée, donc perte de reproductibilité 12m)
2. DROP TRIGGER 1 (libère référence sur les colonnes)
3. DROP COLUMNS (les 2)
4. CREATE TRIGGER 1 étroit (état 0053 : sans ε)
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ADD COLUMNS — ε figés à la POSE (les deux, freeze-point unique)
    op.execute("""
        ALTER TABLE thesis_predictions
        ADD COLUMN epsilon_delta_pct_at_pose REAL
        CHECK(epsilon_delta_pct_at_pose IS NULL OR epsilon_delta_pct_at_pose > 0)
    """)
    op.execute("""
        ALTER TABLE thesis_predictions
        ADD COLUMN epsilon_neutral_pct_at_pose REAL
        CHECK(epsilon_neutral_pct_at_pose IS NULL OR epsilon_neutral_pct_at_pose > 0)
    """)

    # 2. BACKFILL poses pre-0054 sous doctrine ε=1.0 (juin 2026).
    #    Doit se faire AVANT le DROP/CREATE trigger 1 — sinon le trigger
    #    bloque l'UPDATE (les nouvelles colonnes seraient figées).
    #    Au moment de cette migration, SK Hynix ID 1 (asof 2026-06-11) et
    #    CCJ ID 2 (asof 2026-06-10) ont été posées dans la même session,
    #    doctrine ε_delta=1.0 + ε_neutral=1.0 (cf shared/thesis_alpha.py
    #    defaults, shared/thesis_predictions_writer.py DEFAULT_EPSILON_*_PCT,
    #    bot/jobs/thesis_alpha_resolver.py defaults). Le WHERE ε IS NULL
    #    handles N rows existantes sans hardcode d'IDs — fonctionne aussi si
    #    la migration est jouée plus tôt (0 row à backfill) ou plus tard.
    op.execute("""
        UPDATE thesis_predictions
           SET epsilon_delta_pct_at_pose = 1.0,
               epsilon_neutral_pct_at_pose = 1.0
         WHERE epsilon_delta_pct_at_pose IS NULL
            OR epsilon_neutral_pct_at_pose IS NULL
    """)

    # 3. DROP+RECREATE trigger 1 (pose_writeonce) pour inclure les DEUX
    #    nouvelles colonnes dans liste UPDATE OF. Backfill ci-dessus est
    #    désormais figé immuable (cure rétrospective + protection future).
    op.execute("DROP TRIGGER thesis_predictions_pose_writeonce")
    op.execute("""
        CREATE TRIGGER thesis_predictions_pose_writeonce
        BEFORE UPDATE OF
            ticker, asof, asof_price_native, native_currency,
            pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
            your_target_native, your_delta_native_pct, confidence, thesis_summary,
            resolve_due_date, source, notes, created_at,
            epsilon_delta_pct_at_pose, epsilon_neutral_pct_at_pose
        ON thesis_predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'thesis_predictions pose columns are immutable post-insert (SPEC §2.2 / L26 append-only). Pour corriger : INSERT une nouvelle ligne, ne PAS update.');
        END
    """)


def downgrade() -> None:
    bind = op.get_bind()

    # Étape 1 : garde Python (perte des ε figés = perte de reproductibilité 12m)
    n_with_pose_eps = bind.execute(
        text(
            "SELECT COUNT(*) FROM thesis_predictions "
            "WHERE epsilon_delta_pct_at_pose IS NOT NULL "
            "   OR epsilon_neutral_pct_at_pose IS NOT NULL"
        )
    ).scalar() or 0
    if n_with_pose_eps > 0:
        raise RuntimeError(
            f"downgrade 0054 → 0053 BLOQUÉ : {n_with_pose_eps} pose(s) avec ε figé. "
            f"Perte de la doctrine figée = perte de la reproductibilité bit-perfect "
            f"du verdict à t+12m. Export track-record + audit migration manuelle "
            f"requis avant downgrade (sinon les paris reposés deviendraient "
            f"silencieusement classifiables sous une doctrine ε différente)."
        )

    # Étape 2 : DROP TRIGGER 1 (libère référence sur les colonnes pose-ε)
    op.execute("DROP TRIGGER thesis_predictions_pose_writeonce")

    # Étape 3 : DROP COLUMNS (les deux, ordre indifférent)
    op.execute("ALTER TABLE thesis_predictions DROP COLUMN epsilon_neutral_pct_at_pose")
    op.execute("ALTER TABLE thesis_predictions DROP COLUMN epsilon_delta_pct_at_pose")

    # Étape 4 : CREATE TRIGGER 1 étroit (état 0053 : sans ε)
    op.execute("""
        CREATE TRIGGER thesis_predictions_pose_writeonce
        BEFORE UPDATE OF
            ticker, asof, asof_price_native, native_currency,
            pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
            your_target_native, your_delta_native_pct, confidence, thesis_summary,
            resolve_due_date, source, notes, created_at
        ON thesis_predictions
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'thesis_predictions pose columns are immutable post-insert (SPEC §2.2 / L26 append-only). Pour corriger : INSERT une nouvelle ligne, ne PAS update.');
        END
    """)
