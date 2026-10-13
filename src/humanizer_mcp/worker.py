"""One MLX model per worker process. The controller terminates this process to unload it."""

import json
import math
import os
import sys
import threading
import time
from pathlib import Path

from .copy import RewriteRequest, build_prompt, rewrite_field


def watch_parent(parent: int):
    while os.getppid() == parent:
        time.sleep(2)
    os._exit(0)


def emit(value):
    print(json.dumps(value), flush=True)


def main():
    threading.Thread(target=watch_parent, args=(os.getppid(),), daemon=True).start()
    model_path = Path(sys.argv[1])
    if not (model_path / "humanizer-model.json").exists():
        raise RuntimeError("Prepared model is missing. Run scripts/prepare_model.py.")
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = load(str(model_path), tokenizer_config={"trust_remote_code": False})
    mx.eval(model.parameters())
    mx.set_cache_limit(256 * 1024 * 1024)
    sampler = make_sampler(temp=1.0, top_p=0.95, top_k=0, min_p=0.0)

    def memory():
        return {"active_bytes": mx.get_active_memory(), "cache_bytes": mx.get_cache_memory()}

    def generate(draft):
        prompt = build_prompt(draft)
        tokens = len(tokenizer.encode(draft))
        max_tokens = min(2048, max(64, math.ceil(tokens * 2.5)))
        if len(tokenizer.encode(prompt)) + max_tokens > 8192:
            return {"text": draft, "truncated": True}
        parts, last = [], None
        for response in stream_generate(
            model, tokenizer, prompt=prompt, sampler=sampler, max_tokens=max_tokens
        ):
            parts.append(response.text)
            last = response
        return {
            "text": "".join(parts),
            "truncated": last is None or last.finish_reason != "stop",
            "tokens": last.generation_tokens if last else 0,
        }

    emit({"type": "ready", **memory()})
    for line in sys.stdin:
        try:
            started = time.monotonic()
            request = RewriteRequest.model_validate_json(line)
            fields = [rewrite_field(field, generate) for field in request.fields]
            mx.clear_cache()
            emit(
                {
                    "status": "completed",
                    "fields": fields,
                    "seconds": round(time.monotonic() - started, 2),
                    **memory(),
                    "message": "Review accepted rewrites for meaning, names, tone, and factual accuracy.",
                }
            )
        except Exception as error:
            # Do not log drafts or partial rewrites.
            emit({"status": "error", "message": f"Worker failed: {type(error).__name__}"})


if __name__ == "__main__":
    main()
