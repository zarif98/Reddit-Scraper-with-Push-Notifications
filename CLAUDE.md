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

### Single source of truth (avoid cross-layer coupling)

The bot, the API, and the frontend must not each encode the same domain knowledge — when they
drift, you get bugs like "Sylvia shown as a fallback." Rules, in priority order:

1. **Define a decision once, in `config.py`, and derive everywhere.** Source topology lives
   there and nowhere else: `VALID_SOURCES`, `DEFAULT_SOURCE_ORDER`, `RICH_SOURCES` /
   `supports_rich_filters()`, `SOURCE_ORDER_PRESETS`. The bot, `api.py`, and tests all import
   these — adding a source in one place keeps them in agreement. Don't hardcode a parallel
   copy (the earlier `api.py` `('oauth','rss','json')` list is the anti-pattern).
2. **The backend owns business decisions; the frontend consumes API values — it never
   re-derives them.** The UI reads flags like `rich_filters_supported` and
   `using_json_fallback` from `/api/status` and renders them. It must **not** re-compute a
   decision from raw fields (e.g. `activeSource in ('rss','json')` is banned — that logic
   belongs in the backend, keyed off `RICH_SOURCES`).
3. **Shared data _shapes_ are generated, not mirrored.** The `Monitor` TypeScript type is
   generated from the Pydantic model in `reddit_scraper/models.py` (the schema-of-record) —
   see "Generated types" below. Don't hand-write a parallel interface.
4. **The few remaining hand-mirrored constants** (`DEFAULT_COLORS` in `config.py` ↔
   `frontend/types/monitor.ts`; `DEFAULT_MONITOR` _values_ ↔ backend defaults) are the **only**
   acceptable duplication. Each copy carries a `MUST stay in sync with <path>` comment, and you
   change both together. (Migrating these onto the generated model is future work.)

Rule of thumb: if changing a rule means editing more than one file *and* those files can't see
each other's value, you've coupled them — hoist the value into `config.py` (backend), expose it
through the API, or put the shape in `models.py` and generate it.

### Generated types

`reddit_scraper/models.py` (Pydantic) is the single schema-of-record for shapes shared with the
frontend. `frontend/types/generated.ts` is produced from it and **committed** — never edit it
by hand. Regenerate after changing a model:

```bash
npm --prefix frontend run gen:types   # or: python3 scripts/gen_types.py
```

CI regenerates and fails if the committed file is stale, and a pytest guard
(`tests/test_models.py`) checks every model field is present. Backend validation/serialization
against these models is being adopted incrementally (the API already round-trips `Monitor`).

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
