# Direct Dependency and License Notes

**Project:** KnowledgeDigest
**Project-source license:** MIT (see LICENSE)
**Snapshot date:** 2026-10-12
**Scope:** Declared direct packages in pyproject.toml extras and the optional SQLite Transit adapter.

This is a manually maintained, bounded reference list. It is not a generated SBOM, a complete dependency inventory, or a legal compliance assessment. It does not enumerate transitive packages, platform-specific binary contents, or every license option offered by upstream projects. Before redistribution, inspect the license files and metadata of the exact distributions being shipped.

## Declared direct optional packages

| Package | Declared use | Upstream license reference (bounded note) |
|---|---|---|
| pdfplumber | PDF text/layout extraction (extract) | MIT |
| PyPDF2 | PDF parsing fallback (extract) | BSD-3-Clause |
| python-docx | DOCX extraction (extract) | MIT |
| beautifulsoup4 | HTML parsing (extract) | MIT |
| [PySide6](https://doc.qt.io/qtforpython-6/licenses.html) | Desktop GUI (gui) | Qt for Python has LGPLv3/GPLv3 and commercial licensing options, plus components under original licenses; inspect the selected distribution's license files. |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | GUI PDF preview (gui) | Upstream provides Apache-2.0 / BSD-3-Clause notices; inspect the selected distribution. |
| anthropic | Optional Anthropic summarization client (llm) | MIT |
| google-genai | Optional Google GenAI summarization client (llm) | Apache-2.0 |
| pytest | Tests (test) | MIT |

The sqlite-transit-sync adapter is imported optionally by transit.py and is not on PyPI; its project and license metadata are maintained at https://github.com/ellmos-ai/sqlite-transit-sync. It is separate from the default indexing/search path.

## Source and runtime boundaries

- The repository source declares MIT in LICENSE and package metadata.
- The tests/test_no_agpl.py guard checks selected source files for explicit imports of fitz, pymupdf, and PyMuPDF. It does not inspect the dependency graph, downloaded wheels, native libraries, or transitive package licenses.
- Choosing pypdfium2 means the project does not declare PyMuPDF for PDF preview. This is not a guarantee that every possible environment is free of copyleft components.
- Optional summarization sends selected document chunks and prompts to the configured provider when invoked. Optional SQLite Transit can transfer configured snapshots between nodes.

For an actual release or bundled application, generate and review an inventory of the exact build artifacts and their included license files. This document alone is not that review.

## Attribution

See NOTICE for project attribution.
