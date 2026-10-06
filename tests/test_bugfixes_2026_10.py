"""
Regressionstests fuer die Bugfix-Runde 2026-10.

Jeder Test fixiert einen verifizierten Befund (Nummern wie im Review):
 1  FTS5-Delete-Trigger ('delete'-Befehl auf regulaerer FTS5-Tabelle)
 2  Loeschen: erst DB (Transaktion), dann Datei verschieben
 3  Falsche relative Imports in gui/panels
 4  SQLite-Connection aus GUI-Thread in Scan-Threads
 5  EventBus ruft Handler im Worker-Thread auf
 6  Queue-Item 'done' obwohl Chunks fehlschlugen
 7  Queue-Items haengen nach Absturz in 'processing'
 8  Sortierte Dokumentliste -> falsches Dokument
 9  FTS5-Syntaxfehler durch Freitext / LIKE-Platzhalter
10  Re-Ingest: alte Summaries + Queue-Status
11  Archivierte Dokumente (archived_path)
12  Harte Chunk-Obergrenze
13  UTF-8-BOM verdeckt Frontmatter
14  Verzeichnisfilter matcht Geschwister-Ordner
15  is_active=0 wurde zu 1
 +  Kostenschaetzung Haiku 4.5, zoll_station-Aufruf, open_path

Keine Netzwerkzugriffe, keine echten LLM-Aufrufe.
"""

import importlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

_PKG_PARENT = str(Path(__file__).resolve().parent.parent.parent)
_PKG_NAME = Path(__file__).resolve().parent.parent.name


def _mod(name):
    """Importiert ein Paket-Modul (digest.py & Co. nutzen relative Imports)."""
    if _PKG_PARENT not in sys.path:
        sys.path.insert(0, _PKG_PARENT)
    pkg = _PKG_NAME if _PKG_NAME.isidentifier() else "KnowledgeDigest"
    return importlib.import_module(f"{pkg}.{name}")


def _make_kd(tmp_path):
    config_mod = _mod("config")
    digest_mod = _mod("digest")
    cfg = config_mod.Config(tmp_path / "cfg.json")
    cfg.set("inbox_dir", str(tmp_path / "inbox"))
    cfg.set("archive_dir", str(tmp_path / "archive"))
    cfg.set("indexed_directories", [])
    return digest_mod.KnowledgeDigest(db_path=tmp_path / "knowledge.db", config=cfg)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _db(kd):
    return _mod("schema").ensure_schema(kd.db_path)


def _qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ============================================================
# 1  FTS5-Delete-Trigger
# ============================================================

_LEGACY_DOC_TRIGGER = """
CREATE TRIGGER doc_chunk_ad AFTER DELETE ON document_chunks BEGIN
    INSERT INTO document_fts(document_fts, rowid, filename, content)
    SELECT 'delete', old.id,
           (SELECT filename FROM documents WHERE id = old.doc_id),
           old.content;
END;
"""


