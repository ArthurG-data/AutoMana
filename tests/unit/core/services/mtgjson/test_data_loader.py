import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from automana.core.services.app_integration.mtgjson.data_loader import download_all_identifiers


@pytest.mark.asyncio
async def test_download_all_identifiers_streams_to_fixed_path():
    dest = Path("/data/automana_data/mtgjson/raw/AllIdentifiers.json")

    api_repo = MagicMock()
    api_repo.fetch_all_identifiers_stream = AsyncMock(return_value=dest)

    storage_svc = MagicMock()
    storage_svc.build_path = MagicMock(return_value=dest)

    result = await download_all_identifiers(
        mtgjson_repository=api_repo,
        storage_service=storage_svc,
    )

    storage_svc.build_path.assert_called_once_with("AllIdentifiers.json")
    api_repo.fetch_all_identifiers_stream.assert_called_once_with(dest)
    assert result == {"identifiers_filename": "AllIdentifiers.json"}
