from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, AsyncIterator
import asyncio
import json
import logging
import lzma
import queue as _queue
import threading

import ijson


logger = logging.getLogger(__name__)


class StorageBackend(ABC):

    @abstractmethod
    def open_stream(self, path: str, mode: str = "r", **kwargs) -> AbstractAsyncContextManager[Any]:
        """Return an async context manager yielding an open file handle."""

    @abstractmethod
    async def save(self, path: str, data: Any, **kwargs) -> str:
        """Save data to storage. Returns the full path/location."""

    @abstractmethod
    async def load(self, path: str, **kwargs) -> Any:
        """Load data from storage."""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists."""

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file. Returns True if successful."""

    @abstractmethod
    async def list_files(self, directory: str, pattern: str = "*") -> list[str]:
        """List all files in a directory."""

    @abstractmethod
    async def get_file_size(self, path: str) -> int:
        """Get the size of a file in bytes."""

    @abstractmethod
    def resolve_path(self, path: str) -> Path:
        """Resolve a relative path to an absolute Path within the backend root."""


class LocalStorageBackend(StorageBackend):

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorageBackend initialized", extra={"base_path": str(self.base_path)})

    def _get_full_path(self, path: str) -> Path:
        full_path = (self.base_path / path).resolve()
        try:
            full_path.relative_to(self.base_path)
        except ValueError:
            raise ValueError(f"Path '{path}' resolves outside the storage root")
        return full_path

    def resolve_path(self, path: str) -> Path:
        return self._get_full_path(path)

    async def save(self, path: str, data: Any, file_format: str = "json") -> str:
        try:
            full_path = self._get_full_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            loop = asyncio.get_running_loop()

            if file_format == "json":
                await loop.run_in_executor(
                    None, lambda: full_path.write_text(json.dumps(data, indent=2))
                )
            elif file_format == "xz":
                await loop.run_in_executor(None, lambda: full_path.write_bytes(data))
            else:
                raise ValueError(f"Unsupported file format: '{file_format}'")

            logger.info("Data saved", extra={"file": str(full_path)})
            return str(full_path)
        except Exception as e:
            logger.error("Failed to save data", extra={"file": path, "error": str(e)})
            raise

    async def load(self, path: str, file_format: str = "json") -> Any:
        try:
            full_path = self._get_full_path(path)
            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            loop = asyncio.get_running_loop()

            if file_format == "json":
                content = await loop.run_in_executor(None, full_path.read_text)
                return json.loads(content)
            elif file_format in ("xz", "raw"):
                return await loop.run_in_executor(None, full_path.read_bytes)
            else:
                raise ValueError(f"Unsupported file format: '{file_format}'")
        except Exception as e:
            logger.error("Failed to load data", extra={"file": path, "error": str(e)})
            raise

    async def exists(self, path: str) -> bool:
        try:
            return self._get_full_path(path).exists()
        except Exception as e:
            logger.error("Failed to check file existence", extra={"file": path, "error": str(e)})
            return False

    async def delete(self, path: str) -> bool:
        try:
            full_path = self._get_full_path(path)
            if not full_path.exists():
                return False
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, full_path.unlink)
            logger.info("File deleted", extra={"file": path})
            return True
        except Exception as e:
            logger.error("Failed to delete file", extra={"file": path, "error": str(e)})
            raise

    async def list_files(self, directory: str, pattern: str = "*") -> list[str]:
        try:
            full_path = self._get_full_path(directory)
            if not full_path.exists():
                return []
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: [f.name for f in full_path.iterdir() if f.is_file() and fnmatch(f.name, pattern)],
            )
        except Exception as e:
            logger.error("Failed to list files", extra={"directory": directory, "error": str(e)})
            raise

    async def get_file_size(self, path: str) -> int:
        try:
            full_path = self._get_full_path(path)
            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: full_path.stat().st_size)
        except Exception as e:
            logger.error("Failed to get file size", extra={"file": path, "error": str(e)})
            raise

    @asynccontextmanager
    async def open_stream(self, path: str, mode: str = "rb", **kwargs):
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, mode) as f:
            yield f


