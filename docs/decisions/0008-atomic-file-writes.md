# 0008. Write card and board files atomically

- Status: accepted
- Date: 2026-09-23
- Departs from standard: none

## Context

`mdfile.write_md()` wrote straight to the target path via `Path.write_text()`. That call isn't
atomic: it opens the file (truncating it immediately), writes the new content, then closes. A
concurrent read landing in that window sees a partially-written or empty file.

This wasn't hypothetical. It was hit live during this session's own e2e test runs: `/sidebar/stats`
(fetched by the sidebar after nearly every card action, to refresh the Today badge and tag list) read
a card file at the same moment a different request was mid-write to it, and crashed with
`KeyError: 'id'` — the read landed after the truncate but before the new frontmatter was flushed.
Nothing about that request pattern is exotic; it's the app's own normal behaviour, so this was always
reachable, not just a test artifact.

## Decision

`write_md()` now writes to a `<name>.tmp` sibling and `Path.replace()`s it onto the real path.
`os.replace()` (what `Path.replace()` calls) is atomic on both POSIX and Windows: a concurrent reader
always sees either the complete old file or the complete new one, never a partial one. This covers
every card and board write, since both go through the same function.

Not addressed: two writers targeting the *same* file at nearly the same instant can still race each
other at the temp-file level (the second writer's temp file can land before the first's `replace()`,
so one save can still be lost). That's an existing, already-documented limitation of this app's
design ("cards are plain files with no cross-process locking," `AGENTS.md`/`Dockerfile`) tied to
running a single gunicorn worker; this change doesn't add file locking, because the app already
accepts that risk at the "two people edit the same card at the same instant" level. What it does fix
is the far more common case — any read racing any write — which needed no unlucky simultaneous edit
to trigger, just normal use.

## Consequences

- `tests/test_mdfile.py` covers the write/read round trip and that no `.tmp` file is left behind.
- `tests/test_store.py::test_reading_cards_while_writing_never_sees_a_half_written_file` drives the
  actual race (one thread writing a card in a loop, three reading it in a loop) and asserts no
  exception occurs. Verified this test actually catches the bug, not just exercises the code: reverted
  the fix and watched it fail with the same `KeyError('id')` as the real crash, then reapplied the fix
  and watched it pass.
- No behaviour change for a normal single-user session; this only matters under concurrent access,
  which the LAN-mode household use case this app is built for hits routinely (the sidebar's own
  stats-refresh polling is enough on its own, as shown above).
