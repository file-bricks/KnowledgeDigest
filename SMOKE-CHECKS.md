# Smoke-Checks: Web-Viewer und Desktop-GUI

Dieses Dokument beschreibt die Smoke-Checks für die beiden interaktiven
Frontends von KnowledgeDigest: den Web-Viewer und die Desktop-GUI.
Die Core-Unit-Tests (chunker, schema, config, utils) sind in `tests/test_core.py`
abgedeckt und laufen via `python -m pytest tests -q`.

---

## 1. Web-Viewer-Smoke-Check

### Zweck

Sicherstellen, dass der Web-Viewer korrekt startet, einen HTTP-Server auf
dem konfigurierten Port bindet und eine gültige HTML-Seite (Dashboard)
ausliefert — ausschließlich mit Python-Stdlib, ohne externe Abhängigkeiten.

- Modul: `web_viewer.py`
- Einstiegspunkt: `launch_web()` / `python -m KnowledgeDigest --web`
- Abhängigkeiten: **Python-Stdlib only** (kein Flask, kein Django)

### Voraussetzungen

```bash
python --version          # Python 3.10+ erforderlich
pip install -e .          # Paket installieren (kein weiteres pip-install nötig)
```

### Manueller Smoke-Check (interaktiv)

```bash
# Windows (PowerShell oder Git Bash):
PYTHONIOENCODING=utf-8 python -m KnowledgeDigest --web --no-browser
```

Option `--no-browser` verhindert das automatische Öffnen des Browsers.
Alternativer Port (falls 8787 belegt):

```bash
PYTHONIOENCODING=utf-8 python -m KnowledgeDigest --web --port 9000 --no-browser
```

Eigene Datenbankdatei angeben:

```bash
PYTHONIOENCODING=utf-8 python -m KnowledgeDigest --web --db pfad/zur/knowledge.db --no-browser
```

### Erwartete Konsolenausgabe

```
KnowledgeDigest Web-Viewer: http://127.0.0.1:8787
DB: data/knowledge.db
```

Der Prozess blockiert danach (HTTP-Server lauscht). Beenden mit **Ctrl+C**:

```
Viewer beendet.
```

### Erwartetes HTTP-Ergebnis

`GET http://127.0.0.1:8787/` liefert HTTP 200 mit HTML-Dashboard.

Prüfung via PowerShell (Windows, während der Server läuft):

```powershell
(Invoke-WebRequest -Uri http://127.0.0.1:8787/ -UseBasicParsing).StatusCode
# Erwartet: 200
```

Prüfung via Git Bash / curl (falls verfügbar):

```bash
curl -s -w "%{http_code}" http://127.0.0.1:8787/ -o nul
# Erwartet: 200
```

### Headless-Import-Check (CI-geeignet, ohne laufenden Server)

Prüft nur, ob das Modul fehlerfrei importierbar ist — startet keinen Server:

```bash
PYTHONIOENCODING=utf-8 python -c "from KnowledgeDigest.web_viewer import launch_web; print('OK')"
# Erwartet: OK
```

Dieser Check ist bereits indirekt im CI enthalten (`python -m compileall -q .`
und `python -m KnowledgeDigest --help`), testet aber keinen laufenden Server.

### Typische Fehler

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `OSError: [Errno 10048] / Address already in use` | Port 8787 belegt | `--port 9000` (oder freien Port wählen) |
| `sqlite3.OperationalError: no such table` | DB-Schema fehlt | `python -m KnowledgeDigest status` ausführen (initialisiert Schema) |
| `ModuleNotFoundError: No module named 'KnowledgeDigest'` | Paket nicht installiert | `pip install -e .` ausführen |
| `FileNotFoundError` (DB-Pfad) | Falsche DB-Konfiguration | `--db pfad/knowledge.db` explizit angeben |
| Leere Dokumentenliste im Browser | Normale Erstnutzung | `python -m KnowledgeDigest scan <verzeichnis>` ausführen |

---

## 2. Desktop-GUI-Smoke-Check

### Zweck

Sicherstellen, dass die PySide6-Anwendung korrekt startet, das Hauptfenster
öffnet und die 3-Panel-Ansicht (Verzeichnisse | Dokumente | Vorschau) mit
Dark-Theme und Toolbar anzeigt.

- Modul: `gui/app.py` (Einstieg: `launch_gui()`)
- Einstiegspunkt: `python -m KnowledgeDigest --gui`
- Abhängigkeit: **PySide6** (nicht Stdlib — muss installiert sein)
- Voraussetzung: **Grafisches Display** muss verfügbar sein (kein reines Headless-CI)