class TestFtsDeleteTriggers:
    def test_reingest_modified_file(self, tmp_path):
        kd = _make_kd(tmp_path)
        f = _write(tmp_path / "docs" / "a.txt", "Altinhalt Apfel. " * 100)
        assert kd.ingest(f, archive=False)["status"] == "ok"
        _write(f, "Neuinhalt Birne. " * 100)
        result = kd.ingest(f, archive=False)
        assert result["status"] == "ok", result["error"]
        assert kd._search_documents("Birne")
        assert not kd._search_documents("Apfel")
        conn = _db(kd)
        n_fts = conn.execute("SELECT COUNT(*) FROM document_fts").fetchone()[0]
        n_chunks = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
        conn.close()
        kd.close()
        assert n_fts == n_chunks

    def test_legacy_trigger_is_migrated(self, tmp_path):
        schema = _mod("schema")
        db = tmp_path / "knowledge.db"
        conn = schema.ensure_schema(db)
        conn.execute("DROP TRIGGER doc_chunk_ad")
        conn.executescript(_LEGACY_DOC_TRIGGER)
        conn.execute("INSERT INTO documents (id, file_path, filename, file_type) "
                     "VALUES (1, 'x', 'x.txt', 'txt')")
        conn.execute("INSERT INTO document_chunks (doc_id, chunk_index, content) "
                     "VALUES (1, 0, 'hallo welt')")
        conn.commit()
        # Vorbedingung: mit altem Trigger schlaegt jedes DELETE fehl
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM document_chunks WHERE doc_id = 1")
        conn.rollback()
        conn.close()

        conn = schema.ensure_schema(db)  # Migration beim Oeffnen
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='doc_chunk_ad'").fetchone()[0]
        assert "'delete'" not in sql
        conn.execute("DELETE FROM document_chunks WHERE doc_id = 1")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM document_fts").fetchone()[0] == 0
        assert schema.get_schema_version(db) == schema.SCHEMA_VERSION == 5
        conn.close()

    def test_skill_and_wiki_chunk_delete(self, tmp_path):
        schema = _mod("schema")
        conn = schema.ensure_schema(tmp_path / "knowledge.db")
        conn.execute("INSERT INTO skill_index (id, skill_name, skill_type) VALUES (1, 's', 't')")
        conn.execute("INSERT INTO skill_chunks (skill_id, chunk_index, content) VALUES (1, 0, 'abc')")
        conn.execute("INSERT INTO wiki_index (id, wiki_path, title) VALUES (1, 'w', 'W')")
        conn.execute("INSERT INTO wiki_chunks (wiki_id, chunk_index, content) VALUES (1, 0, 'abc')")
        conn.execute("DELETE FROM skill_chunks")
        conn.execute("DELETE FROM wiki_chunks")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM skill_fts").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM wiki_fts").fetchone()[0] == 0
        conn.close()


# ============================================================
# 2 + 11  Loeschen (Web-Viewer + CLI deduplicate)
# ============================================================

class _Server:
    def __init__(self, db_path):
        wv = _mod("web_viewer")
        handler = type("H", (wv.ViewerHandler,), {"db_path": Path(db_path)})
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def post(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     method="POST", data=b"")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _ingested_doc(tmp_path, name="a.txt"):
    kd = _make_kd(tmp_path)
    f = _write(tmp_path / "docs" / name, f"Inhalt {name}. " * 80)
    assert kd.ingest(f, archive=False)["status"] == "ok"
    kd.close()
    return kd, f


