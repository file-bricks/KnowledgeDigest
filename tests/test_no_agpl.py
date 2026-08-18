# SPDX-License-Identifier: MIT
"""Haelt die Lizenzentscheidung E08 dauerhaft fest.

KnowledgeDigest ist MIT-lizenziert. Die PDF-Vorschau im GUI-Panel importierte
frueher PyMuPDF (`fitz`, AGPL-3.0) -- eine geerbte Copyleft-Bindung, die in
einem als MIT ausgewiesenen Modul nicht auftauchen darf. Seit Entscheidung E08
(2026-08-18) laeuft das Rendering ausschliesslich ueber **pypdfium2**
(BSD-3-Clause / Apache-2.0), siehe gui/panels/preview_panel.py::_show_pdf.

Dieser Test verhindert, dass die Abhaengigkeit unbemerkt zurueckkehrt --
durch Copy-Paste aus einer AGPL-Anwendung (DokuZen, NoteSpaceLLM, LitZentrum,
wo PyMuPDF konsistent zur eigenen Lizenz genutzt wird) oder durch eine
bequeme Bibliothek. Ein Test statt einer Notiz, weil eine Notiz niemanden
aufhaelt.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Verzeichnisse, in denen kein eigener Quelltext liegt (Assets, Caches, Tests
# selbst duerfen theoretisch importieren, tun es hier aber ebenfalls nicht).
AUSGESCHLOSSEN = {"__pycache__", "mobile_icons", "assets", ".git"}

# Namen, die eine Copyleft-Bindung in ein ausgeliefertes MIT-Modul tragen wuerden.
VERBOTEN = {
    "fitz": "PyMuPDF (AGPL-3.0)",
    "pymupdf": "PyMuPDF (AGPL-3.0)",
    "PyMuPDF": "PyMuPDF (AGPL-3.0)",
}


def _modul_dateien() -> list[Path]:
    dateien = []
    for pfad in REPO_ROOT.rglob("*.py"):
        if any(teil in AUSGESCHLOSSEN for teil in pfad.relative_to(REPO_ROOT).parts):
            continue
        dateien.append(pfad)
    return sorted(dateien)


def test_paket_hat_dateien():
    assert _modul_dateien(), "Kein Quelltext gefunden -- Testpfad pruefen"


@pytest.mark.parametrize("datei", _modul_dateien(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_kein_copyleft_import(datei: Path):
    """Kein Modul importiert eine copyleft-gebundene Bibliothek."""
    baum = ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
    getroffen: list[str] = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for alias in knoten.names:
                wurzel = alias.name.split(".")[0]
                if wurzel in VERBOTEN:
                    getroffen.append(f"{wurzel} ({VERBOTEN[wurzel]})")
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            wurzel = knoten.module.split(".")[0]
            if wurzel in VERBOTEN:
                getroffen.append(f"{wurzel} ({VERBOTEN[wurzel]})")
    assert not getroffen, (
        f"{datei.relative_to(REPO_ROOT)} importiert copyleft-gebundene Bibliotheken: "
        f"{getroffen}. Entscheidung E08 vom 2026-08-18: PDF-Rendering laeuft ueber "
        "pypdfium2 (BSD-3-Clause / Apache-2.0)."
    )


def test_preview_panel_nutzt_pypdfium2():
    """Positivprobe: der vorgesehene permissive Renderer wird tatsaechlich genutzt."""
    quelle = (REPO_ROOT / "gui" / "panels" / "preview_panel.py").read_text(encoding="utf-8")
    assert "pypdfium2" in quelle, "preview_panel.py soll pypdfium2 zum PDF-Rendern verwenden"


def test_requirements_fuehrt_kein_pymupdf():
    """requirements.txt darf PyMuPDF nicht (mehr) als Abhaengigkeit fuehren."""
    quelle = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    zeilen = [z for z in quelle.splitlines() if "pymupdf" in z.lower()]
    assert not zeilen, f"requirements.txt fuehrt PyMuPDF: {zeilen}"
