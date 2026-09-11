"""Reviewed, immutable export contracts. Importing the catalog performs no I/O."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from printstash_core.inference import EmbeddingError

from app.modules.inference.manifest import TextModelManifest


@dataclass(frozen=True)
class DownloadAsset:
    filename: str
    source: str
    size: int
    sha256: str


@dataclass(frozen=True)
class RegistryEntry:
    manifest: TextModelManifest
    files: tuple[DownloadAsset, ...]

    @property
    def id(self) -> str:
        return self.manifest.space().config_hash

    @property
    def size(self) -> int:
        return sum(asset.size for asset in self.files) + len(
            self.manifest.model_dump_json().encode()
        )


@lru_cache(maxsize=1)
def entries() -> tuple[RegistryEntry, ...]:
    manifest = TextModelManifest.model_validate_json(
        (Path(__file__).parent / "registry" / "bge-small-en-v1.5.json").read_bytes()
    )
    return (
        RegistryEntry(
            manifest,
            (
                DownloadAsset(
                    "model.onnx",
                    "onnx/model.onnx",
                    133093490,
                    manifest.text.graph.sha256,
                ),
                DownloadAsset(
                    "tokenizer.json",
                    "tokenizer.json",
                    711396,
                    manifest.text.tokenizer.sha256,
                ),
            ),
        ),
    )


def require(key: str) -> RegistryEntry:
    for entry in entries():
        if key in (entry.id, entry.manifest.model_key):
            return entry
    raise EmbeddingError("embedding_model_not_found")