class TestDeleteOrder:
    def test_db_failure_leaves_file_in_place(self, tmp_path):
        kd, f = _ingested_doc(tmp_path)
        conn = _db(kd)
        conn.execute("CREATE TRIGGER block_del BEFORE DELETE ON documents "
                     "BEGIN SELECT RAISE(ABORT, 'boom'); END;")
        conn.commit()
        srv = _Server(kd.db_path)
        try:
            status, body = srv.post("/api/delete_file/1")
        finally:
            srv.stop()
        assert status == 500 and not body["ok"]
        assert f.exists()  # Datei nicht verschoben
        # Transaktion zurueckgerollt: Chunks noch da
        assert conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0] > 0
        conn.close()

    def test_move_failure_keeps_db_consistent(self, tmp_path, monkeypatch):
        kd, f = _ingested_doc(tmp_path)
        wv = _mod("web_viewer")

        def _fail(*_a, **_k):
            raise PermissionError("gesperrt")
        monkeypatch.setattr(wv, "move_to_trash", _fail)
        srv = _Server(kd.db_path)
        try:
            status, body = srv.post("/api/delete_file/1")
        finally:
            srv.stop()
        assert status == 200 and body["ok"]
        assert "gesperrt" in body["warning"]
        conn = _db(kd)
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        conn.close()
        assert f.exists()

    def test_delete_archived_document_moves_archived_file(self, tmp_path):
        kd, f = _ingested_doc(tmp_path)
        archived = tmp_path / "archive" / "20260101_a.txt"
        archived.parent.mkdir(parents=True)
        f.rename(archived)
        conn = _db(kd)
        conn.execute("UPDATE documents SET archived_path=? WHERE id=1", (str(archived),))
        conn.commit()
        conn.close()
        srv = _Server(kd.db_path)
        try:
            status, body = srv.post("/api/delete_file/1")
        finally:
            srv.stop()
        assert status == 200 and body["ok"]
        assert not archived.exists()
        assert (tmp_path / "_Papierkorb" / "20260101_a.txt").exists()

    def test_deduplicate_continues_after_item_error(self, tmp_path, monkeypatch, capsys):
        digest_mod = _mod("digest")
        kd = _make_kd(tmp_path)
        files = [_write(tmp_path / "docs" / f"d{i}.txt", "gleich") for i in (1, 2, 3)]
        conn = _db(kd)
        for i, fp in enumerate(files, start=1):
            conn.execute("INSERT INTO documents (id, file_path, filename, file_type, content_hash) "
                         "VALUES (?, ?, ?, 'txt', 'h')", (i, str(fp), fp.name))
        conn.execute("CREATE TRIGGER block2 BEFORE DELETE ON documents WHEN old.id = 2 "
                     "BEGIN SELECT RAISE(ABORT, 'boom'); END;")
        conn.commit()
        monkeypatch.setattr(digest_mod, "KnowledgeDigest", lambda *a, **k: kd)
        monkeypatch.setattr(sys, "argv", ["knowledgedigest", "deduplicate", "-y"])
        assert digest_mod.main() == 0
        ids = [r[0] for r in conn.execute("SELECT id FROM documents ORDER BY id")]
        conn.close()
        assert ids == [1, 2]                      # 3 geloescht, 2 blockiert
        assert files[0].exists() and files[1].exists()
        assert not files[2].exists()
        assert (tmp_path / "_Papierkorb" / "d3.txt").exists()
        assert "boom" in capsys.readouterr().out


# ============================================================
# 3 + 8 + 11 + 14  GUI-Panels
# ============================================================

class TestGuiPanels:
    def test_preview_panel_imports_resolve(self, tmp_path):
        _qapp()
        kd, _f = _ingested_doc(tmp_path)
        preview_mod = _mod("gui.panels.preview_panel")
        panel = preview_mod.PreviewPanel()
        panel._current_doc_db_path = lambda: kd.db_path
        panel._show_chunks({"id": 1})
        assert "=== Chunk 0 ===" in panel._chunks_widget.toPlainText()
        # Config-Import (vorher: from ..config -> ModuleNotFoundError)
        assert isinstance(preview_mod.PreviewPanel._current_doc_db_path(panel), Path)

    def test_preview_uses_archived_path(self, tmp_path):
        _qapp()
        preview_mod = _mod("gui.panels.preview_panel")
        archived = _write(tmp_path / "archive" / "x.txt", "archiviert")
        panel = preview_mod.PreviewPanel()
        panel._current_doc_db_path = lambda: tmp_path / "knowledge.db"
        panel.show_document({"filename": "x.txt", "file_path": str(tmp_path / "weg.txt"),
                             "archived_path": str(archived)})
        assert panel._current_path == str(archived)
        assert panel._text_widget.toPlainText() == "archiviert"

    def test_document_list_sorted_selection(self, tmp_path):
        _qapp()
        kd = _make_kd(tmp_path)
        for name, n in (("alpha", 50), ("beta", 10), ("gamma", 30)):
            kd.ingest(_write(tmp_path / "docs" / f"{name}.txt", f"{name} Inhalt hier. " * n),
                      archive=False)
        dl_mod = _mod("gui.panels.document_list")
        bus_mod = _mod("gui.event_bus")
        selected = []
        handler = selected.append
        bus = bus_mod.get_event_bus()
        bus.subscribe(bus_mod.EventType.DOCUMENT_SELECTED, handler)
        try:
            panel = dl_mod.DocumentListPanel(kd)
            assert panel._table.rowCount() == 3  # Import ...schema funktioniert
            panel._table.sortItems(2)  # nach Woertern
            visual = [panel._table.item(r, 0).text() for r in range(3)]
            assert visual == ["beta.txt", "gamma.txt", "alpha.txt"]
            panel._table.setCurrentCell(0, 0)
            assert selected[-1]["filename"] == "beta.txt"
            panel._table.setCurrentCell(2, 0)
            assert selected[-1]["filename"] == "alpha.txt"
        finally:
            bus.unsubscribe(bus_mod.EventType.DOCUMENT_SELECTED, handler)
            kd.close()

    def test_document_list_directory_filter_excludes_siblings(self, tmp_path):
        _qapp()
        kd = _make_kd(tmp_path)
        kd.ingest(_write(tmp_path / "docs" / "a.txt", "Erstes Dokument. " * 30), archive=False)
        kd.ingest(_write(tmp_path / "docs" / "sub" / "b.txt", "Zweites Dokument. " * 30),
                  archive=False)
        kd.ingest(_write(tmp_path / "docs2" / "c.txt", "Drittes Dokument. " * 30), archive=False)
        dl_mod = _mod("gui.panels.document_list")
        panel = dl_mod.DocumentListPanel(kd)
        panel.filter_by_directory(str(tmp_path / "docs"))
        names = sorted(d["filename"] for d in panel._docs)
        kd.close()
        assert names == ["a.txt", "b.txt"]


