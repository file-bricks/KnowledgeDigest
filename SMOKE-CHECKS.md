# Smoke checks: web viewer, desktop GUI, and installed package

These checks cover selected startup and packaging behavior. They do not exercise provider APIs, real user databases, or a full security boundary.

## Web viewer

Install the core package, then run the local viewer with a test database in a writable temporary directory:

    python -m KnowledgeDigest --web --db C:/Temp/knowledgedigest-smoke.db --no-browser

The current implementation binds to 127.0.0.1 and serves local HTTP without TLS. While it is running, request the dashboard from the same machine and confirm an HTTP 200 response. Stop it with Ctrl+C. Do not expose it through a reverse proxy without a separate security review.

The viewer can create or initialize the selected database. Use a disposable path for this check.

## Desktop GUI

Install the optional GUI dependencies:

    python -m pip install -e ".[gui]"

Then launch:

    python -m KnowledgeDigest --gui

The current desktop UI strings are German-only. A graphical display is required. The application icon is expected to load from the installed KnowledgeDigest package; the packaging smoke script checks this in an offscreen Qt session.

## Installed wheel and source distribution

The CI packaging job builds both artifacts, checks that each contains KnowledgeDigest.ico, installs each into a separate target directory, and runs the CLI help and icon smoke checks from outside the source tree. It does not open a real profile database or call a provider.

## Scope limits

- Optional summarize commands are not part of this smoke check; they can send selected document text and prompts to the configured provider.
- Optional BACH import and SQLite Transit synchronization require their own configured data and are not exercised here.
- A successful startup check does not establish security, licensing, or privacy compliance.
