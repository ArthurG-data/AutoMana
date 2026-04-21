from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, AsyncIterator, Tuple, Union
import asyncio
import json
import logging
import lzma
import queue as _queue
import threading

import ijson

# NB: dropped `from numpy import full` — it was never referenced, yet it
# dragged the entire NumPy dependency into a storage module. That's a
# textbook example of an IDE autocomplete accident passing code review.

logger = logging.getLogger(__name__)

class StorageBackend(ABC):
    """Abstract base class for storage backends"""

    @abstractmethod
    async def open_stream(self, path: str, mode: str = "r", **kwargs) -> Any:
        """Open a file stream for reading or writing."""
        pass

    @abstractmethod
    async def save(self, path: str, data: Any, **kwargs) -> str:
        """Save data to storage. Returns the full path/location."""
        pass

    @abstractmethod
    async def load(self, path: str, **kwargs) -> Any:
        """Load data from storage."""
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a file exists."""
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file. Returns True if successful."""
        pass

    @abstractmethod
    async def list_files(self, directory: str, pattern: str = "*") -> list[str]:
        """List all files in a directory."""
        pass

    @abstractmethod
    async def get_file_size(self, path: str) -> int:
        """Get the size of a file in bytes."""
        pass

    def resolve_path(self, path: str) -> Path:
        raise NotImplementedError

class LocalStorageBackend(StorageBackend):
    """Local filesystem storage"""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorageBackend initialized", extra={"base_path": str(self.base_path)})

    def _get_full_path(self, path: str) -> Path:
        """Get full path and ensure it's within base_path"""
        full_path = (self.base_path / path).resolve()
        if not str(full_path).startswith(str(self.base_path)):
            raise ValueError(f"Path {path} is outside base storage directory")
        return full_path

    def resolve_path(self, path: str) -> Path:
        return self._get_full_path(path)

    async def save(self, path: str, data: Any, file_format: str = "json") -> str:
        """Save data to local filesystem"""
        try:
            full_path = self._get_full_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if file_format == "json":
                async def _write_json():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None,
                        lambda: full_path.write_text(json.dumps(data, indent=2))
                    )
                await _write_json()
            if file_format == "xz":
                async def _write_binary():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None,
                        lambda: full_path.write_bytes(data)
                    )
                await _write_binary()   
            logger.info("Data saved", extra={"file": str(full_path)})
            return str(full_path)

        except Exception as e:
            logger.error("Failed to save data", extra={"file": path, "error": str(e)})
            raise

    async def load(self, path: str, file_format: str = "json") -> Any:
        """Load data from local filesystem"""
        try:
            full_path = self._get_full_path(path)

            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            if file_format == "json":
                async def _read_json():
                    loop = asyncio.get_event_loop()
                    content = await loop.run_in_executor(
                        None,
                        lambda: full_path.read_text()
                    )
                    return json.loads(content)
                return await _read_json()
            else:
                async def _read_binary():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None,
                        lambda: full_path.read_bytes()
                    )
                return await _read_binary()

        except Exception as e:
            logger.error("Failed to load data", extra={"file": path, "error": str(e)})
            raise

    async def exists(self, path: str) -> bool:
        """Check if file exists"""
        try:
            full_path = self._get_full_path(path)
            return full_path.exists()
        except Exception as e:
            logger.error("Failed to check file existence", extra={"file": path, "error": str(e)})
            return False

    async def delete(self, path: str) -> bool:
        """Delete a file"""
        try:
            full_path = self._get_full_path(path)
            if full_path.exists():
                async def _delete():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None,
                        lambda: full_path.unlink()
                    )
                await _delete()
                logger.info("File deleted", extra={"file": path})
                return True
            return False
        except Exception as e:
            logger.error("Failed to delete file", extra={"file": path, "error": str(e)})
            raise

    async def list_files(self, directory: str, pattern: str = "*") -> list[str]:
        """List files in directory"""
        try:
            full_path = self._get_full_path(directory)
            if not full_path.exists():
                return []
            
            async def _list():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: [f.name for f in full_path.iterdir() if f.is_file() and fnmatch(f.name, pattern)]
                )
            return await _list()
        except Exception as e:
            logger.error("Failed to list files", extra={"directory": directory, "error": str(e)})
            raise

    async def get_file_size(self, path: str) -> int:
        """Get file size in bytes"""
        try:
            full_path = self._get_full_path(path)
            if not full_path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            async def _size():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: full_path.stat().st_size
                )
            return await _size()
        except Exception as e:
            logger.error("Failed to get file size", extra={"file": path, "error": str(e)})
            raise

    @asynccontextmanager
    async def open_stream(self, path: str, mode: str = "rb", **kwargs):
        """Open a file stream for reading or writing."""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, mode) as f:
            yield f

