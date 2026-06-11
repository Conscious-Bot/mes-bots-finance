"""Cure P0-2 audit (3) 12/06/2026 — meta-test enforcement registre append-only.

Énumère `APPEND_ONLY_TABLES` (source unique) et assert que chaque table a le
trigger correspondant à sa classe en live DB. → L25 auto-enforcé : si quelqu'un
ajoute une table au registre sans trigger correspondant (ou inversement), le
test mord au CI.

Ce test est LE feedback loop qui empêche le drift gravé ≠ appliqué de revenir.
Cherny n°1 — sans verification, la doctrine devient cosmétique.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from shared.append_only_registry import APPEND_ONLY_TABLES


def _get_triggers_for_table(cx: sqlite3.Connection, table: str) -> list[str]:
    """Retourne la liste des noms de triggers définis sur cette table."""
    rows = cx.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
        (table,),
    ).fetchall()
    return [r[0] for r in rows]


def _get_trigger_sql(cx: sqlite3.Connection, trigger_name: str) -> str:
    """Retourne le SQL de définition du trigger."""
    row = cx.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
        (trigger_name,),
    ).fetchone()
    return row[0] if row else ""


def test_append_only_tables_have_no_delete_trigger(migrated_db: Path):
    """Toute table dans APPEND_ONLY_TABLES (peu importe la classe) doit avoir
    un trigger BEFORE DELETE qui RAISE.

    Niveau 1 du registre : no_delete est commun aux 2 classes (immutable
    + no_delete). Si cette assertion casse, c'est qu'une table a été ajoutée
    au registre sans migration de trigger correspondante.
    """
    cx = sqlite3.connect(str(migrated_db))
    cx.row_factory = sqlite3.Row

    missing: list[tuple[str, str]] = []
    for table, klass in sorted(APPEND_ONLY_TABLES.items()):
        triggers = _get_triggers_for_table(cx, table)
        # Cherche un trigger BEFORE DELETE qui RAISE
        has_no_delete = False
        for trig_name in triggers:
            sql = _get_trigger_sql(cx, trig_name)
            if "BEFORE DELETE" in sql.upper() and "RAISE" in sql.upper():
                has_no_delete = True
                break
        if not has_no_delete:
            missing.append((table, klass))

    if missing:
        msg = ["Tables append-only sans trigger BEFORE DELETE RAISE :"]
        for table, klass in missing:
            msg.append(f"  {table} (classe={klass!r}) — registre dit append-only mais aucun trigger no_delete trouvé")
        msg.append("")
        msg.append("Cure : ajouter le trigger via migration alembic, OU retirer la table du registre si pas vraiment append-only.")
        raise AssertionError("\n".join(msg))


def test_immutable_tables_also_have_no_update_trigger(migrated_db: Path):
    """Niveau 2 du registre : les tables 'immutable' (strict write-once) DOIVENT
    aussi avoir un trigger BEFORE UPDATE qui RAISE.

    Les tables 'no_delete' (mutable rétention) NE DOIVENT PAS avoir ce trigger
    — il casserait les UPDATE légitimes (scoring_status, résolution bias, etc.).
    Ce test vérifie l'asymétrie classe par classe.
    """
    cx = sqlite3.connect(str(migrated_db))
    cx.row_factory = sqlite3.Row

    missing_immutable: list[str] = []
    wrongly_immutable: list[str] = []

    for table, klass in sorted(APPEND_ONLY_TABLES.items()):
        triggers = _get_triggers_for_table(cx, table)
        has_no_update = False
        for trig_name in triggers:
            sql = _get_trigger_sql(cx, trig_name)
            if "BEFORE UPDATE" in sql.upper() and "RAISE" in sql.upper():
                has_no_update = True
                break

        if klass == "immutable" and not has_no_update:
            missing_immutable.append(table)
        elif klass == "no_delete" and has_no_update:
            wrongly_immutable.append(table)

    if missing_immutable or wrongly_immutable:
        msg = ["Triggers UPDATE incohérents avec classe registre :"]
        for t in missing_immutable:
            msg.append(f"  {t} (classe='immutable') MANQUE un trigger BEFORE UPDATE RAISE — strict write-once non-enforced")
        for t in wrongly_immutable:
            msg.append(f"  {t} (classe='no_delete') A un trigger BEFORE UPDATE RAISE — casserait les UPDATE légitimes (scoring/résolution/backfill)")
        msg.append("")
        msg.append("Cure : aligner classe registre et triggers via migration, OU re-vérifier la classification (grep `UPDATE table_name` source).")
        raise AssertionError("\n".join(msg))


def test_registry_classification_is_documented():
    """Le registre doit avoir une rationale par entrée (commentaire au-dessus).
    Pas hard-enforceable au sens strict, mais on vérifie au moins la cohérence
    de l'enum AppendOnlyClass."""
    valid_classes = {"immutable", "no_delete"}
    for table, klass in APPEND_ONLY_TABLES.items():
        assert klass in valid_classes, (
            f"Table {table!r} a classe {klass!r} hors enum {valid_classes} — registre corrompu"
        )
