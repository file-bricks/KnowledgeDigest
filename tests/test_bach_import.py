# -*- coding: utf-8 -*-
"""
Fixture-Tests für den optionalen BACH-Import (Standalone-Funktionen).

Testet:
  - Graceful-Fallback-Pfade ohne echte bach.db (available=False, kein Crash)
  - Positiv-Pfad mit synthetischer bach.db (available=True, Daten landen in knowledge.db)

Setzt KEIN echtes BACH voraus und benötigt KEIN pip install -e .
(Projektverzeichnis wird via sys.path.insert eingebunden).
"""
import sys
import sqlite3
from pathlib import Path

# Projektverzeichnis in sys.path eintragen — ermöglicht direkten Import
# ohne "pip install -e ." (wie in test_core.py für chunker/schema/etc.)
sys.path.insert(0, str(Path(__file__).parent.parent))

from indexer import import_bach_skills      # noqa: E402
from wiki_indexer import import_bach_wikis  # noqa: E402

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Minimale synthetische bach.db erzeugen
# ---------------------------------------------------------------------------

def _make_skills_db(path: Path) -> None:
    """Erzeugt eine minimale bach.db mit einem Skill-Datensatz."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE skills (
            id            INTEGER PRIMARY KEY,
            name          TEXT,
            type          TEXT,
            category      TEXT,
            path          TEXT,
            description   TEXT,
            version       TEXT,
            content       TEXT,
            content_hash  TEXT,
            is_active     INTEGER
        )
    """)
    conn.execute("""
        INSERT INTO skills
            (id, name, type, category, path, description, version,
             content, content_hash, is_active)
        VALUES
            (1, 'fixture-skill', 'workflow', 'testing',
             'skills/fixture.md', 'Ein Fixture-Skill fuer Tests.', '1.0',
             'Das ist der Inhalt des Fixture-Skills fuer den Import-Test.',
             'fixture_hash_abc123', 1)
    """)
    conn.commit()
    conn.close()


def _make_wikis_db(path: Path) -> None:
    """Erzeugt eine minimale bach.db mit einem Wiki-Artikel."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE wiki_articles (
            id            INTEGER PRIMARY KEY,
            path          TEXT,
            title         TEXT,
            content       TEXT,
            category      TEXT,
            last_modified TEXT,
            tags          TEXT
        )
    """)
    conn.execute("""
        INSERT INTO wiki_articles
            (id, path, title, content, category, last_modified, tags)
        VALUES
            (1, 'wiki/fixture.md', 'Fixture-Artikel',
             'Inhalt des Fixture-Wiki-Artikels fuer den Import-Test.',
             'testing', '2026-01-01', 'fixture,test')
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests: import_bach_skills – Fallback-Pfade (kein echtes BACH)
# ---------------------------------------------------------------------------

class TestImportBachSkillsOhneBach:
    """Prüft Graceful-Fallback ohne vorhandene bach.db."""

    def test_kein_pfad_gibt_available_false(self, tmp_path):
        """bach_db_path=None → available=False, kein Exception."""
        result = import_bach_skills(None, tmp_path / "knowledge.db")
        assert isinstance(result, dict)
        assert result.get("available") is False
        assert "error" in result

    def test_fehlender_pfad_gibt_available_false(self, tmp_path):
        """Nicht existierender Pfad → available=False mit Fehlermeldung."""
        result = import_bach_skills(
            tmp_path / "nicht_vorhanden.db",
            tmp_path / "knowledge.db",
        )
        assert isinstance(result, dict)
        assert result.get("available") is False
        assert "error" in result

    def test_db_ohne_skills_tabelle_kein_crash(self, tmp_path):
        """Leere SQLite-DB ohne skills-Tabelle → available=False, kein Exception."""
        leere_db = tmp_path / "leer.db"
        sqlite3.connect(str(leere_db)).close()  # erstellt leere DB
        result = import_bach_skills(leere_db, tmp_path / "knowledge.db")
        assert isinstance(result, dict)
        assert result.get("available") is False
        assert "error" in result

    def test_rueckgabe_immer_dict(self, tmp_path):
        """Rückgabe ist in allen Fehlerpfaden immer ein Dict (nicht None, kein Crash)."""
        faelle = [None, "/absolut/kein/pfad/bach.db", tmp_path / "fehlt.db"]
        for pfad in faelle:
            result = import_bach_skills(pfad, tmp_path / "knowledge.db")
            assert isinstance(result, dict), (
                f"Kein Dict zurückgegeben für bach_db_path={pfad!r}"
            )


# ---------------------------------------------------------------------------
# Tests: import_bach_skills – Positiv-Pfad mit Fixture-Daten
# ---------------------------------------------------------------------------

class TestImportBachSkillsMitFixture:
    """Positiv-Test mit synthetischer bach.db."""

    def test_skill_wird_indexiert(self, tmp_path):
        """Synthetische bach.db mit einem Skill → available=True, indexed=1."""
        bach_db = tmp_path / "bach.db"
        kdb = tmp_path / "knowledge.db"
        _make_skills_db(bach_db)

        result = import_bach_skills(bach_db, kdb)

        assert result.get("available") is True, f"Unerwartetes Ergebnis: {result}"
        assert result.get("total_skills") == 1
        assert result.get("indexed") == 1
        assert result.get("skipped") == 0
        assert result.get("chunks_created", 0) >= 1


# ---------------------------------------------------------------------------
# Tests: import_bach_wikis – Fallback-Pfade (kein echtes BACH)
# ---------------------------------------------------------------------------

class TestImportBachWikisOhneBach:
    """Prüft Graceful-Fallback ohne vorhandene bach.db."""

    def test_kein_pfad_gibt_available_false(self, tmp_path):
        """bach_db_path=None → available=False, kein Exception."""
        result = import_bach_wikis(None, tmp_path / "knowledge.db")
        assert isinstance(result, dict)
        assert result.get("available") is False
        assert "error" in result

    def test_fehlender_pfad_gibt_available_false(self, tmp_path):
        """Nicht existierender Pfad → available=False."""
        result = import_bach_wikis(
            tmp_path / "kein_bach.db",
            tmp_path / "knowledge.db",
        )
        assert isinstance(result, dict)
        assert result.get("available") is False
        assert "error" in result

    def test_db_ohne_wiki_tabelle_kein_crash(self, tmp_path):
        """Leere SQLite-DB ohne wiki_articles-Tabelle → available=False, kein Exception."""
        leere_db = tmp_path / "leer.db"
        sqlite3.connect(str(leere_db)).close()
        result = import_bach_wikis(leere_db, tmp_path / "knowledge.db")
        assert isinstance(result, dict)
        assert result.get("available") is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Tests: import_bach_wikis – Positiv-Pfad mit Fixture-Daten
# ---------------------------------------------------------------------------

class TestImportBachWikisMitFixture:
    """Positiv-Test mit synthetischer bach.db."""

    def test_wiki_wird_indexiert(self, tmp_path):
        """Synthetische bach.db mit einem Wiki-Artikel → available=True, indexed=1."""
        bach_db = tmp_path / "bach.db"
        kdb = tmp_path / "knowledge.db"
        _make_wikis_db(bach_db)

        result = import_bach_wikis(bach_db, kdb)

        assert result.get("available") is True, f"Unerwartetes Ergebnis: {result}"
        assert result.get("total_wikis") == 1
        assert result.get("indexed") == 1
        assert result.get("chunks_created", 0) >= 1
