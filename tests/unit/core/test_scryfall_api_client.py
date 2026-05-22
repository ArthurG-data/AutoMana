"""Unit tests for ScryfallAPIRepository.

Covers the three public surfaces:
  - migrations_to_bytes_buffer: TSV format and note sanitisation
  - download_data_from_url: URL construction and JSON return
  - stream_download: async context manager yields chunked bytes
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from automana.core.repositories.app_integration.scryfall.ApiScryfall_repository import (
    ScryfallAPIRepository,
)

_MIGRATION = {
    "id": "mig-001",
    "uri": "https://api.scryfall.com/migrations/mig-001",
    "performed_at": "2025-01-15",
    "migration_strategy": "merge",
    "old_scryfall_id": "old-uuid",
    "new_scryfall_id": "new-uuid",
    "note": "Cards were merged.",
}

_MIGRATION_DIRTY_NOTE = {**_MIGRATION, "note": "Line one\ttab\nLine two"}


@pytest.fixture
def repo():
    return ScryfallAPIRepository()


class TestMigrationsToByteBuffer:
    async def test_produces_nine_tab_separated_fields(self, repo):
        async def _fake():
            yield _MIGRATION

        repo._fetch_migrations = _fake
        buf = await repo.migrations_to_bytes_buffer()
        line = buf.read().decode().strip()
        assert line.count("\t") == 8  # 9 fields = 8 separators

    async def test_strips_tabs_and_newlines_from_note(self, repo):
        async def _fake():
            yield _MIGRATION_DIRTY_NOTE

        repo._fetch_migrations = _fake
        buf = await repo.migrations_to_bytes_buffer()
        line = buf.read().decode().strip()
        fields = line.split("\t")
        note_field = fields[6]
        assert "\t" not in note_field
        assert "\n" not in note_field

    async def test_field_order_matches_copy_migrations_schema(self, repo):
        """id, uri, performed_at, strategy, old_id, new_id, note, created_at, updated_at."""
        async def _fake():
            yield _MIGRATION

        repo._fetch_migrations = _fake
        buf = await repo.migrations_to_bytes_buffer()
        fields = buf.read().decode().strip().split("\t")
        assert fields[0] == "mig-001"
        assert fields[1] == "https://api.scryfall.com/migrations/mig-001"
        assert fields[2] == "2025-01-15"
        assert fields[3] == "merge"
        assert fields[4] == "old-uuid"
        assert fields[5] == "new-uuid"

    async def test_buffer_contains_one_row_per_migration(self, repo):
        async def _fake():
            yield {**_MIGRATION, "id": "mig-001"}
            yield {**_MIGRATION, "id": "mig-002"}
            yield {**_MIGRATION, "id": "mig-003"}

        repo._fetch_migrations = _fake
        buf = await repo.migrations_to_bytes_buffer()
        lines = [l for l in buf.read().decode().split("\n") if l.strip()]
        assert len(lines) == 3

    async def test_empty_migrations_returns_empty_buffer(self, repo):
        async def _fake():
            return
            yield  # noqa: unreachable — makes this an async generator

        repo._fetch_migrations = _fake
        buf = await repo.migrations_to_bytes_buffer()
        assert buf.read() == b""

    async def test_missing_note_key_writes_empty_string(self, repo):
        row = {k: v for k, v in _MIGRATION.items() if k != "note"}

        async def _fake():
            yield row

        repo._fetch_migrations = _fake
        buf = await repo.migrations_to_bytes_buffer()
        fields = buf.read().decode().strip().split("\t")
        assert fields[6] == ""


class TestDownloadDataFromUrl:
    async def test_returns_parsed_json(self, repo):
        expected = {"data": [{"type": "all_cards", "download_uri": "https://..."}]}

        mock_response = MagicMock()
        mock_response.json.return_value = expected
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(repo, "_get_client", return_value=mock_client):
            result = await repo.download_data_from_url("https://api.scryfall.com/bulk-data")

        assert result == expected

    async def test_builds_full_url_from_relative_endpoint(self, repo):
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(repo, "_get_client", return_value=mock_client):
            await repo.download_data_from_url("/sets")

        call_url = mock_client.get.call_args[0][0]
        assert call_url.startswith("https://api.scryfall.com")
        assert "/sets" in call_url

    async def test_absolute_url_passed_through_unchanged(self, repo):
        abs_url = "https://data.scryfall.io/bulk-manifest/bulk-20250101.json"

        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(repo, "_get_client", return_value=mock_client):
            await repo.download_data_from_url(abs_url)

        call_url = mock_client.get.call_args[0][0]
        assert call_url == abs_url


class TestStreamDownload:
    async def test_yields_chunks_from_response(self, repo):
        mock_chunks = [b"chunk_a", b"chunk_b"]

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content.iter_chunked.return_value = mock_chunks

        mock_get_cm = AsyncMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        # aiohttp session.get() is NOT a coroutine — it returns a context manager
        # directly (synchronous call).  Use MagicMock so calling it doesn't
        # return a coroutine object that would break `async with session.get(...)`.
        mock_session.get = MagicMock(return_value=mock_get_cm)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            async with repo.stream_download("https://data.scryfall.io/bulk.json") as chunks:
                assert chunks is mock_chunks
