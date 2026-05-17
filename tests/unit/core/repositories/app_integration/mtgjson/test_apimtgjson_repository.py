"""Unit tests for ApimtgjsonRepository.

W1: name() is a plain method, not a @property. This breaks any caller that
    accesses repo.name (e.g. service registry lookups that treat name as a
    property consistent with other repositories).
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from automana.core.repositories.app_integration.mtgjson.Apimtgjson_repository import (
    ApimtgjsonRepository,
)


def test_name_is_a_property():
    """W1: ApimtgjsonRepository.name must be a @property, not a plain method."""
    assert isinstance(
        ApimtgjsonRepository.__dict__.get("name"), property
    ), "name should be a @property so repo.name returns the string directly"


def test_name_returns_correct_string():
    repo = ApimtgjsonRepository(environment="test")
    assert repo.name == "ApimtgjsonRepository"


@pytest.mark.asyncio
async def test_fetch_all_identifiers_stream_calls_stream_download():
    repo = ApimtgjsonRepository(environment="test")
    dest = Path("/tmp/AllIdentifiers.json")

    with patch.object(repo, "stream_download", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = dest
        result = await repo.fetch_all_identifiers_stream(dest)

    mock_dl.assert_called_once_with("AllIdentifiers.json", dest)
    assert result == dest
