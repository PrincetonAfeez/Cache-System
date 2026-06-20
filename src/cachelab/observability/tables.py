""" Table utilities for CacheLab """

from __future__ import annotations

from collections.abc import Sequence


def format_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    matrix = [[str(cell) for cell in headers], *[[str(cell) for cell in row] for row in rows]]
    widths = [max(len(row[index]) for row in matrix) for index in range(len(headers))]
    lines = [
        "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(matrix[0])),
        "  ".join("-" * width for width in widths),
    ]
    for row in matrix[1:]:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return "\n".join(lines)
