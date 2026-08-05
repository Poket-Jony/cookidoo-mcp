# TODO

Open items, recorded 2026-08-05. No dependencies between them; 2 and 3 both
touch the docs and are best done together.

## 1. Migrate to the mcp 2.0 API (`FastMCP` → `MCPServer`)

mcp 2.0 removed `mcp.server.fastmcp`; `FastMCP` is replaced by
`mcp.server.mcpserver.MCPServer`. The dependency is currently pinned to
`mcp[cli]>=1.2,<2` (`pyproject.toml:14`, commit `1ab73c7`) — a stopgap, not
a fix.

**Affected (16 files):**

- `server.py` — FastMCP instance + lifespan
- `context.py` — context injection, `ToolContext` alias
- `transport.py`, `resources.py`
- all 7 modules under `tools/`
- `tests/_mcp_internals.py`, `tests/test_server.py`, `tests/test_tools.py`
- `tests/smoke/smoke_test.py` — the client-side overloads of
  `ClientSession.call_tool()` and `read_resource()` changed in 2.0 as well

**Done when:** the pin is removed from `pyproject.toml`, `./check.sh` is
green on Python 3.12/3.13/3.14, and a live read-only run against Cookidoo
succeeds.

## 2. Fix the `run.sh --help` claims in the docs

The docs describe behaviour that does not exist.

- The README quickstart lists `./run.sh --help  # CLI help`, but `run.sh`
  parses no options at all, and `main()` in `__main__.py:13` never reads
  `sys.argv`. So `--help` silently starts the server. Verified:
  `cookidough-mcp --voellig-erfunden --xyz=123` starts up without an error.
- "Any extra arguments are forwarded to `cookidough-mcp`" (header comment
  `run.sh:11`, README, AGENTS.md) is mechanically true
  (`exec ... "$@"`, `run.sh:141`) but a no-op — and it swallows typos.

**Two options:** either drop both claims from the docs, or implement the
flags (`-h/--help`, `--check`, `--reinstall`, `--no-install`, exit 64 on
unknown arguments — mirroring `check.sh`) and make the docs true.

A `--help` should above all document the nine `COOKIDOUGH_*` environment
variables plus the `.env` precedence rule: `.env` is sourced last
(`run.sh:117-123`) and overrides anything the MCP client passes via `env`.

> Deliberately deferred on 2026-08-05 — do not implement for now.

## 3. Document the macOS TCC restriction

Claude Desktop cannot launch `run.sh` when the repository sits under
`~/Documents` (or `~/Desktop`, `~/Downloads`). macOS TCC denies the exec
with `Operation not permitted` (EPERM, **not** EACCES), and the server log
shows nothing else. Reproduced 2026-08-05: six failed launches from
`~/Documents/Entwicklung/GitHub/cookidough-mcp`, immediate success from an
identical clone at `~/Projects/cookidough-mcp`.

**Why it deserves documenting** — self-diagnosis is unpleasantly hard:

- The script is `rwxr-xr-x`, carries no quarantine xattr, and runs fine
  from a terminal.
- No permission dialog ever appears: the exec is attempted by a spawned
  `bash`, not by the GUI app.
- The "Files and Folders" settings pane has no "+" button, so the app
  cannot be added there at all.
- The grant cannot be made from the shell: `TCC.db` is SIP-protected and
  `tccutil` only offers `reset`, no `grant`.

**Suggestion:** a note in the README "MCP client setup" section right next
to the config example, plus a Troubleshooting entry keyed on the exact
string `Operation not permitted`. State the fix as: keep the checkout
outside the protected folders. Full Disk Access works too, but grants far
more than needed.
