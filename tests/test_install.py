import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def installer():
    path = Path(__file__).resolve().parents[1] / "scripts/install.py"
    spec = importlib.util.spec_from_file_location("humanizer_install", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_service_install_without_codex_preserves_off(installer, monkeypatch, tmp_path, capsys):
    home = tmp_path / "home with spaces"
    support = home / "Library/Application Support/Humanizer"
    model = support / "models/humanizer-mlx-8bit"
    model.mkdir(parents=True)
    (model / "humanizer-model.json").write_text("{}")
    (support / "settings.json").write_text('{"enabled": false}')
    python = support / "venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    app = tmp_path / "build/Humanizer.app"
    binary = app / "Contents/MacOS/Humanizer"
    binary.parent.mkdir(parents=True)
    binary.touch()
    calls = []
    monkeypatch.setattr(installer.Path, "home", lambda: home)
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/test/uv" if name == "uv" else None)
    monkeypatch.setattr(installer.subprocess, "run", lambda argv, **kwargs: calls.append(argv))
    monkeypatch.setattr("sys.argv", ["install.py", "--app", str(app), "--model", str(model),
                                    "--skip-codex-plugin", "--codex", "/does-not-exist/codex"])

    installer.main()

    result = json.loads(capsys.readouterr().out)
    assert result["plugin"] is None
    assert json.loads((support / "settings.json").read_text()) == {"enabled": False}
    assert json.loads((support / "config.json").read_text())["model_path"] == str(model)
    assert (home / "Applications/Humanizer.app/Contents/MacOS/Humanizer").exists()
    assert (support / "marketplace/plugins/humanizer/skills/humanize-copy/SKILL.md").exists()
    assert Path(result["mcp"]).stat().st_mode & 0o111
    assert [call[0] for call in calls] == ["/test/uv", "/usr/bin/open"]


def test_default_install_requires_codex_before_writing(installer, monkeypatch, tmp_path):
    app = tmp_path / "Humanizer.app"
    binary = app / "Contents/MacOS/Humanizer"
    binary.parent.mkdir(parents=True)
    binary.touch()
    model = tmp_path / "model"
    model.mkdir()
    (model / "humanizer-model.json").write_text("{}")
    home = tmp_path / "untouched-home"
    monkeypatch.setattr(installer.Path, "home", lambda: home)
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/test/uv" if name == "uv" else None)
    monkeypatch.setattr("sys.argv", ["install.py", "--app", str(app), "--model", str(model),
                                    "--codex", "/does-not-exist/codex"])
    with pytest.raises(SystemExit) as error:
        installer.main()
    assert error.value.code == 2
    assert not home.exists()
