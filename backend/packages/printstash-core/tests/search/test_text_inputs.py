"""Encoder identity extends text recipes without changing existing Spaces."""

import pytest

from printstash_core.inference import EmbeddingError, EmbeddingSpace
from printstash_core.search.text_inputs import TextRecipe


class TestTextRecipe:
    @pytest.mark.parametrize(
        "values",
        [
            {"passage_version": True},
            {"max_input_characters": 128.5},
            {"max_input_characters": "128"},
            {"encoder_manifest_sha256": 123},
        ],
    )
    def test_rejects_invalid_recipe_types(self, values):
        with pytest.raises(EmbeddingError, match="search_recipe_unavailable"):
            TextRecipe(**values)

    def test_preserves_recipe_identity_without_an_encoder(self):
        assert (
            TextRecipe().encode()
            == '{"max_input_characters":16384,"passage_version":1,"recipe":"semantic-text-v1"}'
        )

    def test_binds_local_recipes_to_the_encoder(self):
        recipe = TextRecipe(encoder_manifest_sha256="a" * 64)
        space = EmbeddingSpace(
            model_key="test",
            model_revision="v1",
            dimension=4,
            modality="text",
            render_recipe=recipe.encode(),
        )
        assert TextRecipe.for_space(space) == recipe
        assert '"encoder_manifest_sha256":"' + "a" * 64 + '"' in space.render_recipe

    @pytest.mark.parametrize("digest", ["", "a" * 63, "A" * 64, "g" * 64, "a" * 65])
    def test_rejects_malformed_encoder_digests(self, digest):
        with pytest.raises(EmbeddingError, match="search_recipe_unavailable"):
            TextRecipe(encoder_manifest_sha256=digest)
