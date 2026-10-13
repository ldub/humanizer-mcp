import argparse
import asyncio
import json
import sys

from .client import ensure_app, request


async def run(args):
    status = await ensure_app()
    if status.get("status") == "unavailable" or args.action == "status":
        return status
    if args.action in ("on", "off"):
        return await request({"action": "enable", "enabled": args.action == "on"})
    text = sys.stdin.read()
    return await request(
        {
            "action": "rewrite",
            "request": {
                "fields": [
                    {
                        "id": "draft",
                        "text": text,
                        "format": args.format,
                        "preserve": args.preserve,
                        "max_characters": args.max_characters,
                    }
                ]
            },
        }
    )


def main():
    parser = argparse.ArgumentParser(description="Control the local Humanizer menu bar service")
    parser.add_argument("action", choices=["status", "on", "off", "rewrite"])
    parser.add_argument("--format", choices=["plain", "markdown"], default="plain")
    parser.add_argument("--preserve", action="append", default=[])
    parser.add_argument("--max-characters", type=int)
    print(json.dumps(asyncio.run(run(parser.parse_args())), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
