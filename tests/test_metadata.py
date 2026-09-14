# -*- coding: utf-8 -*-
"""
Contract and metadata tests for KnowledgeDigest (Pfad A).
Validates PEP 621 compliance, version parity, manifest consistency,
workflow constraints, and banner guardrails.
"""

import json
from pathlib import Path
import py_compile
import re

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_pyproject() -> dict:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.is_file(), "pyproject.toml must exist"
    try:
        import tomllib
        with open(pyproject_path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        try:
            import tomli as tomllib
            with open(pyproject_path, "rb") as f:
                return tomllib.load(f)
        except ImportError:
            # Minimal fallback parser for core fields
            content = pyproject_path.read_text(encoding="utf-8")
            data = {"project": {}, "project.urls": {}}
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("name ="):
                    data["project"]["name"] = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("version ="):
                    data["project"]["version"] = line.split("=", 1)[1].strip().strip('"')
            return data


def test_pyproject_pep621_structure():
    """Verify PEP 621 compliant pyproject.toml fields."""
    config = _load_pyproject()
    project = config.get("project", {})

    assert project.get("name") == "knowledgedigest"
    assert project.get("version") == "0.4.0"
    assert project.get("requires-python") == ">=3.10"
    assert project.get("readme") == "README.md"

    # License check
    license_field = project.get("license")
    assert license_field == {"text": "MIT"} or license_field == "MIT"

    # URLs check
    urls = project.get("urls", {})
    assert "Homepage" in urls
    assert "Repository" in urls
    assert "Issues" in urls
    assert "Documentation" in urls
    assert "Architecture" in urls
    assert "Changelog" in urls
    assert "Security" in urls
    assert "Parent Organization" in urls
    assert "Umbrella Ecosystem" in urls


def test_version_parity():
    """Ensure version parity between package __init__.py and pyproject.toml."""
    config = _load_pyproject()
    pyproject_version = config.get("project", {}).get("version")

    init_file = REPO_ROOT / "__init__.py"
    assert init_file.is_file(), "__init__.py must exist"
    init_content = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_content)
    assert match, "__version__ not found in __init__.py"
    assert match.group(1) == pyproject_version, f"Version mismatch: {match.group(1)} != {pyproject_version}"


def test_ellmos_module_v2_manifest():
    """Ensure ellmos-module.v2.json exists and is aligned."""
    manifest_path = REPO_ROOT / "ellmos-module.v2.json"
    assert manifest_path.is_file(), "ellmos-module.v2.json must exist"

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("schema") == "ellmos.module.v2"
    assert data.get("id") == "KnowledgeDigest"

    repo_url = data.get("source_of_truth", {}).get("repository")
    assert repo_url == "https://github.com/file-bricks/knowledgedigest"


def test_all_python_files_compile():
    """Verify that all tracked Python files compile to valid bytecode without syntax errors."""
    python_files = list(REPO_ROOT.glob("*.py")) + list(REPO_ROOT.glob("gui/**/*.py")) + list(REPO_ROOT.glob("tests/**/*.py"))
    assert len(python_files) >= 15, "Expected at least 15 Python files in repository"

    for py_file in python_files:
        # Ignore temporary or cache files if any
        if any(part.startswith(".") or part in ("venv", ".venv", "build", "dist") for part in py_file.parts):
            continue
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as exc:
            raise AssertionError(f"Bytecode compilation failed for {py_file}: {exc}") from exc


def test_security_policy_structure():
    """Ensure SECURITY.md contains supported versions, SLA, and security invariants."""
    sec_file = REPO_ROOT / "SECURITY.md"
    assert sec_file.is_file(), "SECURITY.md must exist"
    sec_text = sec_file.read_text(encoding="utf-8")

    assert "Supported Versions" in sec_text
    assert "0.4.x" in sec_text
    assert "48 hours" in sec_text
    assert "5 business days" in sec_text
    assert "Zero Egress" in sec_text
    assert "RunAsInvoker" in sec_text or "Unprivileged Execution" in sec_text


def test_ci_workflow_integrity():
    """Ensure .github/workflows/tests.yml specifies required guardrails."""
    workflow_file = REPO_ROOT / ".github" / "workflows" / "tests.yml"
    assert workflow_file.is_file(), "tests.yml workflow must exist"
    content = workflow_file.read_text(encoding="utf-8")

    assert "timeout-minutes: 15" in content
    assert "cancel-in-progress: true" in content
    assert "actions/checkout@v4" in content
    assert "actions/setup-python@v5" in content
    assert "actions/checkout@v6" not in content
    assert "actions/setup-python@v6" not in content
    assert "3.13" in content


def test_banner_and_asset_guardrail():
    """Verify banner assets exist and are referenced without duplication (HOOK-BANNER-ASSET-01)."""
    banner_png = REPO_ROOT / "assets" / "banner.png"
    banner_svg = REPO_ROOT / "assets" / "banner.svg"

    assert banner_png.is_file(), "assets/banner.png must exist"
    assert banner_svg.is_file(), "assets/banner.svg must exist"
    assert banner_png.stat().st_size > 0, "assets/banner.png must not be empty"
    assert banner_svg.stat().st_size > 0, "assets/banner.svg must not be empty"

    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    banner_matches = re.findall(r'(?:<img[^>]+banner|\!\[[^\]]*banner[^\]]*\])', readme_text, re.IGNORECASE)
    assert len(banner_matches) == 1, f"Expected exactly 1 banner in README.md, found {len(banner_matches)}"
