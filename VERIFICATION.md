# Verification, 2026-10-13

Built and installed locally on Apple M4 Max, 128 GB unified memory, macOS 26, Python 3.12.8, MLX 0.32.3, mlx-lm 0.32.0, and MCP SDK 1.30.0. Codex discovery used the desktop-bundled CLI, version 0.162.0-alpha.17.2.

## Confirmed

- 24 automated tests passed; Ruff and the Codex skill validator passed. Installer tests cover installation without Codex and preservation of the Off preference.
- Native AppKit app compiled successfully. The installed app passes `codesign --verify --deep --strict` after controller startup and real MCP inference. Python bytecode caching is disabled inside the signed bundle.
- Codex discovered the enabled `humanizer:humanize-copy` skill, attributed to `humanizer@humanizer-local`.
- Codex discovered the `humanizer_status` and `humanize_copy` MCP tools with no tool-discovery error.
- The pinned model downloaded and converted successfully to MLX 8-bit, group size 64. The final model uses approximately 12.7 GB of disk space.
- Real MCP inference completed for interface copy, a message containing protected facts, and a Markdown document containing a code block.
- Two simultaneous MCP clients used the same resident model worker.
- Off interrupted a real long rewrite and its queued sibling. Both callers received their original drafts with `disabled` status. The worker process exited, and reported model allocation dropped to zero.
- A new MCP client reopened a stopped app while preserving its saved Off preference. No worker loaded until explicitly enabled through the local control interface.
- Humanizer was left enabled and ready after verification.
- The installed menu was captured in Ready and Off states using native macOS window screenshots. Reopening the app shows its menu. Its open menu updates when the worker loads or unloads.
- The runtime was reinstalled with `--skip-codex-plugin`, reusing the prepared model and preserving settings.
- Published `mcp-add@0.2.4` generated disposable Claude Code and OpenCode configurations. Both launched the real server, discovered both tools, and reported the same resident worker. The environment-variable launcher handles spaces in the installed path.

## Measurements from the final smoke test

| Measurement | Result |
| --- | --- |
| Three-field batch, including MCP startup | 4.80 s |
| Worker rewrite time for that batch | 4.33 s |
| Ready-state MLX allocation | 12.65 GB |
| Off: request to worker termination | 0.076 s |

These are observations from a small smoke test, not a throughput or quality benchmark. MLX allocation is not total system RAM usage. No battery-life measurement was performed.

| Field | Result | Mechanical warnings |
| --- | --- | --- |
| `empty_state` | rewritten | None |
| `message` | rewritten | None |
| `document` | rewritten | None |

The menu labels were also submitted for review. Overlong candidates were retained as originals; the original labels were kept after reviewing function and clarity. This model can expand short labels or change protected details. Length and literal checks catch some of those cases; the paired skill still requires a meaning and tone review.

## Limits of verification

Native screenshots verify menu rendering and live state changes. Enable/disable behavior was exercised through the same controller interface the menu uses. Physical mouse clicks were not automated because macOS denied the shell's Accessibility access.

The Claude Code and OpenCode connection checks used their generated configurations with the MCP SDK. Full agent sessions and automatic skill selection in those clients were not tested. Claude Desktop configuration follows the official local-server guide but was not tested in the desktop client. The `mcp-add` Codex TOML writer was inspected in source; the user's existing Codex registration was not replaced by that utility.

Implicit skill selection is instruction-driven and may occasionally be missed. It is not a mandatory response interception hook. Start a fresh Codex chat after installation; restart the desktop app if the new plugin is not listed.

Raw local results: [model and lifecycle test](verification.json), [relaunch test](launch-verification.json), [Codex discovery](codex-verification.json).
