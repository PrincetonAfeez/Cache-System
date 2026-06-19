# Testing Strategy

Correctness tests use `FakeClock` for TTL and for write-back retry timing, whose
backoff advances virtual time instead of sleeping. Real sleeps are confined to
demo/CLI smoke paths where the point is to show live worker behavior.

The suite is organized around invariants: policy metadata, TTL correctness
(including that an update without a ttl preserves the original expiry), capacity
under concurrent writes, single-flight loader counts, scheduler ticks, worker
shutdown (idempotent, leaves no threads, and survives a full bounded queue),
write-back ordering, tombstones and their pruning, and unsafe counterexamples.

Type checking covers both `src` and `tests` under mypy `--strict`; a bare
`mypy` run (no arguments) picks up the targets from `pyproject.toml`.
