"""Private Unix-socket service owned by the menu bar app."""

import argparse
import asyncio
import fcntl
import json
import os
import signal
import sys
from pathlib import Path

from .copy import RewriteRequest, unchanged
from .paths import atomic_json, data_dir, private_dir, read_json

MAX_MESSAGE = 2 * 1024 * 1024


class Controller:
    def __init__(self, root: Path, worker_command=None, load_timeout=120, request_timeout=180):
        self.root = private_dir(root)
        self.enabled = read_json(root / "settings.json", {"enabled": True}).get("enabled") is True
        config = read_json(root / "config.json", {})
        model = config.get("model_path", str(root / "models/humanizer-mlx-8bit"))
        self.worker_command = worker_command or [sys.executable, "-m", "humanizer_mcp.worker", model]
        self.load_timeout, self.request_timeout = load_timeout, request_timeout
        self.worker = None
        self.load_task = None
        self.jobs = set()
        self.lifecycle = asyncio.Lock()
        self.inference = asyncio.Lock()
        self.epoch = 0
        self.state = "off" if not self.enabled else "starting"
        self.message = "Humanizer is off" if not self.enabled else "Starting Humanizer"
        self.memory = {"active_bytes": 0, "cache_bytes": 0}

    def status(self):
        return {
            "status": self.state,
            "enabled": self.enabled,
            "message": self.message,
            "worker_pid": self.worker.pid if self.worker and self.worker.returncode is None else None,
            "controller_pid": os.getpid(),
            "queued_requests": len(self.jobs),
            "model": "Humanizer 12B · MLX 8-bit",
            **self.memory,
        }

    async def _read_ready(self, process):
        try:
            line = await asyncio.wait_for(process.stdout.readline(), self.load_timeout)
            response = json.loads(line)
            if response.get("type") != "ready":
                raise RuntimeError("Unexpected worker startup response")
            if self.worker is process:
                self.state, self.message = "ready", "Ready"
                self.memory = {key: response.get(key, 0) for key in self.memory}
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.worker is process:
                self.state, self.message = "error", "Could not load the model. Open Logs for details."
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 3)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
            raise RuntimeError(self.message) from None

    async def start_worker(self):
        async with self.lifecycle:
            if not self.enabled:
                return
            if self.worker and self.worker.returncode is None:
                return
            env = dict(
                os.environ,
                HF_HUB_OFFLINE="1",
                HF_HUB_DISABLE_TELEMETRY="1",
                TOKENIZERS_PARALLELISM="false",
                PYTHONUNBUFFERED="1",
            )
            with open(self.root / "worker.log", "ab", buffering=0) as log:
                self.worker = await asyncio.create_subprocess_exec(
                    *self.worker_command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=log,
                    env=env,
                    limit=MAX_MESSAGE,
                )
            self.state, self.message = "loading", "Loading model"
            self.load_task = asyncio.create_task(self._read_ready(self.worker))
            # Retrieve exceptions even when the user enables without sending a rewrite.
            self.load_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            asyncio.create_task(self._watch_worker(self.worker))

    async def _watch_worker(self, process):
        await process.wait()
        if self.worker is process:
            self.worker = None
            self.memory = {key: 0 for key in self.memory}
            if self.enabled:
                self.state, self.message = "error", "Model stopped. Toggle off and on to retry."

    async def _stop_worker(self):
        process, self.worker = self.worker, None
        if self.load_task and not self.load_task.done():
            self.load_task.cancel()
            await asyncio.gather(self.load_task, return_exceptions=True)
        self.load_task = None
        if process and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        self.memory = {key: 0 for key in self.memory}

    async def set_enabled(self, enabled: bool):
        async with self.lifecycle:
            self.enabled = enabled
            atomic_json(self.root / "settings.json", {"enabled": enabled})
            if not enabled:
                self.epoch += 1
                self.state, self.message = "stopping", "Unloading model"
                for job in tuple(self.jobs):
                    job.cancel()
                await self._stop_worker()
                self.state, self.message = "off", "Humanizer is off · model unloaded"
        if enabled:
            await self.start_worker()
        return self.status()

    async def rewrite(self, request: RewriteRequest):
        if not self.enabled:
            return unchanged(
                request, "disabled", "Humanizer is off. Continue with the original draft; do not retry."
            )
        task = asyncio.current_task()
        epoch = self.epoch
        self.jobs.add(task)
        owns_worker = False
        process = None
        try:
            async with asyncio.timeout(self.request_timeout):
                async with self.inference:
                    if not self.enabled or epoch != self.epoch:
                        return unchanged(
                            request, "disabled", "Humanizer was turned off; the draft is unchanged."
                        )
                    await self.start_worker()
                    process = self.worker
                    owns_worker = True
                    await asyncio.shield(self.load_task)
                    self.state, self.message = "busy", "Rewriting copy"
                    process.stdin.write(request.model_dump_json().encode() + b"\n")
                    await process.stdin.drain()
                    response = json.loads(await process.stdout.readline())
                    if epoch != self.epoch or not self.enabled:
                        return unchanged(
                            request, "disabled", "Humanizer was turned off; the draft is unchanged."
                        )
                    if response.get("status") != "completed":
                        return unchanged(request, "error", response.get("message", "Model request failed"))
                    self.memory = {key: response.get(key, 0) for key in self.memory}
                    return response
        except asyncio.CancelledError:
            if epoch != self.epoch:
                return unchanged(request, "disabled", "Humanizer was turned off; the draft is unchanged.")
            # A disconnected caller must not leave an expensive rewrite running.
            if owns_worker:
                async with self.lifecycle:
                    if self.worker is process:
                        await self._stop_worker()
                        self.state, self.message = "idle", "Ready to load on next request"
            raise
        except Exception as error:
            if owns_worker:
                async with self.lifecycle:
                    if self.worker is process:
                        await self._stop_worker()
                        self.state, self.message = "error", "Rewrite failed. The original draft was retained."
            kind = "timeout" if isinstance(error, TimeoutError) else "error"
            return unchanged(request, kind, "Humanizer could not finish. Continue with the original draft.")
        finally:
            self.jobs.discard(task)
            if owns_worker and self.worker is process and self.state == "busy":
                self.state, self.message = "ready", "Ready"

    async def dispatch(self, body):
        action = body.get("action")
        if action == "status":
            return self.status()
        if action == "enable" and type(body.get("enabled")) is bool:
            return await self.set_enabled(body["enabled"])
        if action == "rewrite":
            return await self.rewrite(RewriteRequest.model_validate(body.get("request")))
        return {"status": "error", "message": "Unknown action or invalid arguments"}

    async def handle(self, reader, writer):
        operation = disconnected = None
        try:
            try:
                line = await asyncio.wait_for(reader.readline(), 5)
                body = json.loads(line)
                if not isinstance(body, dict):
                    raise TypeError("Request must be an object")
                operation = asyncio.create_task(self.dispatch(body))
                disconnected = asyncio.create_task(reader.read(1))
                done, _ = await asyncio.wait([operation, disconnected], return_when=asyncio.FIRST_COMPLETED)
                if operation not in done:
                    operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)
                    return
                response = operation.result()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Validation errors can contain the draft; return only the exception type.
                response = {"status": "error", "message": f"Invalid request: {type(error).__name__}"}
            if not writer.is_closing():
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        except ConnectionError:
            pass
        finally:
            if disconnected:
                disconnected.cancel()
                await asyncio.gather(disconnected, return_exceptions=True)
            if operation and not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def close(self):
        # Preserve the user's preference on an unexpected app exit.
        async with self.lifecycle:
            self.epoch += 1
            for job in tuple(self.jobs):
                job.cancel()
            await self._stop_worker()


async def serve(root: Path, parent_pid: int | None):
    private_dir(root)
    with open(root / "controller.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        socket = root / "control.sock"
        socket.unlink(missing_ok=True)
        controller = Controller(root)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        server = await asyncio.start_unix_server(controller.handle, path=str(socket), limit=MAX_MESSAGE)
        socket.chmod(0o600)
        if controller.enabled:
            await controller.start_worker()

        async def watch_parent():
            while parent_pid and os.getppid() == parent_pid:
                await asyncio.sleep(2)
            if parent_pid:
                stop.set()

        watcher = asyncio.create_task(watch_parent())
        try:
            await stop.wait()
        finally:
            server.close()
            await server.wait_closed()
            await controller.close()
            watcher.cancel()
            socket.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=data_dir())
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    os.umask(0o077)
    asyncio.run(serve(args.data_dir, args.parent_pid))


if __name__ == "__main__":
    main()
