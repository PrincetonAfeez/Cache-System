# Benchmark Results

Run local benchmarks with:

```powershell
cachelab benchmark --policies lru,lfu,fifo --pattern hotspot --requests 50000
cachelab benchmark --policies lru,lfu,fifo --pattern looping --requests 50000
cachelab benchmark --policies lru,lfu,fifo --pattern sequential --requests 50000
```

Simulations run on a single shard by default (`--shards 1`) so the reported hit
ratio reflects the eviction policy itself, not capacity split across several
independent sub-caches. Increase `--shards` to observe how sharding partitions a
workload.

## Recorded results

Measured locally on Windows with Python 3.11, `capacity=100`, `requests=50000`,
`seed=0`, `shards=1`:

### Hotspot (zipfian)

| Policy | Hits | Misses | Hit ratio | Evictions | Seconds |
|--------|------|--------|-----------|-----------|---------|
| LRU    | 42805 | 7195 | 0.8561 | 7095 | 0.53 |
| LFU    | 42782 | 7218 | 0.8556 | 7118 | 0.90 |
| FIFO   | 41185 | 8815 | 0.8237 | 8715 | 0.37 |

LRU and LFU retain the hot key set better than FIFO, which evicts by insertion
order and throws away hot entries once they age out.

### Looping (working set fits capacity)

| Policy | Hits | Misses | Hit ratio | Evictions | Seconds |
|--------|------|--------|-----------|-----------|---------|
| LRU    | 49920 | 80 | 0.9984 | 0 | 0.23 |
| LFU    | 49920 | 80 | 0.9984 | 0 | 0.46 |
| FIFO   | 49920 | 80 | 0.9984 | 0 | 0.41 |

The working set sits just inside capacity, so every policy reaches a very high hit
ratio (~0.99). This is the "fits mostly inside capacity" case.

### Sequential (cold scan)

| Policy | Hits | Misses | Hit ratio | Evictions | Seconds |
|--------|------|--------|-----------|-----------|---------|
| LRU    | 0 | 50000 | 0.0 | 49900 | 1.30 |
| LFU    | 0 | 50000 | 0.0 | 49900 | 1.89 |
| FIFO   | 0 | 50000 | 0.0 | 49900 | 2.05 |

A pure scan of unique keys that never repeat. Nothing can be reused, so every
policy lands near 0.0. Caching cannot help a cold scan.

## What each pattern shows

- **looping** — the working set is sized to sit just inside capacity, so a
  recency policy holds the whole loop and every policy reaches a very high hit
  ratio (~0.99). This is the "fits mostly inside capacity" case.
- **sequential** — a pure scan of unique keys that never repeat. Nothing can be
  reused, so every policy lands near 0.0. Caching cannot help a cold scan.
- **hotspot / zipfian** — a small set of hot keys dominates. LRU and LFU retain
  those hot keys and clearly beat FIFO, which evicts by insertion order and
  throws hot entries away once they age out.

The headline comparison (`cachelab demo all`) uses the hotspot workload because
it is where the policies diverge: LRU and LFU keep more of the hot set resident
than FIFO does.

Reproduce the tables above:

```powershell
python -m cachelab.cli.main benchmark --policies lru,lfu,fifo --pattern hotspot --capacity 100 --requests 50000 --seed 0
python -m cachelab.cli.main benchmark --policies lru,lfu,fifo --pattern looping --capacity 100 --requests 50000 --seed 0
python -m cachelab.cli.main benchmark --policies lru,lfu,fifo --pattern sequential --capacity 100 --requests 50000 --seed 0
```
