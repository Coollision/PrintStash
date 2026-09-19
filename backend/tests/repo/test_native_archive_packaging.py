"""The native archive kernel remains part of the production wheel build."""

from __future__ import annotations

from tests.paths import REPO_ROOT


def test_packages_archive_core_in_the_native_wheel() -> None:
    dockerfile = (REPO_ROOT / "backend" / "Dockerfile").read_text()

    assert "COPY rust/archive-core ./archive-core" in dockerfile