class StorageService:

    def __init__(self, backend: StorageBackend):
        self.backend = backend
        logger.info("StorageService initialized", extra={"backend": backend.__class__.__name__})

    async def save_json(self, filename: str, data: Any) -> str:
        return await self.backend.save(filename, data, file_format="json")

    async def load_json(self, filename: str) -> Any:
        return await self.backend.load(filename, file_format="json")

    async def save_binary(self, filename: str, data: bytes | str, file_format: str = "xz") -> str:
        return await self.backend.save(filename, data, file_format=file_format)

    async def load_binary(self, filename: str) -> bytes:
        return await self.backend.load(filename, file_format="raw")

    def open_stream(self, filename: str, mode: str = "rb", **kwargs) -> AbstractAsyncContextManager[Any]:
        """Return an async context manager yielding a readable binary stream.
        Compatible with ijson and other streaming parsers.
        """
        return self.backend.open_stream(filename, mode, **kwargs)

    def build_timestamped_name(self, filename: str, ts: str) -> str:
        if filename.endswith(".json.xz"):
            base = filename[: -len(".json.xz")]
            return f"{base}_{ts}.json.xz"
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        return f"{name}_{ts}.{ext}" if ext else f"{name}_{ts}"

    def build_timestamped_path(self, filename: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.backend.resolve_path(self.build_timestamped_name(filename, timestamp))

    def build_path(self, filename: str) -> Path:
        return self.backend.resolve_path(filename)

    async def save_with_timestamp(self, filename: str, data: Any, file_format: str = "xz") -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamped = self.build_timestamped_name(filename, timestamp)
        if file_format == "json":
            return await self.save_json(timestamped, data)
        if file_format == "xz":
            return await self.save_binary(timestamped, data, file_format="xz")
        raise ValueError(f"Unsupported file format: '{file_format}'")

    async def file_exists(self, filename: str) -> bool:
        return await self.backend.exists(filename)

    async def delete_file(self, filename: str) -> bool:
        return await self.backend.delete(filename)

    async def delete_files(self, filenames: list[str]) -> dict[str, bool]:
        results = await asyncio.gather(
            *[self.delete_file(f) for f in filenames],
            return_exceptions=True,
        )
        return {
            f: (r if isinstance(r, bool) else False)
            for f, r in zip(filenames, results)
        }

    async def list_directory(self, pattern: str = "*") -> list[str]:
        return await self.backend.list_files("", pattern)

    async def get_file_size(self, filename: str) -> int:
        return await self.backend.get_file_size(filename)

    async def load_xz_as_json(self, absolute_path: str) -> dict:
        """Decompress an `.xz` file at the given absolute path and parse as JSON.

        CPU-heavy decompression is offloaded to the executor to keep the event
        loop responsive. Prefer `iter_xz_json_kvitems` for payloads above a
        few hundred MB to avoid loading the full decompressed payload into memory.
        """
        loop = asyncio.get_running_loop()

        def _read() -> dict:
            with lzma.open(absolute_path, "rt", encoding="utf-8") as f:
                return json.load(f)

        return await loop.run_in_executor(None, _read)

    async def iter_xz_json_kvitems(
        self,
        absolute_path: str,
        prefix: str,
        queue_maxsize: int = 4,
    ) -> AsyncIterator[tuple[str, Any]]:
        """Stream ``(key, value)`` pairs parsed from a JSON map inside an ``.xz`` file.

        Memory stays bounded by ``queue_maxsize`` × sizeof(one value). For the
        MTGJson price catalog this means ~1 card's worth of JSON in flight at a
        time rather than the full ~1-2 GB payload.

        Parameters
        ----------
        absolute_path:
            Resolved path to the ``.xz`` file on disk.
        prefix:
            ijson key-path to the target map (e.g. ``"data"`` for a top-level
            ``{"data": {"<card_uuid>": {...}, ...}}`` document).
        queue_maxsize:
            Upper bound on how many parsed values may sit in the bridge queue
            before the producer thread blocks. Also acts as backpressure.
        """
        sentinel: object = object()
        bridge: _queue.Queue = _queue.Queue(maxsize=queue_maxsize)
        err: list[Exception | None] = [None]

        def _producer() -> None:
            try:
                with lzma.open(absolute_path, "rb") as fh:
                    for kv in ijson.kvitems(fh, prefix):
                        bridge.put(kv)
            except Exception as exc:
                err[0] = exc
            finally:
                bridge.put(sentinel)

        thread = threading.Thread(
            target=_producer, name="storage-xz-json-kvitems", daemon=True
        )
        thread.start()

        loop = asyncio.get_running_loop()
        try:
            while True:
                item = await loop.run_in_executor(None, bridge.get)
                if item is sentinel:
                    break
                yield item
            if err[0] is not None:
                raise err[0]
        finally:
            thread.join(timeout=5)


def get_storage_service(base_path: str = "storage") -> StorageService:
    return StorageService(LocalStorageBackend(base_path=base_path))
