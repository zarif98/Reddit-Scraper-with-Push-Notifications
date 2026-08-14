# CLAUDE.md

Guidance for working in this repo. It documents the conventions the code already
follows so changes stay consistent rather than ad hoc.

## What this is

A Reddit monitor that watches subreddits/threads for keyword matches and sends push
notifications. Three deployable pieces (see `docker-compose.yml`):

- **`bot.py`** — the long-running monitor loop (`python bot.py`). Fetches posts/comments,
  applies filters, sends notifications. Hot-reloads `search.json` and `credentials.json`.
- **`api.py`** — a Flask REST API (`python api.py`, port 5001) backing the web UI. Reads/
  writes `search.json` (monitors + source order) and `credentials.json`.
- **`frontend/`** — a Next.js web UI (`npm run dev`).

The reusable logic lives in the **`reddit_scraper/`** package; `api.py` and `bot.py` are
thin entry points that compose it.

### `reddit_scraper/` modules

| Module | Responsibility |
|--------|----------------|
| `config.py` | Data paths (`DATA_DIR`), `search.json` access, source-order resolution. **The single source of truth for `VALID_SOURCES` / `DEFAULT_SOURCE_ORDER`** — reference these, don't hardcode source lists. |
| `credentials.py` | Credential loading (file + env), the non-ASCII encoding guard, PRAW auth. |
| `sources.py` | The data-source pathways (`oauth`/`sylvia`/`json`/`rss`) and the fetch dispatcher. Runtime state is encapsulated in `_SourceState` (see below). |
| `monitor.py` | `RedditMonitor` — evaluates a subreddit/thread against filter rules. |
| `notifications.py` | Apprise dispatch. |
| `status.py` / `health.py` | Bot-status file + Uptime Kuma heartbeats. |

## Commands

```bash
python3 -m pytest -q            # run the test suite (fast, no network — HTTP is mocked)
python3 -m ruff check .         # lint
python3 -m ruff format .        # auto-format
python3 -m ruff check . --fix   # lint + autofix
```

Frontend: `npm run lint` / `npm run build` in `frontend/`.

**Before committing Python changes, run `ruff check .` and `ruff format .`.** Config is in
`ruff.toml` (E/W/F/I, line-length 120, `quote-style = preserve`). Ruff is in
`requirements-test.txt`.

## Coding principles

### Python

- **Style is enforced by ruff** — don't hand-format; run `ruff format`. Line length 120.
- **snake_case** functions/variables, **PascalCase** classes. Module-level "private" helpers
  are prefixed `_`.
- **No type annotations** — this codebase deliberately doesn't use them. Convey types through
  clear names and docstrings; don't add hints piecemeal.
- **Logging, not print** — use the `logging` module with **f-string** messages
  (`logging.info(f"...")`). Emoji prefixes are used for scannable status lines (📡 🔐 ⚠️).
  `print` is only for a CLI startup banner in `__main__`.
- **Docstrings explain _why_, not _what_** — a one-liner for simple functions; for non-obvious
  logic, say what problem it solves (see `_SourceState`, `_coalesce`). Keep them concise.
- **Centralize shared access** — paths/config through `config.py`, credentials through
  `credentials.py`. Don't re-read env vars or files that a helper already owns.

### Error handling

- **Fetchers signal blocking by raising, transient/empty by returning `None`.** RSS/JSON/Sylvia
  fetchers `raise` on 403/429/auth failure so the dispatcher cools the source down and falls
  through; they return `None` on a malformed-but-non-blocking response.
- **Broad `except Exception` belongs at boundaries** — the fetch dispatcher, the monitor loop,
  and Flask routes catch broadly to degrade gracefully (log + continue / return an error JSON).
  Elsewhere, catch the specific exception you expect.
- **Fail safe.** When a source can't provide a field (e.g. RSS has no score/domain), filters
  that need it don't match rather than firing false notifications.

### State

- **`sources.py` runtime state lives in `_SourceState`** (cooldowns/backoff, active source,
  coalescing cache, proxy rotation, RSS throttle, notification flags), owned by a single
  `_state` instance. Module-level functions are a thin facade over it — call those (and the
  `get_active_source()` / `get_last_fetch_success_ts()` accessors) rather than reaching into
  fields. Tuning knobs (`SOURCE_COOLDOWN_*`, `FETCH_CACHE_TTL`, `_PROXIES`, `SYLVIA_API_KEY`,
  …) stay module-level config so they can be overridden by env/tests.

### Data sources

The dispatcher tries sources in `config.get_source_order()`, falling through on failure with
exponential backoff, and coalesces duplicate concurrent fetches. Order is set via the UI
(→ `search.json`), then `REDDIT_SOURCE_ORDER`, then the default. `sylvia` is opt-in (needs
`SYLVIA_API_KEY`); anonymous fetches can be routed through a proxy (`REDDIT_PROXY(IES)`).

### Frontend

- **PascalCase components**, one concern each. Large modals are split into focused sections
  (see `components/settings/`), with shared types in a co-located `types.ts`.
- Lint with the repo `eslint.config.mjs`.

## Testing

- **pytest**, one `test_<module>.py` per module under `tests/`; shared setup in `conftest.py`.
- **No network in tests** — HTTP is mocked with `responses` (or by monkeypatching `requests`).
- **Reset module/global state in an `autouse` fixture** (see `test_sources.py`'s
  `reset_source_state`, which calls `sources._state.reset()`).
- **Test through the public surface** — call the public functions/accessors, not private
  state, so tests survive internal refactors.
- Add/adjust tests with any behavior change; keep the suite green.