class StorageService:
    """High-level storage service with common operations"""

    def __init__(self, backend: StorageBackend):
        self.backend = backend
        logger.info("StorageService initialized", extra={"backend": backend.__class__.__name__})

    async def save_json(self, filename: str, data: Any) -> str:
        return await self.backend.save(filename, data, file_format="json")

    async def load_json(self, filename: str) -> Any:
        return await self.backend.load(filename, file_format="json")

    async def save_binary(self, filename: str, data: Union[bytes, str],
                          file_format: str = "xz") -> str:
        return await self.backend.save(filename, data, file_format=file_format)

    async def load_binary(self, filename: str) -> bytes:
        return await self.backend.load(filename, file_format="binary")

    def open_stream(self, filename: str, mode: str = "rb", **kwargs):
        """Return an async context manager yielding a readable binary stream.
        Works for local files and any future backend (S3 StreamingBody, etc.).
        Compatible with ijson and other streaming parsers.
        """
        return self.backend.open_stream(filename, mode, **kwargs)

    def build_timestamped_name(self, filename: str, ts: str) -> str:
        if filename.endswith(".json.xz"):
            base = filename[:-len(".json.xz")]
            return f"{base}_{ts}.json.xz"
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        return f"{name}_{ts}.{ext}" if ext else f"{name}_{ts}"

    def build_timestamped_path(self, filename: str) -> Path:
        """Return the full resolved path for a timestamped file without writing anything."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamped = self.build_timestamped_name(filename, timestamp)
        return self.backend.resolve_path(timestamped)

    async def save_with_timestamp(self, filename: str, data: Any, file_format: str = "xz") -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        timestamped = self.build_timestamped_name(filename, timestamp)
        if file_format == "json":
            return await self.save_json(timestamped, data)
        if file_format == "xz":
            return await self.save_binary(timestamped, data, file_format="xz")
        raise ValueError(f"Unsupported file format: {file_format}")

    async def file_exists(self, filename: str) -> bool:
        return await self.backend.exists(filename)

    async def delete_file(self, filename: str) -> bool:
        return await self.backend.delete(filename)
    
    async def delete_files(self, filenames: list[str]) -> dict[str, bool]:
        results = {}
        for filename in filenames:
            try:
                result = await self.delete_file(filename)
                results[filename] = result
            except Exception as e:
                logger.error("Failed to delete file", extra={"file": filename, "error": str(e)})
                results[filename] = False
        return results

    async def list_directory(self, pattern: str = "*") -> list[str]:
        return await self.backend.list_files("", pattern)
    
    
    async def get_file_size(self, filename: str) -> int:
        return await self.backend.get_file_size(filename)

    async def load_xz_as_json(self, absolute_path: str) -> dict:
        """Decompress an `.xz` file at the given absolute path and parse as JSON.

        The decompression + JSON parse is CPU-heavy and synchronous, so it is
        offloaded to the default executor to keep the event loop responsive.

        Memory cost scales with the full decompressed payload — prefer
        :meth:`iter_xz_json_kvitems` for anything above a few hundred MB.
        """
        # `get_running_loop()` is the 3.10+ idiom; `get_event_loop()` is on
        # the deprecation glide path when called outside a running loop.
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
    ) -> AsyncIterator[Tuple[str, Any]]:
        """Stream ``(key, value)`` pairs parsed from a JSON map inside an ``.xz`` file.

        Memory stays bounded by ``queue_maxsize`` × sizeof(one value). For the
        MTGJson price catalog this means ~1 card's worth of JSON in flight at
        a time, rather than the full ~1-2 GB payload.

        Parameters
        ----------
        absolute_path:
            Resolved path to the ``.xz`` file on disk.
        prefix:
            ijson key-path to the target map (e.g. ``"data"`` for a top-level
            ``{"data": {"<card_uuid>": {...}, ...}}`` document).
        queue_maxsize:
            Upper bound on how many parsed values may sit in the bridge queue
            before the producer thread blocks. Also doubles as backpressure.
        """
        sentinel: object = object()
        bridge: _queue.Queue = _queue.Queue(maxsize=queue_maxsize)
        err: list[Exception | None] = [None]

        def _producer() -> None:
            try:
                with lzma.open(absolute_path, "rb") as fh:
                    for kv in ijson.kvitems(fh, prefix):
                        bridge.put(kv)
            except Exception as exc:  # captured and re-raised on the consumer side
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
    """Get a storage service instance"""
    backend = LocalStorageBackend(base_path=base_path)
    return StorageService(backend)