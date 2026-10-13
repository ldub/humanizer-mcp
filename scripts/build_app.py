"""Build the native menu app and bundle Python source. No network or model download."""

import argparse
import plistlib
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    app = args.output.resolve()
    binary = app / "Contents/MacOS/Humanizer"
    binary.parent.mkdir(parents=True, exist_ok=True)
    resources = app / "Contents/Resources"
    resources.mkdir(exist_ok=True)
    subprocess.run(
        [
            "swiftc",
            "-swift-version",
            "5",
            "-O",
            "-framework",
            "AppKit",
            str(repo / "macos/Humanizer.swift"),
            "-o",
            str(binary),
        ],
        check=True,
    )
    python_resources = resources / "python"
    if python_resources.exists():
        shutil.rmtree(python_resources)
    shutil.copytree(
        repo / "src/humanizer_mcp",
        python_resources / "humanizer_mcp",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    with (app / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump(
            {
                "CFBundleIdentifier": "dev.lev.humanizer",
                "CFBundleName": "Humanizer",
                "CFBundleDisplayName": "Humanizer",
                "CFBundleExecutable": "Humanizer",
                "CFBundlePackageType": "APPL",
                "CFBundleVersion": "1",
                "CFBundleShortVersionString": "0.1.0",
                "LSUIElement": True,
                "LSMinimumSystemVersion": "14.0",
                "NSHighResolutionCapable": True,
            },
            stream,
        )
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    print(app)


if __name__ == "__main__":
    main()
