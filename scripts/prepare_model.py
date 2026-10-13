"""Download the pinned upstream weights and convert them once to MLX 8-bit."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO = "jialinyyzz/humanizer"
REVISION = "7232532cb8466bd393544e97826e12e6b5e471ac"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.output / "humanizer-model.json").exists():
        print(f"Prepared model already exists: {args.output}")
        return
    from huggingface_hub import snapshot_download
    from mlx_lm.convert import convert

    snapshot_download(
        REPO,
        revision=REVISION,
        local_dir=args.source,
        allow_patterns=["*.json", "*.safetensors", "LICENSE", "NOTICE"],
    )
    pf = json.loads((args.source / "prompt_format.json").read_text())
    fingerprint = hashlib.sha256((pf["instr"] + "\n\nX" + pf["sep"]).encode()).hexdigest()[:16]
    if fingerprint != "cc51d66b4c593fbe":
        raise RuntimeError("Unexpected upstream prompt format")
    convert(str(args.source), str(args.output), quantize=True, q_bits=8, q_group_size=64)
    for name in ["prompt_format.json", "LICENSE", "NOTICE"]:
        if (args.source / name).exists():
            shutil.copy2(args.source / name, args.output / name)
    (args.output / "humanizer-model.json").write_text(
        json.dumps(
            {
                "repo": REPO,
                "revision": REVISION,
                "bits": 8,
                "group_size": 64,
                "prompt_fingerprint": fingerprint,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Model ready: {args.output}")


if __name__ == "__main__":
    main()
