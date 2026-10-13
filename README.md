# Humanizer for Codex

Local copy editing for websites, apps, documents, and messages you plan to send. A Codex plugin pairs a skill with an MCP tool; a native macOS menu bar app keeps one MLX model available across chats.

Ordinary assistant replies and progress updates are outside the skill's scope. This is an instruction-driven workflow, not an interception hook: Codex selects the skill when the task involves audience-facing copy, sends the draft to Humanizer, and reviews the result before using it.

## Everyday use

Open **Humanizer.app** and click its text-bubble menu bar icon. The **Enabled** checkbox is the main control:

- **On:** load the model once, then reuse it for successive requests. Requests from different chats are queued through the same worker.
- **Off:** cancel active and queued rewrites, terminate the model worker, and release its memory. The lightweight menu app and controller remain available.
- **Quit Humanizer:** turn it off and quit. An MCP connection can reopen the menu app, but the saved Off preference remains Off.

The menu shows loading, ready, busy, or off, along with the worker's last reported MLX allocation. It does not estimate system-wide RAM or battery use. Keeping weights resident consumes memory; inference is the main compute cost. No login item is installed.

After installing the plugin, start a new Codex chat. For example:

> Build a settings page with a friendly empty state and confirmation messages.

The paired skill tells Codex to humanize the app's copy before inserting it. You can also explicitly invoke `humanize-copy` if implicit selection misses it. Turning the menu switch off lets the same task continue with the original drafts.

## Install from source

Requirements: Apple Silicon, macOS 14 or later, Xcode Command Line Tools, `uv`, and a recent Codex with plugin support. The tested configuration is recorded in [VERIFICATION.md](VERIFICATION.md). The initial download and conversion need approximately 40 GB of free disk space; the final 8-bit model is approximately 13 GB. Model preparation is the only step that downloads weights.

From this repository:

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.lock
.venv/bin/python scripts/prepare_model.py --source build/source-model --output build/humanizer-mlx-8bit
.venv/bin/python scripts/build_app.py --output build/Humanizer.app
.venv/bin/python scripts/install.py --app build/Humanizer.app --model build/humanizer-mlx-8bit --move-model
```

The installer uses the Codex CLI bundled with `/Applications/ChatGPT.app` when available; pass `--codex /absolute/path/to/codex` for another installation. It registers the local `humanizer-local` marketplace and installs `humanizer@humanizer-local` with Codex's plugin commands.

Installed locations:

| Item | Location |
| --- | --- |
| Menu app and Python source | `~/Applications/Humanizer.app` |
| Runtime, model, settings, logs | `~/Library/Application Support/Humanizer/` |
| Local plugin marketplace | `~/Library/Application Support/Humanizer/marketplace/` |
| Command line interface | `~/Library/Application Support/Humanizer/bin/humanizer` |

`--move-model` avoids another copy of the converted weights. After installation and verification, the downloaded source weights in `build/source-model` can be removed. Existing settings are preserved; the installer refuses to overwrite an existing app bundle.

For an upgrade, quit Humanizer, move the old app bundle aside, rebuild, and run the installer with the existing model directory as `--model`. Keep `settings.json` to retain the On/Off preference.

## Tools and copy contract

The MCP exposes only `humanizer_status` and `humanize_copy`. It has no tool for changing the user's switch.

```json
{
  "fields": [
    {
      "id": "empty_state",
      "text": "You can utilize Collections to organize your saved documents.",
      "format": "plain",
      "preserve": ["Collections"],
      "max_characters": 120
    }
  ]
}
```

Submit up to 16 fields per call, with unique IDs, and keep each call around 300 words total. Longer documents should be split at paragraph boundaries. The MCP adapter allows 45 seconds for a request, below Codex's usual tool timeout; disconnecting cancels the underlying work. `preserve` entries must appear in the draft. Use plain fields for interface strings and headings; Markdown mode rewrites prose while keeping headings, tables, quoted blocks, and code intact. Send actual copy, not JSX, HTML, or localization source files.

Selected literal checks protect numbers, percentages, URLs, inline code, placeholders, quotations, and explicitly preserved terms. Truncation, a changed protected literal, or an exceeded character limit retains the entire original field with a warning. These checks cannot prove that meaning, claims, tone, or all units are unchanged. Codex must review accepted rewrites.

Disabled, unavailable, failed, or timed-out calls return original drafts. The skill prohibits retries while disabled and prohibits claiming that an unprocessed draft was humanized. A failed model request does not prevent Codex from finishing the user's task.

### CLI

```sh
"$HOME/Library/Application Support/Humanizer/bin/humanizer" status
"$HOME/Library/Application Support/Humanizer/bin/humanizer" off
"$HOME/Library/Application Support/Humanizer/bin/humanizer" on
printf '%s' 'You can utilize Collections to organize documents.' | \
  "$HOME/Library/Application Support/Humanizer/bin/humanizer" rewrite --preserve Collections
