# -*- coding: utf-8 -*-
"""
KnowledgeDigest -- Shared Utilities.

Gemeinsame Funktionen fuer alle Module:
    - sha256_hash(): Content-Hashing fuer Aenderungserkennung
    - extract_keywords(): Keyword-Extraktion mit Stoppwort-Filterung
    - STOP_WORDS: DE/EN Stoppwoerter
    - resolve_document_path(): aktueller Pfad eines Dokuments (auch archiviert)
    - open_path(): Datei/Ordner mit dem Standardprogramm oeffnen (plattformuebergreifend)
    - escape_like(): Platzhalter % und _ fuer LIKE ... ESCAPE '\\' maskieren
    - dir_filter_sql(): SQL-Filter "liegt in Verzeichnis X oder darunter"
    - fts5_quote(): Freitext-Suche als sichere FTS5-Query (Tokens in Anfuehrungszeichen)
    - move_to_trash(): Datei kollisionsfrei in einen Papierkorb-Ordner verschieben
"""

__all__ = ["sha256_hash", "extract_keywords", "STOP_WORDS",
           "resolve_document_path", "open_path", "escape_like",
           "dir_filter_sql", "fts5_quote", "move_to_trash"]

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple


# Stoppwoerter (DE/EN gemischt, fuer Keyword-Extraktion)
STOP_WORDS = frozenset({
    # Deutsch
    'der', 'die', 'das', 'ein', 'eine', 'und', 'oder', 'aber', 'ist', 'sind',
    'wird', 'werden', 'hat', 'haben', 'mit', 'von', 'auf', 'fuer', 'zur',
    'zum', 'den', 'dem', 'des', 'als', 'auch', 'nicht', 'nur', 'wenn',
    'bei', 'aus', 'nach', 'ueber', 'unter', 'vor', 'durch', 'wie', 'noch',
    'kann', 'soll', 'muss', 'alle', 'diese', 'dieser', 'dieses', 'sich',
    'dann', 'denn', 'was', 'wer', 'wo', 'hier', 'dort', 'sein', 'seine',
    'seinem', 'seinen', 'seiner', 'einer', 'eines', 'einem', 'einen',
    # Englisch
    'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
    'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
    'can', 'not', 'no', 'nor', 'so', 'if', 'for', 'of', 'in', 'on', 'at',
    'to', 'from', 'by', 'with', 'as', 'into', 'it', 'its', 'this', 'that',
    'these', 'those', 'which', 'what', 'who', 'how', 'all', 'each', 'any',
    # YAML/Code
    'true', 'false', 'null', 'none', 'yes', 'default', 'type', 'name',
    'value', 'version', 'status', 'active', 'description',
})

# Minimum-Wortlaenge fuer Keywords
MIN_KEYWORD_LEN = 3
MAX_KEYWORDS_PER_ITEM = 30


def sha256_hash(text: str) -> str:
    """SHA256-Hash eines Textes."""
    return hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()


def extract_keywords(text: str, max_count: int = MAX_KEYWORDS_PER_ITEM) -> List[str]:
    """Extrahiert relevante Keywords aus Text.

    Strategie:
        - Alle Woerter tokenisieren
        - Stoppwoerter und zu kurze Woerter filtern
        - Nach Haeufigkeit sortieren
        - Top-N zurueckgeben
    """
    if not text:
        return []

    # Woerter extrahieren (alphanumerisch + Umlaute + Bindestriche)
    words = re.findall(
        r'[a-zA-Z\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df_-]{3,}',
        text.lower()
    )

    # Stoppwoerter filtern
    words = [w for w in words if w not in STOP_WORDS and len(w) >= MIN_KEYWORD_LEN]

    # Haeufigkeit zaehlen
    freq: Dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    # Nach Haeufigkeit sortieren, Top-N
    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [kw for kw, _ in sorted_kw[:max_count]]


def resolve_document_path(doc: Any) -> Optional[str]:
    """Gibt den aktuell gueltigen Pfad eines Dokuments zurueck.

    Archivierte Dokumente liegen nicht mehr unter file_path, sondern unter
    archived_path. Reihenfolge: file_path (falls vorhanden), sonst
    archived_path (falls vorhanden), sonst file_path als Fallback.

    Args:
        doc: dict oder sqlite3.Row mit 'file_path' und optional 'archived_path'
    """
    def _get(key: str) -> Optional[str]:
        try:
            return doc[key]
        except (KeyError, IndexError):
            return None

    file_path = _get("file_path")
    archived_path = _get("archived_path")
    if file_path and os.path.exists(file_path):
        return file_path
    if archived_path and os.path.exists(archived_path):
        return archived_path
    return file_path or archived_path or None


def open_path(path: Any) -> None:
    """Oeffnet Datei/Ordner mit dem Standardprogramm des Systems.

    Windows: os.startfile, macOS: open, Linux/sonstige: xdg-open.
    """
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def escape_like(text: str) -> str:
    """Maskiert \\, % und _ fuer SQL ``LIKE ? ESCAPE '\\'``."""
    return (text.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_"))


def dir_filter_sql(column: str, directory: str) -> Tuple[str, List[str]]:
    """SQL-Bedingung: `column` ist `directory` selbst oder liegt darunter.

    Anders als ``LIKE directory || '%'`` matcht das keine Geschwister-Ordner
    (``docs`` vs. ``docs2``) und behandelt % / _ im Pfad nicht als Platzhalter.
    Beide Trennzeichen (/ und \\) werden beruecksichtigt.

    Returns:
        (sql, params) -- z.B. ``("(d.source_dir = ? OR ...)", [...])``
    """
    base = directory.rstrip("/\\")
    esc = escape_like(base)
    sql = (f"({column} = ? OR {column} LIKE ? ESCAPE '\\' "
           f"OR {column} LIKE ? ESCAPE '\\')")
    return sql, [base, esc + "/%", esc + "\\\\%"]


def fts5_quote(query: str) -> str:
    """Macht aus Freitext eine syntaktisch sichere FTS5-Query.

    Jedes Whitespace-Token wird in Anfuehrungszeichen gesetzt (innere " werden
    verdoppelt), z.B. ``COVID-19 c++`` -> ``"COVID-19" "c++"``.
    """
    return " ".join('"' + tok.replace('"', '""') + '"' for tok in query.split())


def move_to_trash(file_path: Any, trash_dir: Any) -> Path:
    """Verschiebt eine Datei in trash_dir (Name bei Kollision mit _1, _2, ...).

    Gibt den Zielpfad zurueck; Fehler (z.B. Datei gesperrt) werden geworfen.
    """
    trash_dir = Path(trash_dir)
    trash_dir.mkdir(parents=True, exist_ok=True)
    base_name = os.path.basename(str(file_path))
    name, ext = os.path.splitext(base_name)
    trash_path = trash_dir / base_name
    counter = 1
    while trash_path.exists():
        trash_path = trash_dir / f"{name}_{counter}{ext}"
        counter += 1
    shutil.move(str(file_path), str(trash_path))
    return trash_path
