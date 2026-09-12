"""An actual installation serves Search and an independent consumer without Similar Models."""

import os
import shutil
import subprocess
import sys

from tests.factories.embeddings import local_embedding_assets
from tests.paths import BACKEND_DIR


class TestSearchIndependence:
    def test_runs_without_the_similarity_package(self, tmp_path):
        isolated = tmp_path / "installation"
        shutil.copytree(
            BACKEND_DIR / "app",
            isolated / "app",
            ignore=lambda _directory, names: set(names) & {"__pycache__", "similarity"},
        )
        assets = local_embedding_assets(tmp_path / "preplaced-model")
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(isolated), str(BACKEND_DIR))),
            "VAULT_DB_URL": f"sqlite:///{tmp_path / 'vault.sqlite'}",
            "VAULT_SETUP_MODE": "trusted_network",
            "VAULT_SETUP_ALLOWED_HOSTS": "testserver",
            "VAULT_SECRETS_KEY": "independent-consumer-test-key",
            "VAULT_SECRETS_KEY_FILE": str(tmp_path / "secrets-key"),
            "VAULT_EMBEDDING_LOCAL_MODEL_DIR": str(assets),
            "VAULT_EMBEDDING_MODEL_KEY": "two-tower-contract",
            "VAULT_EMBEDDING_ONNX_THREADS": "1",
            "VAULT_EMBEDDING_DOWNLOAD_ENABLED": "false",
            "VAULT_AI_SEARCH_ENABLED": "false",
        }
        for key in (
            "DATA_DIR",
            "THUMB_DIR",
            "STAGING_DIR",
            "BACKUP_DIR",
            "ARTIFACT_CACHE_ROOT",
            "EMBEDDING_CACHE_DIR",
        ):
            directory = tmp_path / key.lower()
            directory.mkdir()
            environment[f"VAULT_{key}"] = str(directory)
        result = subprocess.run(
            [sys.executable, "-m", "tests.fakes.independent_search_consumer"],
            cwd=isolated,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "independent-search-consumer-complete" in result.stdout
