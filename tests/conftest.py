"""Pytest configuration for the Veeam ONE integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# GitHub Actions can invoke pytest without the repository root on sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/veeam_one."""
    yield
