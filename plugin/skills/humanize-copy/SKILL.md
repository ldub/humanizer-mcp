---
name: humanize-copy
description: Run local Humanizer when creating or editing website or app copy, documents or presentations for an audience, or messages the user will copy and send to someone else. Apply while building an app that contains copy. Ordinary assistant replies, progress updates, code, and technical identifiers are outside this workflow.
---

# Humanize copy

Draft the requested copy, then call Humanizer's `humanize_copy` MCP tool before putting it in the final artifact or returning it as a message draft. Submit related pieces together as named fields, up to 16 per call and around 300 words total. Split longer drafts at paragraph boundaries and submit calls sequentially to fit the local time budget.

Use `format: plain` for app strings, headings, and message drafts. Use `format: markdown` for prose in a complete Markdown document. Markdown mode keeps headings, tables, quotations, and code blocks unchanged; submit any headings that need rewriting as separate plain fields. Extract reader-facing strings from source code rather than sending source files, JSX, HTML, or localization dictionaries through the model.

For each field, include exact names, product terms, placeholders, and required wording in `preserve`. Set `max_characters` when the interface has a real length limit. Every preserve term must occur in that field's draft. Short labels may already be the best wording; keep them when the rewrite changes their function or tone.

Review each returned field against the draft before using it. Mechanical checks cover selected literals and length, not meaning. Check who did what, negation, uncertainty, names, dates, units, promises, and whether the tone fits the audience. Repair or reject changed claims. Keep the accepted copy's wording when inserting it into the artifact; perform a new pass if you substantially rewrite the prose later.

If a field returns `original_retained`, use its original text and inspect its warnings. If the service returns `disabled`, continue with the original draft without retrying or turning Humanizer on. The user's menu bar switch controls that preference. For `unavailable`, `timeout`, or `error`, continue the task with your own reviewed draft and mention the limitation once when relevant. Never describe unprocessed text as humanized.

Calling this tool rewrites a draft locally. It does not publish, send a message, or authorize either action.
