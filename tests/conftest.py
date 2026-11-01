# -*- coding: utf-8 -*-
"""Pytest fixtures and configuration for KnowledgeDigest test suite."""

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Provide package fallback when running tests directly without editable install
if "KnowledgeDigest" not in sys.modules:
    pkg = types.ModuleType("KnowledgeDigest")
    pkg.__path__ = [str(REPO_ROOT)]
    sys.modules["KnowledgeDigest"] = pkg
