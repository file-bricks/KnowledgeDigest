# Third-Party Licenses & Level 1 SBOM Inventory

**Project:** `KnowledgeDigest` (Portable Local Knowledge Database & Full-Text Search Engine)  
**License:** [MIT License](LICENSE)  
**Audit Date:** 2026-09-22  
**Repository:** [file-bricks/KnowledgeDigest](https://github.com/file-bricks/knowledgedigest)  
**Organization:** [file-bricks](https://github.com/file-bricks)  
**Umbrella Ecosystem:** [open-bricks](https://github.com/open-bricks)  
**Author:** Lukas Geiger ([github.com/lukisch](https://github.com/lukisch))  

---

## 1. Runtime Architecture & Zero-Cloud Core

`KnowledgeDigest` is an offline-first, local-first document indexing and retrieval application built with Python 3.10+, SQLite FTS5, and PySide6. The application runs entirely on the user's local workstation, persists indexed document chunks in a self-contained SQLite database (`data/knowledge.db`), and exposes both a native desktop GUI and a zero-dependency Python standard library Web Viewer (`web_viewer.py` on `http://localhost:8787`).

Under default configuration, zero network calls are performed. Optional LLM summarization (`--flash` via Google GenAI or `--haiku` via Anthropic) is strictly opt-in and operates only when the user explicitly provides API credentials.

---

## 2. Direct Runtime Dependencies

All direct runtime dependencies are distributed under permissive open-source licenses (MIT, Apache-2.0, BSD-3-Clause, LGPL-3.0, PSFL). No viral copyleft (GPL, AGPL) components are bundled into the distribution:

| Component / Package | License | Project URL | Purpose |
|---|---|---|---|
| **Python Standard Library** | PSFL-2.0 | [python.org](https://www.python.org/) | Runtime execution, SQLite (`sqlite3`), HTTP Web Viewer (`http.server`), cryptographic hashing (`hashlib`). |
| **`pdfplumber`** | MIT | [jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) | Deep text and layout extraction from PDF files. |
| **`PyPDF2`** | BSD-3-Clause | [py-pdf/pypdf](https://github.com/py-pdf/pypdf) | Fallback PDF stream extraction and structural parsing. |
| **`python-docx`** | MIT | [python-openxml/python-docx](https://github.com/python-openxml/python-docx) | Text and metadata extraction from Microsoft Word (`.docx`) files. |
| **`beautifulsoup4`** | MIT | [wention/BeautifulSoup4](https://git.launchpad.net/beautifulsoup) | HTML document parsing and boilerplate stripping. |
| **`PySide6` / Qt6** | LGPL-3.0 | [qt.io](https://www.qt.io/) | Native 3-panel desktop GUI interface with dark theme. Dynamically linked in compliance with LGPL-3.0 Section 4. |
| **`pypdfium2`** | Apache-2.0 / BSD-3-Clause | [pypdfium2-team/pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | In-app GUI PDF preview rendering (Decision E08: explicitly selected over PyMuPDF / AGPL-3.0 to keep distribution 100% free of copyleft). |
| **`anthropic`** (optional) | MIT | [anthropics/anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python) | Optional Claude Haiku batch summarization client. |
| **`google-genai`** (optional) | Apache-2.0 | [googleapis/python-genai](https://github.com/googleapis/python-genai) | Optional Gemini Flash batch summarization client. |

---

## 3. Development, Testing & Verification Dependencies

The following tools are utilized strictly during development, automated testing, and CI verification pipelines:

| Tool / Framework | License | Project URL | Purpose |
|---|---|---|---|
| **`pytest`** | MIT | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | Test execution and metadata contract test suite. |
| **`ruff`** | MIT / Apache-2.0 | [astral-sh/ruff](https://github.com/astral-sh/ruff) | High-performance Python linting and code formatting enforcement. |

---

## 4. Invariant Cross-Reference Matrix

KnowledgeDigest enforces ten core governance and runtime invariants across its architecture and codebase:

| Invariant Code | Category | Description & Technical Implementation | Verification Method |
|---|---|---|---|
| **`INV-LOCAL-01`** | Data Privacy | **Local-First & Zero Egress**: All parsing, indexing, and SQLite FTS5 queries execute strictly on the local machine. Zero background telemetry or tracking. | `tests/test_core.py`, `SECURITY.md` |
| **`INV-SQLITE-02`** | Storage Engine | **ACID SQLite FTS5 Full-Text Engine**: Persistent indexed chunks, keywords, and metadata in `data/knowledge.db` with BM25 snippet ranking and auto-sync triggers. | `KnowledgeDigest/schema.py`, `tests/test_core.py` |
| **`INV-CHUNK-03`** | Natural Language | **Sentence-Bounded Semantic Chunking**: Text segmentation into ~350-word chunks respecting natural punctuation and paragraph boundaries without mid-sentence chops. | `KnowledgeDigest/chunker.py`, `tests/test_core.py` |
| **`INV-COPYLEFT-04`** | Licensing | **Zero-Copyleft Isolation Guarantee**: 100% Permissive MIT distribution. Decision E08 mandates `pypdfium2` over PyMuPDF (`fitz`), and PySide6 is dynamically linked. | `tests/test_no_agpl.py` |
| **`INV-RUNAS-05`** | Security | **Unprivileged Execution (`RunAsInvoker`)**: Operates exclusively in user space without administrator, root, or elevated privileges. | `SECURITY.md` |
| **`INV-DUAL-06`** | User Interface | **Dual Frontends**: PySide6 Desktop GUI (3-panel layout) + Python stdlib zero-dependency Web Viewer (`http://localhost:8787`). | `KnowledgeDigest/gui/`, `KnowledgeDigest/web_viewer.py` |
| **`INV-OPTLLM-07`** | Extensibility | **Optional LLM Boundary**: Complete search, indexing, and browsing functionality works 100% offline without any LLM; optional Gemini Flash / Haiku batch queues. | `KnowledgeDigest/summarizer.py`, `tests/test_flash_summarizer.py` |
| **`INV-DEDUPE-08`** | Data Integrity | **Cryptographic Deduplication & Quarantine**: SHA-256 hash calculation for all indexed documents with non-destructive `_Papierkorb` duplicate isolation. | `KnowledgeDigest/digest.py`, `tests/test_core.py` |
| **`INV-DOCS-09`** | Documentation | **100% Bilingual Documentation Parity**: 18-point dual-anchor navigation parity between English (`README.md`) and German (`README_de.md`). | `tests/test_metadata.py` |
| **`INV-SLA-10`** | Governance | **Statutory Disclaimer & 48h Security SLA**: German statutory disclaimer (§ 521 BGB Gefälligkeitsrecht) and guaranteed 48-hour response SLA. | `SECURITY.md`, `README.md`, `README_de.md` |

---

## 5. Zero-Copyleft Guarantee & Unprivileged Execution

- **Zero-Copyleft Guarantee:** All source code, interfaces, CLI scripts, and manifests in this repository are licensed under the permissive [MIT License](LICENSE). In adherence to Decision E08 (2026-08-18), no AGPL or viral copyleft libraries (such as `PyMuPDF`/`fitz`) are permitted in the distribution. Automated regression tests (`tests/test_no_agpl.py`) continuously enforce this invariant.
- **Unprivileged User Mode (`RunAsInvoker`):** `KnowledgeDigest` runs entirely within standard user permissions. It does not install kernel drivers, background daemons, root services, or modify system-wide registry keys.
- **Data Isolation:** All persistent runtime databases, indices, and configuration files reside in `data/` or user-specified local directories and are strictly excluded from Git tracking via `.gitignore`.