# ============================================================
# 4  Thread-lokale Connections
# ============================================================

class TestThreadConnections:
    def test_scan_in_worker_thread_after_gui_thread_use(self, tmp_path):
        kd = _make_kd(tmp_path)
        kd.get_status()  # GUI-Thread oeffnet Connections (Ingestor, Summarizer)
        src = tmp_path / "docs"
        for i in range(3):
            _write(src / f"f{i}.txt", f"Dokument Nummer {i} mit Text. " * 30)
        out = {}
        t = threading.Thread(target=lambda: out.update(
            kd.scan_directory(str(src), archive=False)))
        t.start()
        t.join()
        assert out["errors"] == 0, [f["error"] for f in out["files"]]
        assert out["ingested"] == 3
        assert kd.get_status()["documents"]["total_documents"] == 3
        kd.close()

    def test_close_all_and_reopen(self, tmp_path):
        schema = _mod("schema")
        pool = schema.ThreadLocalConnections()
        db = tmp_path / "knowledge.db"
        c1 = pool.get(db)
        assert pool.get(db) is c1
        other = {}
        t = threading.Thread(target=lambda: other.update(c=pool.get(db)))
        t.start()
        t.join()
        assert other["c"] is not c1
        pool.close_all()
        with pytest.raises(sqlite3.ProgrammingError):
            c1.execute("SELECT 1")
        with pytest.raises(sqlite3.ProgrammingError):
            other["c"].execute("SELECT 1")
        c2 = pool.get(db)
        assert c2 is not c1
        c2.execute("SELECT 1")
        pool.close_all()


# ============================================================
# 5  EventBus: Handler im GUI-Thread
# ============================================================

class TestEventBusThreading:
    def test_emit_from_worker_dispatches_in_gui_thread(self):
        app = _qapp()
        bus_mod = _mod("gui.event_bus")
        bus = bus_mod.EventBus()
        calls = []
        bus.subscribe(bus_mod.EventType.STATUS_MESSAGE,
                      lambda data: calls.append((data, threading.current_thread())))

        t = threading.Thread(target=lambda: bus.emit(bus_mod.EventType.STATUS_MESSAGE, "aus Thread"))
        t.start()
        t.join()
        assert calls == []  # nicht synchron im Worker-Thread ausgefuehrt
        deadline = time.time() + 5
        while not calls and time.time() < deadline:
            app.processEvents()
        assert calls == [("aus Thread", threading.main_thread())]

    def test_emit_in_gui_thread_is_synchronous(self):
        _qapp()
        bus_mod = _mod("gui.event_bus")
        bus = bus_mod.EventBus()
        calls = []
        bus.subscribe(bus_mod.EventType.STATUS_MESSAGE, calls.append)
        bus.emit(bus_mod.EventType.STATUS_MESSAGE, "direkt")
        assert calls == ["direkt"]


