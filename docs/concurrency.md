# Concurrency

Keys route through `stable_hash`, a process-stable hash (built on
`blake2b(repr(...))`) so shard placement does not depend on Python's randomized
hash seed and tests stay deterministic. Numeric keys are canonicalized first so
that values which are equal under `==` but render differently — `1`, `1.0`,
`True` — hash to the same shard and never miss each other. (Exotic equal types
such as `1.5 == Fraction(3, 2)` remain a documented edge case.)

Total capacity is divided evenly across shards, with remainders assigned to the
lowest shard indexes. Because a shard with zero capacity could never store a
key, the configuration requires `capacity >= shard_count`.

Every public read/write operation that can mutate metadata runs under the shard
lock. Single-flight entries are also shard-local, so unrelated keys can compute
concurrently while duplicate loads for the same key collapse to one loader call.
