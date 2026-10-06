# -*- coding: utf-8 -*-
"""
KnowledgeDigest -- Document List Panel.
Zeigt Dokumente als sortierbare Tabelle.
Adaptiert von DokuZentrum (gui/panels/document_list.py).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt

from ..event_bus import EventType, get_event_bus
from ...utils import dir_filter_sql, open_path, resolve_document_path


class DocumentListPanel(QWidget):
    """Mittleres Panel: Dokumentenliste."""

    COLUMNS = ["Dateiname", "Typ", "Woerter", "Chunks", "Status"]

    def __init__(self, kd, parent=None):
        super().__init__(parent)
        self._kd = kd
        self._bus = get_event_bus()
        self._current_filter = None
        self._docs = []
        self._setup_ui()
        self._connect_signals()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget()
        self._table.setColumnCount(len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._table)

    def _connect_signals(self):
        self._table.currentCellChanged.connect(self._on_selection_changed)
        self._table.cellDoubleClicked.connect(self._on_double_click)

    def refresh(self):
        """Laedt Dokumentenliste aus der DB."""
        self._load_documents(self._current_filter)

    def filter_by_directory(self, path):
        """Filtert nach Verzeichnis."""
        if path == "__all__":
            self._current_filter = None
        else:
            self._current_filter = path
        self._load_documents(self._current_filter)

    def show_search_results(self, results):
        """Zeigt Suchergebnisse."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._docs = []

        for r in results:
            self._docs.append(r)
            row = self._table.rowCount()
            self._table.insertRow(row)

            name = r.get("filename", r.get("name", "?"))
            self._table.setItem(row, 0, self._name_item(name, len(self._docs) - 1))
            self._table.setItem(row, 1, QTableWidgetItem(r.get("file_type", r.get("source", ""))))

            wc = QTableWidgetItem()
            wc.setData(Qt.ItemDataRole.DisplayRole, r.get("word_count", 0))
            self._table.setItem(row, 2, wc)

            cc = QTableWidgetItem()
            cc.setData(Qt.ItemDataRole.DisplayRole, r.get("chunk_count", 0))
            self._table.setItem(row, 3, cc)

            self._table.setItem(row, 4, QTableWidgetItem(
                r.get("snippet", "")[:60] if r.get("snippet") else ""
            ))

        self._table.setSortingEnabled(True)
        self._bus.emit(EventType.STATUS_MESSAGE, f"{len(results)} Suchergebnisse")

    def _load_documents(self, dir_filter=None):
        """Laedt Dokumente aus der DB."""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._docs = []

        try:
            from ...schema import ensure_schema
            conn = ensure_schema(self._kd.db_path)

            if dir_filter:
                where_sql, where_params = dir_filter_sql("d.source_dir", dir_filter)
                rows = conn.execute(f"""
                    SELECT d.id, d.filename, d.file_type, d.word_count, d.chunk_count,
                           d.file_path, d.archived_path, d.source_dir,
                           (SELECT COUNT(*) FROM summaries s
                            WHERE s.source_type='document' AND s.source_id=d.id) as sum_count
                    FROM documents d
                    WHERE {where_sql}
                    ORDER BY d.filename
                """, where_params).fetchall()
            else:
                rows = conn.execute("""
                    SELECT d.id, d.filename, d.file_type, d.word_count, d.chunk_count,
                           d.file_path, d.archived_path, d.source_dir,
                           (SELECT COUNT(*) FROM summaries s
                            WHERE s.source_type='document' AND s.source_id=d.id) as sum_count
                    FROM documents d
                    ORDER BY d.filename
                """).fetchall()

            conn.close()

            for row in rows:
                doc = dict(row)
                self._docs.append(doc)
                r = self._table.rowCount()
                self._table.insertRow(r)

                self._table.setItem(r, 0, self._name_item(doc["filename"], len(self._docs) - 1))
                self._table.setItem(r, 1, QTableWidgetItem(doc.get("file_type", "")))

                wc = QTableWidgetItem()
                wc.setData(Qt.ItemDataRole.DisplayRole, doc.get("word_count", 0))
                self._table.setItem(r, 2, wc)

                cc = QTableWidgetItem()
                cc.setData(Qt.ItemDataRole.DisplayRole, doc.get("chunk_count", 0))
                self._table.setItem(r, 3, cc)

                sc = doc.get("sum_count", 0)
                status = "summarized" if sc > 0 else "pending"
                self._table.setItem(r, 4, QTableWidgetItem(status))

        except Exception as e:
            self._bus.emit(EventType.ERROR_MESSAGE, f"Fehler: {e}")

        self._table.setSortingEnabled(True)

    @staticmethod
    def _name_item(text, doc_index):
        """Spalte-0-Item; merkt sich den Index in self._docs (UserRole),
        da die sichtbare Zeile nach dem Sortieren nicht mehr dem Index entspricht."""
        item = QTableWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, doc_index)
        return item

    def _doc_at(self, row):
        """Dokument zur sichtbaren Tabellenzeile (sortierfest)."""
        item = self._table.item(row, 0)
        if item is None:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self._docs):
            return self._docs[idx]
        return None

    def _on_selection_changed(self, row, col, prev_row, prev_col):
        doc = self._doc_at(row)
        if doc is not None:
            self._bus.emit(EventType.DOCUMENT_SELECTED, doc)

    def _on_double_click(self, row, col):
        """Doppelklick oeffnet Datei."""
        doc = self._doc_at(row)
        if doc is not None:
            file_path = resolve_document_path(doc)
            if file_path:
                try:
                    open_path(file_path)
                except Exception:
                    pass
