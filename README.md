# claude-logger

Claude Code plugin that records task lifecycle events to Markdown reports under:

```text
~/.claude/logs/<session-id>/summary.md
```

It captures user prompts, tool calls, tool failures, visible transcript context, final assistant output, and completion reasons from `Stop`, `StopFailure`, and `SessionEnd` hooks.

## Install

```bash
claude plugin marketplace add markyang2020/claude-logger
claude plugin install claude-logger@mark-local-plugins
```

For local development:

```bash
claude plugin validate .
claude --plugin-dir .
```

## Notes

Claude Code hooks do not expose hidden chain-of-thought. This plugin records only visible transcript thinking summaries, assistant text, tool calls, and tool results.

Full documentation: [docs/README.md](docs/README.md)
