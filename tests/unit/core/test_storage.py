import tempfile
from pathlib import Path

from automana.core.storage import LocalStorageBackend, StorageService


def _make_service(tmp_path: Path) -> StorageService:
    return StorageService(LocalStorageBackend(base_path=str(tmp_path)))


def test_build_path_returns_correct_absolute_path(tmp_path):
    svc = _make_service(tmp_path)
    result = svc.build_path("AllIdentifiers.json")
    assert result == tmp_path / "AllIdentifiers.json"
    assert isinstance(result, Path)


def test_build_path_is_not_timestamped(tmp_path):
    svc = _make_service(tmp_path)
    result = svc.build_path("AllIdentifiers.json")
    assert result.name == "AllIdentifiers.json"
