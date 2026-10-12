import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_application_icon_is_declared_as_package_data():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(
        r'(?ms)^\[tool\.setuptools\.package-data\]\s*KnowledgeDigest\s*=\s*\["KnowledgeDigest\.ico"\]',
        pyproject,
    )
    icon = REPO_ROOT / "KnowledgeDigest.ico"
    assert icon.is_file()
    assert icon.stat().st_size > 0
