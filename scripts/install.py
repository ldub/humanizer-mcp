"""Install the built app, shared runtime, prepared model, and local Codex plugin."""

import argparse
import json
import shlex
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--move-model", action="store_true", help="Move the prepared model instead of copying it"
    )
    parser.add_argument(
        "--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    source_model = args.model.resolve()
    if not (source_model / "humanizer-model.json").exists():
        parser.error("The model must be prepared with scripts/prepare_model.py first")
    if not (args.app / "Contents/MacOS/Humanizer").is_file():
        parser.error("Build Humanizer.app with scripts/build_app.py first")
    uv = shutil.which("uv")
    if not uv:
        parser.error("Install uv first: https://docs.astral.sh/uv/")
    codex = str(args.codex) if args.codex.exists() else shutil.which("codex")
    if not codex:
        parser.error("Codex CLI was not found. Use --codex PATH.")
    support = Path.home() / "Library/Application Support/Humanizer"
    app = Path.home() / "Applications/Humanizer.app"
    support.mkdir(parents=True, exist_ok=True, mode=0o700)
    support.chmod(0o700)
    app.parent.mkdir(parents=True, exist_ok=True)
    if app.exists():
        parser.error(f"{app} already exists. Quit it and move the old bundle aside before reinstalling.")
    python = support / "venv/bin/python"
    if not python.exists():
        subprocess.run([uv, "venv", "--python", "3.12", str(support / "venv")], check=True)
    subprocess.run(
        [uv, "pip", "install", "--python", str(python), "-r", str(repo / "requirements.lock")], check=True
    )
    model = support / "models/humanizer-mlx-8bit"
    model.parent.mkdir(exist_ok=True)
    if source_model != model:
        if model.exists():
            parser.error(f"{model} already exists; pass it as --model to reuse it")
        if args.move_model:
            shutil.move(str(source_model), model)
        else:
            shutil.copytree(source_model, model)
    shutil.copytree(args.app.resolve(), app)
    config = support / "config.json"
    config.write_text(json.dumps({"python": str(python), "model_path": str(model)}, indent=2) + "\n")
    config.chmod(0o600)
    # Preserve an existing Off preference across upgrades.
    settings = support / "settings.json"
    if not settings.exists():
        settings.write_text('{"enabled": true}\n')
    settings.chmod(0o600)
    launcher_dir = support / "bin"
    launcher_dir.mkdir(exist_ok=True)
    for name, module in [("humanizer-mcp", "humanizer_mcp.server"), ("humanizer", "humanizer_mcp.cli")]:
        launcher = launcher_dir / name
        launcher.write_text(
            "#!/bin/sh\n"
            + "export PYTHONDONTWRITEBYTECODE=1\n"
            + "export PYTHONPATH="
            + shlex.quote(str(app / "Contents/Resources/python"))
            + "\n"
            + "exec "
            + shlex.quote(str(python))
            + " -m "
            + module
            + ' "$@"\n'
        )
        launcher.chmod(0o755)
    marketplace = support / "marketplace"
    plugin = marketplace / "plugins/humanizer"
    shutil.copytree(repo / "plugin", plugin, dirs_exist_ok=True)
    catalog_dir = marketplace / ".agents/plugins"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "humanizer-local",
                "interface": {"displayName": "Humanizer Local"},
                "plugins": [
                    {
                        "name": "humanizer",
                        "source": {"source": "local", "path": "./plugins/humanizer"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                        "category": "Productivity",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    subprocess.run([codex, "plugin", "marketplace", "add", str(marketplace)], check=True)
    subprocess.run([codex, "plugin", "add", "humanizer@humanizer-local"], check=True)
    subprocess.run(["/usr/bin/open", "-g", str(app)], check=True)
    print(
        json.dumps(
            {
                "app": str(app),
                "data": str(support),
                "model": str(model),
                "cli": str(launcher_dir / "humanizer"),
                "plugin": "humanizer@humanizer-local",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
