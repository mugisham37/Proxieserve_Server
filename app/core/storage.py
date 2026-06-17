"""File storage abstraction for application documents."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles
import aiofiles.os

from app.core.config import Settings, get_settings

CHUNK_SIZE = 65_536


class StorageBackend(ABC):
    @abstractmethod
    async def save_file(
        self,
        *,
        stream: AsyncIterator[bytes],
        relative_path: str,
    ) -> str:
        """Stream file data to storage and return the absolute path."""

    @abstractmethod
    async def open_file(self, relative_path: str) -> str:
        """Return the absolute path for reading a stored file."""

    @abstractmethod
    async def delete_file(self, relative_path: str) -> None:
        """Remove a stored file if it exists."""


class LocalFilesystemBackend(StorageBackend):
    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir)

    def _absolute(self, relative_path: str) -> Path:
        return self._root / relative_path

    async def save_file(
        self,
        *,
        stream: AsyncIterator[bytes],
        relative_path: str,
    ) -> str:
        destination = self._absolute(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(destination, "wb") as handle:
            async for chunk in stream:
                await handle.write(chunk)
        return str(destination)

    async def open_file(self, relative_path: str) -> str:
        absolute = self._absolute(relative_path)
        if not absolute.is_file():
            raise FileNotFoundError(relative_path)
        return str(absolute)

    async def delete_file(self, relative_path: str) -> None:
        absolute = self._absolute(relative_path)
        if absolute.is_file():
            await aiofiles.os.remove(absolute)


_storage: StorageBackend | None = None


def get_storage(settings: Settings | None = None) -> StorageBackend:
    global _storage
    if _storage is None:
        resolved = settings or get_settings()
        os.makedirs(resolved.upload_dir, exist_ok=True)
        _storage = LocalFilesystemBackend(resolved.upload_dir)
    return _storage
