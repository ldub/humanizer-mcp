import asyncio
import json
import time

from .paths import app_path, data_dir


async def request(body: dict, timeout=190, root=None):
    async with asyncio.timeout(timeout):
        reader, writer = await asyncio.open_unix_connection(
            str((root or data_dir()) / "control.sock"), limit=2 * 1024 * 1024
        )
        try:
            writer.write(json.dumps(body).encode() + b"\n")
            await writer.drain()
            return json.loads(await reader.readline())
        finally:
            writer.close()
            await writer.wait_closed()


async def ensure_app():
    try:
        return await request({"action": "status"}, timeout=2)
    except (OSError, ValueError, TimeoutError):
        pass
    app = app_path()
    if not app.exists():
        return {"status": "unavailable", "message": "Install Humanizer.app before using this plugin."}
    process = await asyncio.create_subprocess_exec(
        "/usr/bin/open", "-g", str(app), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await process.wait()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            return await request({"action": "status"}, timeout=1)
        except (OSError, ValueError, TimeoutError):
            await asyncio.sleep(0.25)
    return {"status": "unavailable", "message": "Open Humanizer from Applications and check its menu."}
