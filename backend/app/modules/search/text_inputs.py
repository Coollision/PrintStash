"""Immutable text recipes, with explicit provider-budget truncation."""

import json
from dataclasses import dataclass

from printstash_core.inference import EmbeddingError, EmbeddingInput, EmbeddingSpace
from printstash_core.search.passages import RECIPE_VERSION


@dataclass(frozen=True)
class TextRecipe:
    passage_version: int = RECIPE_VERSION
    max_input_characters: int = 16384
    recipe: str = "semantic-text-v1"

    def __post_init__(self):
        if (
            self.recipe != "semantic-text-v1"
            or self.passage_version != RECIPE_VERSION
            or not 128 <= self.max_input_characters <= 16384
        ):
            raise EmbeddingError("search_recipe_unavailable")

    def encode(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))

    @classmethod
    def for_space(cls, space: EmbeddingSpace):
        try:
            return cls(**json.loads(space.render_recipe))
        except (TypeError, ValueError):
            raise EmbeddingError("search_recipe_unavailable") from None


def document_input(space: EmbeddingSpace, text: str) -> tuple[EmbeddingInput, bool]:
    recipe = TextRecipe.for_space(space)
    budget = recipe.max_input_characters - len(space.document_prefix)
    if budget <= 0:
        raise EmbeddingError("search_prefix_exceeds_budget")
    return EmbeddingInput("text", text=space.document_prefix + text[:budget]), len(
        text
    ) > budget
