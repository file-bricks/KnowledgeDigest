# Security Policy — KnowledgeDigest

## Supported Versions

| Version | Supported |
| --- | --- |
| 0.4.x | :white_check_mark: Active security support |
| < 0.4.0 | :x: End of life (please upgrade) |

## Security Invariants & Architecture

KnowledgeDigest is engineered around local-first data integrity:

1. **Zero Egress by Default**: All document parsing, text chunking, and SQLite FTS5 search indexing occur 100% locally on your machine. No telemetry, usage statistics, or automated background telemetry calls are ever made.
2. **Explicit LLM Boundary**: External network calls only happen when the user explicitly configures and invokes LLM summarization (`--flash` via Google GenAI or `--haiku` via Anthropic).
3. **Web Viewer Hardening**:
   - State-changing endpoints (`/open/`, `/api/reset_doc/`, `/api/delete_file/`) strictly enforce HTTP POST (HTTP 405 on GET).
   - Host header validation mitigates DNS rebinding attacks.
   - Origin / Referer checks protect against Cross-Site Request Forgery (CSRF).
   - Search snippet outputs are escaped prior to `<mark>` tag injection to prevent stored XSS.
4. **Unprivileged Execution**: KnowledgeDigest runs as a standard user process (`RunAsInvoker`) without requiring elevated or root permissions.

## Reporting a Vulnerability

If you discover a potential security vulnerability, please report it responsibly:

1. **Do NOT open a public issue.**
2. **Use GitHub Private Vulnerability Reporting**:
   Navigate to [GitHub Advisory Submission](https://github.com/file-bricks/knowledgedigest/security/advisories/new).
3. Provide details:
   - Component / module affected (e.g. `web_viewer.py`, `chunker.py`, `digest.py`)
   - Steps to reproduce or proof-of-concept
   - Potential impact and severity assessment

## Service Level Agreements (SLAs)

- **Initial Response**: Within 48 hours of report submission.
- **Triage & Assessment**: Within 5 business days.
- **Patch Deployment**: Security fixes will be released on `main` and tagged in a timely manner before coordinated disclosure.