```

The CLI is a local user control and can change the switch. MCP tools cannot.

## How it works

```text
Codex skill → stdio MCP adapter ─┐
Codex in another chat ──────────┼→ private Unix socket → controller → one MLX worker
Native menu app ────────────────┘                       On / Off      resident weights
```

The native app owns the controller. The controller owns a separate inference process so Off can terminate it even during generation; this also releases MLX/Metal allocations. A lock prevents duplicate controllers. Parent watchdogs stop orphaned workers after an unexpected app or controller exit. The controller serializes model requests, cancels work on caller disconnect, and imposes load and request timeouts.

The socket is accessible only to the current user. Inference runs offline, with Hugging Face offline mode enabled. Drafts travel through local pipes and a Unix socket; the service does not write them to logs. Codex itself still receives the draft and tool result as part of its conversation.

The plugin contains `plugin.json`, `mcp.json`, and `skills/humanize-copy/`. Installing that bundle supplies both the tools and their usage instructions. It does not depend on the MCP server dynamically installing a skill or editing global `AGENTS.md` files.

### Model and upstream compatibility

- Model: [`jialinyyzz/humanizer`](https://huggingface.co/jialinyyzz/humanizer), pinned to `7232532cb8466bd393544e97826e12e6b5e471ac`.
- Runner reference: [`sgaofen/humanizer-local-model`](https://github.com/sgaofen/humanizer-local-model), pinned to `d4f11a8e52a4c668951b0eece6a97f755d0e43bd`.
- Local format: MLX 8-bit, group size 64, converted once from the pinned weights.
- Prompt: upstream raw completion format, without a chat template. Fingerprint: `cc51d66b4c593fbe`.
- Sampling: temperature 1.0, top-p 0.95, no top-k or min-p filtering; EOS termination, capped output and context budgets.
- Chunking and Markdown planning: vendored upstream `hz_text.py`, with its license and notice.

The selected revision is pinned for reproducibility. See [NOTICE](NOTICE) for attribution.

## Development and verification

```sh
.venv/bin/ruff check src scripts tests
.venv/bin/pytest -q
```

Tests cover preservation and fallback behavior, concurrent callers, cancellation, Off-state persistence, worker crashes, timeouts, Unix-socket handling, and the actual stdio MCP discovery/call protocol. Lifecycle tests use a small fake worker and do not require downloading weights. On macOS, run them in a context that permits local Unix sockets.

The native app is built locally and ad-hoc signed. Distributing it to other Macs would also require a packaging and signing/notarization workflow.

## Troubleshooting and removal

Use **Open Logs…** in the menu to open the support directory. `controller.log` records startup problems; `worker.log` records model-loading errors. A missing runtime, incomplete conversion, or incompatible MLX version will appear there. Reopen the app after fixing a controller startup failure. Toggle Off then On after a worker load failure.

To remove the integration, quit Humanizer and uninstall `humanizer@humanizer-local` through Codex's plugin settings or `codex plugin remove humanizer@humanizer-local`. Move `~/Applications/Humanizer.app` and `~/Library/Application Support/Humanizer` to Trash. The latter contains the model and all Humanizer settings; keep it if you plan to reinstall.
