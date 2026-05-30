import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from automana.core.services.app_integration.mtgjson.data_loader import (
    cleanup_staging_db,
    download_all_identifiers,
)


@pytest.mark.asyncio
async def test_download_all_identifiers_streams_to_fixed_path():
    dest = Path("/data/automana_data/mtgjson/raw/AllIdentifiers.json")

    api_repo = MagicMock()
    api_repo.fetch_all_identifiers_stream = AsyncMock(return_value=dest)

    storage_svc = MagicMock()
    storage_svc.build_path = MagicMock(return_value=dest)

    result = await download_all_identifiers(
        mtgjson_repository=api_repo,
        ops_repository=AsyncMock(),
        storage_service=storage_svc,
    )

    storage_svc.build_path.assert_called_once_with("AllIdentifiers.json")
    api_repo.fetch_all_identifiers_stream.assert_called_once_with(dest)
    assert result == {"identifiers_filename": "AllIdentifiers.json"}


@pytest.mark.asyncio
async def test_cleanup_staging_db_returns_deleted_count():
    repo = MagicMock()
    repo.truncate_staging_after_promotion = AsyncMock(return_value=500)

    result = await cleanup_staging_db(mtgjson_repository=repo, ops_repository=AsyncMock())

    repo.truncate_staging_after_promotion.assert_called_once()
    assert result == {"staging_rows_deleted": 500}


@pytest.mark.asyncio
async def test_cleanup_staging_db_zero_rows():
    repo = MagicMock()
    repo.truncate_staging_after_promotion = AsyncMock(return_value=0)

    result = await cleanup_staging_db(mtgjson_repository=repo, ops_repository=AsyncMock())

    assert result == {"staging_rows_deleted": 0}
