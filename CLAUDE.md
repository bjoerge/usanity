# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

µsanity (usanity) is a MicroPython client library for the Sanity.io API. It provides two layers:

1. **Client layer** (`lib/client/`) — `SanityClient` (sync) and `AsyncSanityClient` (async) that handle HTTP internally via `urequests` or a pluggable requester.
2. **Request-builder layer** (`lib/endpoints.py`) — low-level functions (`query_request()`, `mutate_request()`, `listen_request()`, `doc_request()`) that return `(url, headers[, body])` tuples for the caller to execute.

## Running Tests

Tests use a custom minimal test framework (no pytest/unittest — this targets MicroPython). Run all tests with CPython:

```bash
python main.py
```

Test functions are discovered by convention: any function starting with `test_` in `test_query.py`, `test_mutation.py`, `test_listen.py`, `test_eventsource.py`, and `test_client.py`. The test runner in `main.py` handles both sync and async test functions.

Test assertions use `expect_equal(actual, expected)` from `test_helpers.py`, which raises `TestError` on mismatch.

## Architecture

- **`lib/`** — the installable package (published as `usanity` via MicroPython's `mip`)
  - `endpoints.py` — core request builders: `query_request()`, `mutate_request()`, `listen_request()`, `doc_request()`
  - `mutations.py` — helpers for constructing Sanity mutation/patch dicts (`create`, `patch`, `insert`, `set`, etc.)
  - `utils.py` — `merge()` dict helper and `encode_uri_component()`
  - `constants.py` — `USER_AGENT` string built from `os.uname()`
  - **`client/`** — high-level clients that wrap endpoints + HTTP
    - `sync_client.py` — `SanityClient` using `urequests` (lazy-imported)
    - `async_client.py` — `AsyncSanityClient` using `async_urequests`, adds `listen()` method
  - **`http/`** — HTTP-level modules
    - `eventsource.py` — SSE (Server-Sent Events) client: `EventSource` async iterator with auto-reconnect
    - `async_urequests.py` — async HTTP client (`get`, `post`) built on `uasyncio`
- **`package.json`** — MicroPython `mip` package manifest (maps install paths to source files), **not** an npm package
- **`main.py`** — test runner entry point

## MicroPython Constraints

- Only use modules available in MicroPython (e.g. `ucollections.OrderedDict`, `urequests`). No standard CPython-only imports.
- Keep memory footprint small — this runs on microcontrollers.