# ============================================================
# 6 + 7  Summarizer-Queue
# ============================================================

def _queue_db(tmp_path, n_chunks=2):
    schema = _mod("schema")
    db = tmp_path / "knowledge.db"
    conn = schema.ensure_schema(db)
    conn.execute("INSERT INTO documents (id, file_path, filename, file_type) "
                 "VALUES (1, 'x', 'x.txt', 'txt')")
    for i in range(n_chunks):
        conn.execute("INSERT INTO document_chunks (doc_id, chunk_index, content) "
                     "VALUES (1, ?, ?)", (i, f"chunk {i}"))
    conn.execute("INSERT INTO digest_queue (source_type, source_id) VALUES ('document', 1)")
    conn.commit()
    return db, conn


_OK_JSON = '{"summary": "s", "keywords": ["k"], "domain": "d"}'


class TestSummarizerQueue:
    def test_partial_chunk_failure_marks_error(self, tmp_path):
        Summarizer = _mod("summarizer").Summarizer
        db, conn = _queue_db(tmp_path)

        def llm(_system, text):
            if text == "chunk 1":
                raise RuntimeError("API down / 429")
            return _OK_JSON
        s = Summarizer(db, provider="custom", llm_fn=llm)
        stats = s.summarize_queue(limit=5, delay=0)
        s.close()
        row = conn.execute("SELECT status, error_msg FROM digest_queue").fetchone()
        assert (stats["processed"], stats["errors"]) == (0, 1)
        assert row["status"] == "error"
        assert "429" in row["error_msg"] and "1/2" in row["error_msg"]
        # Erfolgreiche Summary bleibt erhalten
        assert conn.execute("SELECT chunk_index FROM summaries").fetchall()[0][0] == 0
        conn.close()

    def test_all_chunks_ok_marks_done(self, tmp_path):
        Summarizer = _mod("summarizer").Summarizer
        db, conn = _queue_db(tmp_path)
        s = Summarizer(db, provider="custom", llm_fn=lambda _s, _t: _OK_JSON)
        stats = s.summarize_queue(limit=5, delay=0)
        s.close()
        assert (stats["processed"], stats["errors"]) == (1, 0)
        assert conn.execute("SELECT status FROM digest_queue").fetchone()[0] == "done"
        conn.close()

    def test_gemini_chunk_failure_marks_error(self, tmp_path):
        gfs = _mod("gemini_flash_summarizer")
        db, conn = _queue_db(tmp_path, n_chunks=1)
        s = gfs.GeminiFlashSummarizer(db, api_key="k")
        s._summarize_chunk = lambda _text: {"error": "quota"}
        stats = s.summarize_queue(limit=5, delay=0)
        s.close()
        assert stats["errors"] == 1 and stats["processed"] == 0
        row = conn.execute("SELECT status, error_msg FROM digest_queue").fetchone()
        assert row["status"] == "error" and "quota" in row["error_msg"]
        conn.close()

    def test_stale_processing_is_reset(self, tmp_path):
        Summarizer = _mod("summarizer").Summarizer
        db, conn = _queue_db(tmp_path, n_chunks=1)
        conn.execute("INSERT INTO documents (id, file_path, filename, file_type) "
                     "VALUES (2, 'y', 'y.txt', 'txt'), (3, 'z', 'z.txt', 'txt')")
        conn.execute("INSERT INTO document_chunks (doc_id, chunk_index, content) "
                     "VALUES (2, 0, 'a'), (3, 0, 'b')")
        conn.execute("UPDATE digest_queue SET status='processing', "
                     "started_at=datetime('now', '-2 hours') WHERE source_id=1")
        conn.execute("INSERT INTO digest_queue (source_type, source_id, status, started_at) "
                     "VALUES ('document', 2, 'processing', NULL), "
                     "('document', 3, 'processing', CURRENT_TIMESTAMP)")
        conn.commit()
        s = Summarizer(db, provider="custom", llm_fn=lambda _s, _t: _OK_JSON)
        stats = s.summarize_queue(limit=10, delay=0)
        s.close()
        status = dict(conn.execute("SELECT source_id, status FROM digest_queue").fetchall())
        conn.close()
        assert stats["reset_stale"] == 2
        assert status == {1: "done", 2: "done", 3: "processing"}  # 3 laeuft noch

    def test_keyboard_interrupt_resets_item_to_pending(self, tmp_path):
        Summarizer = _mod("summarizer").Summarizer
        db, conn = _queue_db(tmp_path)

        def llm(_system, _text):
            raise KeyboardInterrupt
        s = Summarizer(db, provider="custom", llm_fn=llm)
        with pytest.raises(KeyboardInterrupt):
            s.summarize_queue(limit=5, delay=0)
        s.close()
        row = conn.execute("SELECT status, started_at FROM digest_queue").fetchone()
        conn.close()
        assert row["status"] == "pending" and row["started_at"] is None

    def test_haiku_cost_estimate(self, tmp_path):
        Summarizer = _mod("summarizer").Summarizer
        db, conn = _queue_db(tmp_path, n_chunks=1)
        conn.execute("INSERT INTO summaries (source_type, source_id, chunk_index, summary, "
                     "input_tokens, output_tokens) VALUES ('document', 1, 0, 's', 1000000, 1000000)")
        conn.commit()
        conn.close()
        s = Summarizer(db, provider="anthropic", api_key="unused")
        cost = s.get_queue_status()["summaries"]["estimated_cost_usd"]
        s.close()
        assert cost == pytest.approx(6.0)  # $1 in + $5 out pro MTok


