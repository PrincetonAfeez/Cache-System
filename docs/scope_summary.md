# Scope Summary

CacheLab implements the `[CORE]` acceptance criteria from the project scope
documents (`cache_system_scope.txt` and `cache_system_revised_scope.txt` in the
repository root). Those files define the academic requirements; this summary
points reviewers to the mapping and evidence.

## Where to look

| Area | Scope section | Conformance map |
|------|---------------|-----------------|
| Eviction policies (LRU/LFU/FIFO) | §16 LRU/LFU/FIFO | `docs/scope_conformance.md` |
| TTL (lazy + active) | §16 TTL | `tests/unit/test_ttl.py`, `tests/workers/test_active_expiration.py` |
| Cache API | §16 Cache API | `tests/integration/test_cache_api.py` |
| Single-flight | §16 Single-flight | `tests/concurrency/test_singleflight.py` |
| Sharding | §16 Sharding | `tests/concurrency/test_sharded_cache.py` |
| Workers / queue | §16 Worker lifecycle, Queue | `tests/workers/` |
| Write-through / write-back | §16 Write modes | `tests/integration/test_write_*.py` |
| CLI + demos | §16 CLI, Deliberate failure demos | `tests/cli/` |
| Architecture | design docs | `docs/architecture.md` |

Run `pytest` and `mypy --strict` locally, or rely on `.github/workflows/ci.yml`.
