import asyncio
import json
import os

import pytest

from humanizer_mcp.client import request
from humanizer_mcp.controller import MAX_MESSAGE, Controller
from humanizer_mcp.copy import RewriteRequest


def batch(text="utilize this"):
    return RewriteRequest(fields=[{"id": "body", "text": text}])


async def wait_for(check):
    async with asyncio.timeout(5):
        while not check():
            await asyncio.sleep(0.01)


async def test_concurrent_chats_share_one_worker(controller):
    results = await asyncio.gather(*(controller.rewrite(batch()) for _ in range(8)))
    assert len({r["pid"] for r in results}) == 1
    assert all(r["fields"][0]["text"] == "use this" for r in results)
    assert controller.status()["status"] == "ready"


async def test_off_cancels_active_and_queued_and_survives_restart(controller):
    active = asyncio.create_task(controller.rewrite(batch("slow")))
    await wait_for(lambda: controller.state == "busy")
    pid = controller.worker.pid
    queued = asyncio.create_task(controller.rewrite(batch("utilize later")))
    await wait_for(lambda: len(controller.jobs) == 2)
    status = await controller.set_enabled(False)
    results = await asyncio.gather(active, queued)
    assert status["worker_pid"] is None
    assert status["active_bytes"] == 0
    assert [r["status"] for r in results] == ["disabled", "disabled"]
    assert results[0]["fields"][0]["text"] == "slow"
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert (await controller.rewrite(batch()))["status"] == "disabled"
    assert controller.worker is None
    reconnected = Controller(controller.root, controller.worker_command)
    try:
        assert not reconnected.enabled
        assert (await reconnected.rewrite(batch()))["status"] == "disabled"
        assert reconnected.worker is None
    finally:
        await reconnected.close()


async def test_enable_loads_new_worker_once(controller):
    first = await controller.rewrite(batch())
    await controller.set_enabled(False)
    await asyncio.gather(*(controller.set_enabled(True) for _ in range(4)))
    second = await controller.rewrite(batch())
    third = await controller.rewrite(batch())
    assert second["pid"] != first["pid"]
    assert second["pid"] == third["pid"]


async def test_crash_retains_original_and_can_recover(controller):
    result = await controller.rewrite(batch("crash"))
    assert result["status"] == "error"
    assert result["fields"][0]["text"] == "crash"
    assert (await controller.rewrite(batch()))["status"] == "completed"


async def test_timeout_unloads_worker(controller):
    controller.request_timeout = 0.2
    result = await controller.rewrite(batch("slow"))
    assert result["status"] == "timeout"
    assert controller.worker is None


async def test_disabling_during_load(controller):
    controller.worker_command.append("--slow-load")
    job = asyncio.create_task(controller.rewrite(batch()))
    await wait_for(lambda: controller.state == "loading")
    await controller.set_enabled(False)
    assert (await job)["status"] == "disabled"
    assert controller.worker is None


async def test_load_failure(controller):
    controller.worker_command.append("--fail-load")
    result = await controller.rewrite(batch())
    assert result["status"] == "error"
    assert controller.status()["active_bytes"] == 0


async def test_real_socket_routes_and_disconnect_cancels(controller):
    socket = controller.root / "control.sock"
    server = await asyncio.start_unix_server(controller.handle, path=str(socket), limit=MAX_MESSAGE)
    try:
        result = await request({"action": "rewrite", "request": batch().model_dump()}, root=controller.root)
        assert result["fields"][0]["text"] == "use this"
        reader, writer = await asyncio.open_unix_connection(str(socket))
        writer.write(
            json.dumps({"action": "rewrite", "request": batch("slow").model_dump()}).encode() + b"\n"
        )
        await writer.drain()
        await wait_for(lambda: controller.state == "busy")
        writer.close()
        await writer.wait_closed()
        await wait_for(lambda: controller.worker is None)
        await wait_for(lambda: not controller.jobs)
        assert (await request({"action": "status"}, root=controller.root))["enabled"]
    finally:
        server.close()
        await server.wait_closed()


async def test_invalid_request_never_echoes_draft(controller):
    socket = controller.root / "control.sock"
    server = await asyncio.start_unix_server(controller.handle, path=str(socket), limit=MAX_MESSAGE)
    try:
        result = await request(
            {
                "action": "rewrite",
                "request": {"fields": [{"id": "private", "text": "private draft", "unexpected": "secret"}]},
            },
            root=controller.root,
        )
        assert result["status"] == "error"
        assert "secret" not in json.dumps(result)
        assert "private draft" not in json.dumps(result)
    finally:
        server.close()
        await server.wait_closed()