# ============================================================
# 9  Suche: FTS5-Syntaxfehler + LIKE-Platzhalter
# ============================================================

class TestSearchSanitizing:
    @pytest.fixture
    def kd(self, tmp_path):
        kd = _make_kd(tmp_path)
        kd.ingest(_write(tmp_path / "docs" / "covid.txt",
                         "Studie zu COVID-19 und E-Mail Verkehr mit c++ Code. " * 20),
                  archive=False)
        kd.ingest(_write(tmp_path / "docs" / "rabatt.txt", "Heute gibt es 50% Rabatt. " * 20),
                  archive=False)
        yield kd
        kd.close()

    @pytest.mark.parametrize("query", ["COVID-19", "E-Mail", "c++", '"COVID-19', "e-mail verkehr"])
    def test_free_text_queries_find_document(self, kd, query):
        names = [r["name"] for r in kd.search_all(query)]
        assert "covid.txt" in names

    def test_fts_syntax_still_works(self, kd):
        assert [r["name"] for r in kd.search_all("Studie AND Verkehr")] == ["covid.txt"]

    def test_document_like_fallback_escapes_wildcards(self, kd):
        conn = kd._get_conn()
        try:
            assert kd._search_documents_fallback(conn, "%%", 10) == []
            assert kd._search_documents_fallback(conn, "5_%", 10) == []
            hits = kd._search_documents_fallback(conn, "50%", 10)
        finally:
            conn.close()
        assert [h["name"] for h in hits] == ["rabatt.txt"]

    def test_skill_like_fallback_escapes_wildcards(self, kd):
        conn = kd._get_conn()
        conn.execute("INSERT INTO skill_index (id, skill_name, skill_type) VALUES (1, 'abc', 't')")
        conn.commit()
        try:
            assert kd._search_fallback(conn, "%", 10, None, None) == []
            assert kd._search_wikis_fallback(conn, "_", 10, None) == []
        finally:
            conn.close()

    def test_web_viewer_search(self, kd):
        wv = _mod("web_viewer")
        assert "covid.txt" in wv.page_search(kd.db_path, query="COVID-19")
        # '%' ist kein LIKE-Platzhalter mehr (vorher: Treffer auf alles)
        assert "covid.txt" not in wv.page_search(kd.db_path, query="%")
        assert "covid.txt" not in wv.page_search(kd.db_path, query='"_')


