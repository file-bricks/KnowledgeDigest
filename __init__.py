# -*- coding: utf-8 -*-
"""
KnowledgeDigest -- Portable Wissensdatenbank.

Indexiert Dokumente (PDF, DOCX, TXT, MD, HTML), chunked den Content
und macht ihn durchsuchbar via FTS5-Volltextsuche.

Usage:
    from KnowledgeDigest import KnowledgeDigest

    kd = KnowledgeDigest()
    kd.add_directory("/path/to/docs")
    kd.scan_directory("/path/to/docs")
    results = kd.search_all("suchbegriff")

    # GUI starten: python -m KnowledgeDigest --gui
    # Web-Viewer:  python -m KnowledgeDigest --web

Author: Lukas Geiger
License: MIT
"""

try:
    from .digest import KnowledgeDigest
except ImportError:
    # Ohne Paket-Kontext (z.B. wenn pytest __init__.py direkt importiert):
    # KnowledgeDigest bleibt undefiniert; normaler Package-Import ist nicht betroffen.
    pass  # type: ignore[assignment]

__version__ = "0.4.0"
__all__ = ["KnowledgeDigest"]
