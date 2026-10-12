# Security Policy — KnowledgeDigest

## Supported Versions

| Version | Status |
|---|---|
| 0.4.x | Current maintenance line |

## Scope and Runtime Notes

Document extraction, chunking, indexing, and FTS5 search operate on the configured local SQLite database. Optional summarization is a separate network boundary: the CLI defaults to Anthropic, --flash selects Google GenAI, and the Python API supports Ollama or a custom endpoint. Selected document text and prompts are sent to the configured provider when summarization is invoked. Custom endpoints may be remote.

The standard-library web viewer currently binds to 127.0.0.1 and checks request headers for state-changing routes. It uses HTTP without TLS and is not an authenticated remote service or an operating-system sandbox. Do not expose it to other hosts without a separate review.

These notes describe reviewed source paths; they do not certify a deployment, dependency set, or user configuration.

## Reporting a Vulnerability

Check the repository’s Security tab to see whether GitHub Private Vulnerability Reporting is enabled. If enabled, use its private report form. If it is unavailable, do not publish vulnerability details in a public issue; ask the maintainers for a private contact route.

Include the affected version, relevant component, reproducible steps, and impact. Avoid attaching private documents, credentials, or unrelated personal data.

## Response Expectations

Maintainers aim to acknowledge reports within 48 hours and complete initial triage within five business days. When a fix is appropriate, they aim to coordinate a release before public disclosure. These are maintainer targets, not guaranteed service levels; investigation and release timing depend on severity, reproducibility, and capacity.