# ============================================================
# 10  Re-Ingest setzt Summaries + Queue zurueck
# ============================================================

def test_reingest_resets_summaries_and_queue(tmp_path):
    kd = _make_kd(tmp_path)
    f = _write(tmp_path / "docs" / "a.txt", "Version eins. " * 80)
    kd.ingest(f, archive=False)
    conn = _db(kd)
    conn.execute("INSERT INTO summaries (source_type, source_id, chunk_index, summary) "
                 "VALUES ('document', 1, 0, 'alt')")
    conn.execute("UPDATE digest_queue SET status='done', finished_at=CURRENT_TIMESTAMP, "
                 "error_msg='x'")
    conn.commit()
    _write(f, "Version zwei ganz anders. " * 80)
    assert kd.ingest(f, archive=False)["status"] == "ok"
    kd.close()
    assert conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0] == 0
    row = conn.execute("SELECT status, finished_at, error_msg FROM digest_queue").fetchone()
    conn.close()
    assert tuple(row) == ("pending", None, None)


# ============================================================
# 11  resolve_document_path
# ============================================================

def test_resolve_document_path(tmp_path):
    utils = _mod("utils")
    present = _write(tmp_path / "da.txt", "x")
    archived = _write(tmp_path / "archiv.txt", "x")
    missing = str(tmp_path / "weg.txt")
    assert utils.resolve_document_path({"file_path": str(present),
                                        "archived_path": str(archived)}) == str(present)
    assert utils.resolve_document_path({"file_path": missing,
                                        "archived_path": str(archived)}) == str(archived)
    assert utils.resolve_document_path({"file_path": missing}) == missing
    # sqlite3.Row ohne archived_path-Spalte
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT ? AS file_path", (missing,)).fetchone()
    assert utils.resolve_document_path(row) == missing


# ============================================================
# 12 + 13  Chunker / Extractor
# ============================================================

def test_chunker_enforces_hard_upper_bound():
    chunker = _mod("chunker")
    text = " ".join(f"wort{i}" for i in range(3000))
    chunks = chunker.chunk_text(text)
    assert all(c.token_count <= chunker.MAX_CHUNK_SIZE for c in chunks)
    assert " ".join(c.content for c in chunks).split() == text.split()
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_bom_text_file_frontmatter_detected(tmp_path):
    extractor = _mod("extractor")
    chunker = _mod("chunker")
    f = tmp_path / "skill.md"
    f.write_bytes("---\ntitle: x\n---\n# Body\n".encode("utf-8-sig") + b"text " * 100)
    text = extractor.TextExtractor().extract(f).text
    assert not text.startswith("\ufeff")
    assert chunker.chunk_text(text)[0].is_frontmatter
    # auch direkt uebergebener Text mit BOM
    assert chunker.chunk_text("\ufeff---\ntitle: x\n---\n# Body\n" + "text " * 100)[0].is_frontmatter


# ============================================================
# 14  Verzeichnisfilter
# ============================================================

