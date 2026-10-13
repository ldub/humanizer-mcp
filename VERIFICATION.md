# Verification — 2026-10-13

Built and installed locally on Apple M4 Max, 128 GB unified memory, macOS 26, Python 3.12.8, MLX 0.32.3, mlx-lm 0.32.0, and MCP SDK 1.30.0. Codex discovery used the desktop-bundled CLI, version 0.162.0-alpha.17.2.

## Confirmed

- 22 automated tests passed; Ruff and the Codex skill validator passed.
- Native AppKit app compiled successfully. The installed app passes `codesign --verify --deep --strict` after controller startup and real MCP inference. Python bytecode caching is disabled inside the signed bundle.
- Codex discovered the enabled `humanizer:humanize-copy` skill, attributed to `humanizer@humanizer-local`.
- Codex discovered the `humanizer_status` and `humanize_copy` MCP tools with no tool-discovery error.
- The pinned model downloaded and converted successfully to MLX 8-bit, group size 64. The final model uses approximately 12.7 GB of disk space.
- Real MCP inference completed for interface copy, a message containing protected facts, and a Markdown document containing a code block.
- Two simultaneous MCP clients used the same resident model worker.
- Off interrupted a real long rewrite and its queued sibling. Both callers received their original drafts with `disabled` status. The worker process exited, and reported model allocation dropped to zero.
- A new MCP client reopened a stopped app while preserving its saved Off preference. No worker loaded until explicitly enabled through the local control interface.
- Humanizer was left enabled and ready after verification.

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

The UI automation service could inspect normal apps but timed out when targeting this menu-only app. Its actual rendered menu and mouse clicks were not visually verified. The native app's startup, controller ownership, the same enable/disable actions used by the menu, and MCP relaunch behavior were verified through the local service.

Implicit skill selection is instruction-driven and may occasionally be missed. It is not a mandatory response interception hook. Start a fresh Codex chat after installation; restart the desktop app if the new plugin is not listed.

Raw local results: [model and lifecycle test](verification.json), [relaunch test](launch-verification.json), [Codex discovery](codex-verification.json).
