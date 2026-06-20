# CacheLab Schema Folder

This folder contains JSON Schema Draft 2020-12 files for CacheLab's public/interchange data shapes:

- `cache_config.schema.json` — fields accepted by `CacheConfig`.
- `cache_config_toml_container.schema.json` — the full config document, allowing either top-level keys or a `[cache]` table after converting TOML to JSON.
- `cli_state.schema.json` and `cli_state_entry.schema.json` — the JSON state file used by basic CLI commands.
- `cache_entry_snapshot.schema.json` — diagnostic entry snapshots.
- `cache_stats_snapshot.schema.json`, `shard_stats_snapshot.schema.json`, and `policy_stats_snapshot.schema.json` — stats snapshots.
- `worker_job.schema.json` plus worker job subtype schemas — serializable versions of the worker dataclass messages.
- `simulation_result.schema.json` — a generic output record for simulations/benchmarks.

Notes:

1. JSON Schema cannot portably enforce `capacity >= shard_count`, so keep that rule in application validation.
2. `PreloadKey.loader` is a Python callable, so the serializable schema uses `loader_ref` instead.
3. TOML files should be converted to JSON-compatible objects before validation.