class TestDirectoryFilter:
    def _insert(self, conn, source_dirs):
        for i, d in enumerate(source_dirs, start=1):
            conn.execute("INSERT INTO documents (file_path, filename, file_type, source_dir) "
                         "VALUES (?, ?, 'txt', ?)", (f"{d}/f{i}", f"f{i}", d))
        conn.commit()

    def test_get_directories_counts(self, tmp_path):
        kd = _make_kd(tmp_path)
        base = str(tmp_path / "a_b")
        conn = _db(kd)
        self._insert(conn, [base, base + "/sub", base + "\\win", base + "2",
                            str(tmp_path / "aXb"), base + "%x"])
        conn.close()
        kd._config.set("indexed_directories", [base])
        assert kd.get_directories() == [{"path": base, "doc_count": 3}]

    def test_dir_filter_sql_trailing_separator(self, tmp_path):
        utils = _mod("utils")
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE documents (source_dir TEXT)")
        conn.executemany("INSERT INTO documents VALUES (?)",
                         [("/data/docs",), ("/data/docs/x",), ("/data/docs2",)])
        sql, params = utils.dir_filter_sql("source_dir", "/data/docs/")
        n = conn.execute(f"SELECT COUNT(*) FROM documents WHERE {sql}", params).fetchone()[0]
        assert n == 2


# ============================================================
# 15  is_active=0 bleibt 0
# ============================================================

def test_skill_indexer_keeps_inactive(tmp_path):
    indexer = _mod("indexer")
    bach = tmp_path / "bach.db"
    conn = sqlite3.connect(str(bach))
    conn.execute("CREATE TABLE skills (id INTEGER, name TEXT, type TEXT, category TEXT, "
                 "path TEXT, description TEXT, version TEXT, content TEXT, "
                 "content_hash TEXT, is_active INTEGER)")
    conn.executemany(
        "INSERT INTO skills VALUES (?, ?, 'agent', 'c', 'p', 'd', '1', ?, NULL, ?)",
        [(1, "aktiv", "Inhalt eins " * 20, 1),
         (2, "inaktiv", "Inhalt zwei " * 20, 0),
         (3, "unbekannt", "Inhalt drei " * 20, None)])
    conn.commit()
    conn.close()
    idx = indexer.SkillIndexer(tmp_path / "knowledge.db")
    idx.index_from_bach(bach)
    rows = dict(idx._get_conn().execute("SELECT skill_name, is_active FROM skill_index").fetchall())
    idx.close()
    assert rows == {"aktiv": 1, "inaktiv": 0, "unbekannt": 1}


# ============================================================
# Kleinere Befunde: zoll_station, open_path
# ============================================================

def test_zoll_station_runs_digest_as_module():
    zoll = _mod("zoll_station")
    pkg_dir = Path(zoll.__file__).resolve().parent
    cmd, cwd = zoll._digest_command(pkg_dir, "summarize", "--help")
    assert cmd[:2] == [sys.executable, "-m"]
    assert "digest.py" not in " ".join(cmd)
    assert cwd == str(pkg_dir.parent)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60, check=False,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stderr
    assert "--flash" in result.stdout


@pytest.mark.parametrize("platform, expected", [("darwin", "open"), ("linux", "xdg-open")])
def test_open_path_cross_platform(monkeypatch, platform, expected):
    utils = _mod("utils")
    calls = []
    monkeypatch.setattr(utils.sys, "platform", platform)
    monkeypatch.setattr(utils.subprocess, "Popen", lambda args: calls.append(args))
    utils.open_path(Path("/tmp/x.pdf"))
    assert calls == [[expected, str(Path("/tmp/x.pdf"))]]


def test_open_path_windows(monkeypatch):
    utils = _mod("utils")
    calls = []
    monkeypatch.setattr(utils.sys, "platform", "win32")
    monkeypatch.setattr(utils.os, "startfile", calls.append, raising=False)
    utils.open_path("C:\\x.pdf")
    assert calls == ["C:\\x.pdf"]


def test_config_defaults_are_not_shared_between_instances(tmp_path):
    from KnowledgeDigest.config import DEFAULT_CONFIG, Config

    before = list(DEFAULT_CONFIG["indexed_directories"])
    cfg = Config(tmp_path / "config.json")
    cfg._data["indexed_directories"].append(str(tmp_path))
    assert DEFAULT_CONFIG["indexed_directories"] == before
    assert Config(tmp_path / "other.json")._data["indexed_directories"] == before
