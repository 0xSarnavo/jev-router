# Tool router

Adds a hint about which built-in tool groups a prompt needs and which it can skip. MCP servers
have their own router, see [MCP router](mcp-router.md).

## What it does

Each tool group gets one yes/no question: will handling this prompt need this group? A group
at or above `use_threshold` is listed as likely needed. A group at or below `skip_threshold` is
listed as skippable. Groups in between are not mentioned.

The router only advises. Claude still sees every tool and can use any of them, so a wrong answer
costs a little efficiency, never a blocked task.

Claude Code already defers most MCP tool schemas until they are searched for. The hint saves the
search, the schema load and the call that would not have helped.

## Config

```json
"tools": {
  "enabled": true,
  "groups": {
    "web": "searching the web or fetching live web pages (WebSearch, WebFetch, TinyFish, Firecrawl)",
    "browser": "driving a real browser to click, fill forms or take screenshots (Claude in Chrome, computer use)"
  },
  "use_threshold": 0.6,
  "skip_threshold": 0.2
}
```

Each group's text completes the sentence "Will handling the request in `prompt` need ...?".
Name the concrete tools in brackets so the hint maps to what Claude sees.

## Not done

A `PreToolUse` hook could turn skip hints into blocks. It is left out on purpose, because a
wrong skip would stop real work. Add it only if the logs show the hints are ignored often
enough to matter.
