# Changelog

## [Unreleased]

## 2026-09-14

- **Repository Hygiene & Critical Scoping Fix (Pfad A)**:
  - Fixed `F823 UnboundLocalError` on `Path` in `digest.py` caused by inner import shadowing module-level variable in CLI `dups` command.
  - Resolved 24 code and import warnings across `digest.py`, `web_viewer.py`, `chunker.py`, `gemini_flash_summarizer.py`, `summarizer.py`, `launcher.py`, `gui/app.py`, `gui/main_window.py`, `gui/panels/document_list.py`, `gui/widgets/search_bar.py`, and test suites. `ruff check .` now passes with 0 issues.
- **Packaging & PEP 621 Standardization**:
  - Upgraded `pyproject.toml` with PEP 621 compliant metadata, `license = { text = "MIT" }`, Python 3.13 and OS classifiers.
  - Added grouped optional dependencies (`extract`, `gui`, `llm`, `test`, `all`).
  - Expanded `[project.urls]` with canonical links to Documentation, Architecture, Changelog, Security Policy, Parent Organization (`file-bricks`), and Umbrella Ecosystem (`open-bricks`).
  - Configured pytest default options (`addopts = "-ra -v"`).
- **CI Matrix Hardening (`.github/workflows/tests.yml`)**:
  - Replaced invalid action versions with official `actions/checkout@v4` and `actions/setup-python@v5`.
  - Added workflow-level `concurrency` with `cancel-in-progress: true` to prevent duplicate CI runs.
  - Added 15-minute job timeout and expanded Python test matrix to `["3.10", "3.11", "3.12", "3.13"]`.
- **Git & Multi-Host Sync Hygiene**:
  - Added `.gitignore` patterns for multi-host conflict artifacts (`*-ASUS-GEI*`, `*-WORKSTATION-LG*`, `*.sync-conflict-*`, `*.conflict`) and testing/linting caches (`.pytest_cache/`, `.ruff_cache/`, `.coverage`).
- **Security Policy Hardening**:
  - Updated `SECURITY.md` with supported versions table (0.4.x active support), response SLAs (48h acknowledgement, 5 business days triage), and local-first zero-egress invariants.
- **Contract Test Suite Expansion**:
  - Added `tests/test_metadata.py` with 8 automated contract tests covering PEP 621 structure, version parity, manifest integrity, bytecode compilation across all files, security policy clauses, CI workflow guardrails, and banner preservation (`HOOK-BANNER-ASSET-01`). Total test suite expanded to 148 passed tests.
- **Documentation & Badges**:
  - Synchronized test badges in `README.md` and `README_de.md` to 148 passed.
  - Refreshed `llms.txt` timestamp to 2026-09-14.

- Discoverability, Design & Architecture Enhancement (Path B).
- Updated test badges to 130 passed tests, added PySide6 and Architecture badges.
- Added comprehensive Ingestion & Retrieval Lifecycle Sequence Diagram (`mermaid`) to `README.md`, `README_de.md`, and `ARCHITECTURE.md`.
- Completed and enriched `## What It Does` section in `README.md` with detailed capabilities and value proposition.
- Validated all Mermaid diagrams with `lint_mermaid.py` (0 syntax issues).
- Synchronized `llms.txt` timestamp and architecture references.

## 2026-07-26

- Discoverability, SEO & README Design Audit (Path B).
- `README.md` & `README_de.md`: integrated Shields.io badges (Pytest 92 passed, Local-First, LLM-Ready), GFM LLM note callout (`> [!NOTE]`), and Mermaid system architecture diagram.
- `pyproject.toml`: added `[tool.pytest.ini_options]` with `pythonpath = "."` and `testpaths = ["tests"]`.
- `llms.txt`: updated `Last-checked` timestamp to `2026-07-26`.

## 2026-07-25

- Technical hygiene audit: verified Pytest test suite (92/92 passed cleanly).
- `llms.txt`: updated `Last-checked` timestamp to 2026-07-25.
- `.gitignore`: added patterns for host-specific local README copies (`README-*Studio.md`).

### Security
- Web viewer: state-changing routes (`/open/`, `/api/reset_doc/`, `/api/delete_file/`) are now POST-only (405 on GET — previously a simple `<img src>` GET could delete files), with a Host-header gate against DNS rebinding and an Origin/Referer gate against CSRF (empty Origin stays allowed so local CLI tools like curl keep working). Regression tests in `tests/test_web_viewer_security.py`.
- Web viewer: FTS5 search snippets are now HTML-escaped before `<mark>` highlighting is re-inserted (stored XSS via indexed document content).

### Changed
- Config discovery now honors `$XDG_CONFIG_HOME`/`~/.config/knowledgedigest/` on Linux/macOS (as the README already promised) and skips an empty `%APPDATA%`.
- The `summarize_model` config key is now passed through to the summarizer (was previously ignored).
- Server-specific deployment scripts removed from the public repository (kept privately).
- `llms.txt`: added `## Last-checked: 2026-06-11`, `## Audience` (5 groups), and `## Search Phrases` fenced code block (9 phrases).
- `README.md`: corrected BACH Integration link (`github.com/lukisch` → `github.com/ellmos-ai/bach`).

### Fixed
- `TODO.md` removed from Git tracking and added to `.gitignore` (contained internal audit paths).

## 2026-06-06

- Updated the test workflow to current `actions/checkout@v6` and `actions/setup-python@v6` majors.

## 2026-06-02

- Added packaging metadata so the repository can be installed as `knowledgedigest` while exposing the `KnowledgeDigest` package.
- Added GitHub Actions test workflow for Python 3.10, 3.11, and 3.12.
- Updated community workflow action versions.
- Corrected repository links from the former `lukisch` location to `file-bricks/knowledgedigest`.
- Aligned public docs with version `0.4.0` and cleaned visible encoding artifacts.

## 2026-05-17

- Added unit tests for core modules.

## 2026-05-01

- Added KnowledgeDigest icon and EXE build support.
- Backported v0.4.0 features from the local knowledge database line, including Gemini Flash summarization, deduplication, trash handling, and agent routing.