### Voraussetzungen

```bash
python --version          # Python 3.10+ erforderlich
pip install -e .          # Paket + Kern-Abhängigkeiten installieren
pip install PySide6       # GUI-Abhängigkeit (LGPL)
```

### Manueller Smoke-Check (interaktiv)

```bash
# Windows (PowerShell oder Git Bash):
PYTHONIOENCODING=utf-8 python -m KnowledgeDigest --gui
```

Alternativ über das mitgelieferte Windows-Startskript:

```bat
start.bat
```

(`start.bat` liegt im Elternordner des Projektverzeichnisses und ruft
`launcher.py` auf, der seinerseits die GUI startet.)

### Erwartetes Verhalten

Nach dem Start (keine Konsolenausgabe erwartet):

1. Anwendungsfenster öffnet sich (Mindestgröße 900 × 600 px).
2. Dark-Theme ist aktiv (Hintergrundfarbe `#0d1117`).
3. Toolbar sichtbar mit den Aktionen „+ Verzeichnis" und „Scannen", einem Suchfeld
   (Platzhaltertext „Suche (FTS5)...") sowie den Aktionen „Web-Viewer" und „Einstellungen".
4. 3-Panel-Splitter: Links Verzeichnisliste, Mitte Dokumententabelle, Rechts Vorschau.
5. Statusleiste am unteren Rand zeigt eine Bereitschaftsmeldung.
6. Schließen des Fensters beendet die Anwendung sauber (Exit-Code 0).

### Headless-Import-Check (CI-geeignet, ohne Display)

Prüft den Import aller GUI-Module ohne einen QApplication-Start:

```bash
PYTHONIOENCODING=utf-8 python -c "from KnowledgeDigest.gui.app import launch_gui; print('OK')"
# Erwartet: OK  (schlägt fehl, wenn PySide6 nicht installiert ist)
```

**Hinweis:** Der vollständige GUI-Start (`launch_gui()`) erfordert einen
aktiven Display-Server. In headless CI-Umgebungen (z. B. GitHub Actions
Ubuntu-Runner ohne Virtual Display) schlägt `python -m KnowledgeDigest --gui`
mit einem Qt-Fehler fehl — das ist kein Anwendungsfehler:

```
qt.qpa.xcb: could not connect to display
```

Der CI-Workflow (`tests.yml`) enthält deshalb keinen vollständigen GUI-Start.
Der Import-Check oben ist der höchste CI-taugliche Prüfpunkt ohne Xvfb-Setup.

### Typische Fehler

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `ModuleNotFoundError: No module named 'PySide6'` | PySide6 nicht installiert | `pip install PySide6` |
| `qt.qpa.xcb: could not connect to display` | Kein grafisches Display (Linux CI) | Nur im interaktiven Kontext ausführen; kein CI-Fehler |
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | Fehlende Qt-Plattform-Bibliotheken (Linux) | PySide6 neu installieren oder `libxcb`-Pakete via apt prüfen |
| `FileNotFoundError: KnowledgeDigest.ico` | App-Icon nicht vorhanden | Kein funktionaler Fehler — GUI startet trotzdem ohne Icon |
| `ModuleNotFoundError: No module named 'KnowledgeDigest'` | Paket nicht installiert | `pip install -e .` ausführen |
| `ModuleNotFoundError: No module named 'fitz'` | PyMuPDF fehlt (PDF-Vorschau) | `pip install PyMuPDF` (optional, nur für PDF-Vorschau im Preview-Panel) |
| Leere Dokumentenliste nach Start | Normale Erstnutzung | Verzeichnis über Toolbar-Schaltfläche „+" hinzufügen und scannen |

---

## Abgrenzung: Was dieser Check NICHT testet

- **Core-Logik** (Chunker, Schema, Config, Utils): Abgedeckt durch `tests/test_core.py`
  (`python -m pytest tests -q`).
- **LLM-Summarization** (Haiku/Flash): Erfordert API-Schlüssel — kein Teil des Smoke-Checks.
- **BACH-Integration**: Optionales Modul, deaktiviert per Default (`bach_enabled: false`).
- **Vollständige End-to-End-Tests** (Ingest → Suche → Ergebnis): Nicht enthalten;
  diese würden eigene Integrationstests erfordern.

---

*Erstellt 2026-06-28. Basis: `web_viewer.py` (launch\_web), `gui/app.py` (launch\_gui),
`__main__.py`, `.github/workflows/tests.yml`.*
