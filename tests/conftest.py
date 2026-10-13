import asyncio
import sys
import tempfile
from pathlib import Path

import pytest_asyncio

from humanizer_mcp.controller import Controller


@pytest_asyncio.fixture
async def controller():
    # Unix socket paths are limited to 104 bytes on macOS.
    with tempfile.TemporaryDirectory(prefix="hz-", dir="/tmp") as directory:
        root = Path(directory)
        service = Controller(root, [sys.executable, str(Path(__file__).with_name("fake_worker.py"))])
        yield service
        await service.close()
        await asyncio.sleep(0)
