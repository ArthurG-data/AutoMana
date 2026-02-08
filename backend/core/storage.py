from abc import ABC, abstractmethod
from pathlib import Path
import json
import asyncio
import logging
from typing import Any, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class StorageBackend(ABC):
    """Abstract base class for storage backends"""

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
    async def list_files(self, directory: str) -> list[str]:
        """List all files in a directory."""
        pass

class LocalStorageBackend(StorageBackend):
    """Local filesystem storage"""

    def __init__(self, base_path: str = r"G:\data\mtgjson\raw"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalStorageBackend initialized at {self.base_path}")

    def _get_full_path(self, path: str) -> Path:
        """Get full path and ensure it's within base_path"""
        full_path = (self.base_path / path).resolve()
        if not str(full_path).startswith(str(self.base_path)):
            raise ValueError(f"Path {path} is outside base storage directory")
        return full_path

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
            else:
                # For binary or text data
                if isinstance(data, (dict, list)):
                    data = json.dumps(data)
                if isinstance(data, str):
                    data = data.encode()
                
                async def _write_binary():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None,
                        lambda: full_path.write_bytes(data)
                    )
                await _write_binary()

            logger.info(f"Saved data to {full_path}")
            return str(full_path)

        except Exception as e:
            logger.error(f"Failed to save data to {path}: {e}")
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
            logger.error(f"Failed to load data from {path}: {e}")
            raise

    async def exists(self, path: str) -> bool:
        """Check if file exists"""
        try:
            full_path = self._get_full_path(path)
            return full_path.exists()
        except Exception as e:
            logger.error(f"Error checking if file exists {path}: {e}")
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
                logger.info(f"Deleted file: {path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete file {path}: {e}")
            raise

    async def list_files(self, directory: str) -> list[str]:
        """List files in directory"""
        try:
            full_path = self._get_full_path(directory)
            if not full_path.exists():
                return []
            
            async def _list():
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: [f.name for f in full_path.iterdir() if f.is_file()]
                )
            return await _list()
        except Exception as e:
            logger.error(f"Failed to list files in {directory}: {e}")
            raise

class StorageService:
    """High-level storage service with common operations"""

    def __init__(self, backend: StorageBackend):
        self.backend = backend
        logger.info(f"StorageService initialized with {backend.__class__.__name__}")

    async def save_json(self, path: str, data: Any) -> str:
        """Save data as JSON"""
        return await self.backend.save(path, data, file_format="json")

    
    async def load_json(self, path: str) -> Any:
        """Load data from JSON file"""
        return await self.backend.load(path, file_format="json")

    async def save_binary(self, path: str, data: Union[bytes, str]) -> str:
        """Save data as binary"""
        return await self.backend.save(path, data, file_format="binary")

    async def load_binary(self, path: str) -> bytes:
        """Load data as binary"""
        return await self.backend.load(path, file_format="binary")

    async def save_with_timestamp(self, directory: str, filename: str, data: Any, file_format: str = "binary") -> str:
        """Save data with timestamp in filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        timestamped_filename = f"{name}_{timestamp}.{ext}" if ext else f"{name}_{timestamp}"
        path = f"{directory}/{timestamped_filename}"
        if file_format == "json":
            return await self.save_json(path, data)
        return await self.save_binary(path=path, data=data)

    async def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        return await self.backend.exists(path)

    async def delete_file(self, path: str) -> bool:
        """Delete a file"""
        return await self.backend.delete(path)

    async def list_directory(self, directory: str) -> list[str]:
        """List files in directory"""
        return await self.backend.list_files(directory)

def get_storage_service(base_path: str = "storage") -> StorageService:
    """Get a storage service instance"""
    backend = LocalStorageBackend(base_path=base_path)
    return StorageService(backend)