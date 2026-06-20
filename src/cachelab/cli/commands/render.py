""" Render commands for the CLI """

from __future__ import annotations

from cachelab.core.cache import Cache
from cachelab.observability.tables import format_table


def fmt_float(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def stats_table(cache: Cache) -> str:
    stats = cache.stats()
    return format_table(
        ["metric", "value"],
        [
            ["hits", stats.hits],
            ["misses", stats.misses],
            ["hit_ratio", round(stats.hit_ratio, 4)],
            ["puts", stats.puts],
            ["deletes", stats.deletes],
            ["evictions", stats.evictions],
            ["expirations", stats.expirations],
            ["size", stats.size],
            ["queue_depth", stats.queue_depth],
            ["queue_dropped", stats.queue_dropped],
            ["worker_done", stats.worker_jobs_completed],
            ["worker_failed", stats.worker_jobs_failed],
            ["retries", stats.write_back_retries],
            ["stale_skips", stats.stale_write_back_jobs_skipped],
        ],
    )


def print_simulation(rows: list[dict[str, object]]) -> None:
    print(
        format_table(
            ["policy", "pattern", "requests", "hits", "misses", "hit_ratio", "evictions", "seconds"],
            [
                [
                    row.get("policy"),
                    row.get("pattern"),
                    row.get("requests"),
                    row.get("hits"),
                    row.get("misses"),
                    row.get("hit_ratio"),
                    row.get("evictions"),
                    row.get("seconds", "-"),
                ]
                for row in rows
            ],
        )
    )
