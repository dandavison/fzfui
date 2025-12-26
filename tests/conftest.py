"""Pytest configuration for snitchi tests."""

import pytest


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )


@pytest.fixture(scope="session")
def check_dependencies():
    """Check that required dependencies are available."""
    import shutil

    missing = []

    if not shutil.which("tmux"):
        missing.append("tmux")
    if not shutil.which("snitch"):
        missing.append("snitch")
    if not shutil.which("fzf"):
        missing.append("fzf")

    if missing:
        pytest.skip(f"Missing required dependencies: {', '.join(missing)}")

