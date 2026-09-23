# MCP router

Decides which MCP servers a prompt needs. In a session it adds a hint. At launch it starts the
agent CLI with only those servers, which is where the savings are.

## Why

MCP servers send their tool schemas to the model. How much that costs depends on the CLI.
Measured on this laptop on 2026-09-23:

| CLI | What MCP costs | Measured |
| --- | --- | --- |
| OpenCode | Every schema, on every request | One-word prompt: 109,069 input tokens with 4 servers on, 25,585 with them off |
| Claude Code | Tool names and server instructions. Schemas load on search | Railway 57 tools, 26.1k tokens of schemas. TinyFish 23 tools, 15.6k |
| Codex | Not measured | Codex did not list MCP tools to the model even with Railway on, so it likely defers them too |

On OpenCode, turning four servers off saved about 83,000 tokens per request.

## What it asks Jev

One yes/no question per MCP server: will handling this prompt need it? The question uses a
short description from `describe` in the config, so write one for each server you add.

## In a session

The hook adds a line like:

```
MCP servers likely needed: railway. MCP servers not needed, do not search or call their
tools: tinyfish, figma.
```

Servers come from the CLI running the hook: `~/.claude.json` and the project's `.mcp.json` for
Claude Code, `~/.codex/config.toml` for Codex. A running session cannot drop a server, so this
only saves searches and wrong calls.

## At launch

`jev "<prompt>"` asks the same questions before starting a CLI and keeps every server that is not
a clear no. A server is dropped only when its probability is at or below `skip_threshold`.

| CLI | How servers are dropped |
| --- | --- |
| Claude Code | `--mcp-config <file> --strict-mcp-config` with only the kept servers. The file is written to `~/.cache/jev-router/launch/` with mode 600, because server definitions can hold tokens |
| Codex | `-c mcp_servers.<name>.enabled=false` per dropped server |
| OpenCode | `OPENCODE_CONFIG_CONTENT` with `enabled: false` per dropped server. This works on the free tier, unlike changing tools from a plugin |

If a dropped server turns out to be needed, restart with `jev --all-mcp "<prompt>"`.

## Config

```json
"mcp": {
  "enabled": true,
  "use_threshold": 0.6,
  "skip_threshold": 0.2,
  "ignore": ["node_repl"],
  "describe": { "railway": "the Railway MCP server for deploying and inspecting Railway services" }
}
```

Servers in `ignore` get no question and are always kept. `node_repl` is there because Codex uses
it for its own browser and computer-use features.
