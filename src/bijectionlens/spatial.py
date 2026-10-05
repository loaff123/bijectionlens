"""Complete radius graphs from a deterministic, exact two-dimensional tree.

Tree construction is charged for index references, sorting comparisons and
bounding-box comparisons. ``tree_visits`` charges node/candidate inspections
and adjacency-ordering comparisons; it is deliberately conservative. Every
retained edge is charged before append. A partially constructed graph never
escapes this module on exhaustion.
"""
from dataclasses import dataclass
from functools import cmp_to_key
from typing import TYPE_CHECKING

from .geometry import box_squared_distance, squared_distance

if TYPE_CHECKING:
    from .contract import Budget, Point


@dataclass(slots=True)
class _Node:
    bounds: tuple
    indices: tuple[int, ...] = ()
    low: '_Node | None' = None
    high: '_Node | None' = None


def _build(points, indices, axis, budget):
    if len(indices) <= 8:
        budget.charge('tree_build', len(indices))
        first = points[indices[0]]
        lo_r = hi_r = first.real
        lo_i = hi_i = first.imag
        for index in indices[1:]:
            p = points[index]
            budget.charge('tree_build', 4)
            lo_r = min(lo_r, p.real)
            hi_r = max(hi_r, p.real)
            lo_i = min(lo_i, p.imag)
            hi_i = max(hi_i, p.imag)
        return _Node((lo_r, hi_r, lo_i, hi_i), tuple(indices))

    def order(a, b):
        p, q = points[a], points[b]
        x = p.real if axis == 0 else p.imag
        y = q.real if axis == 0 else q.imag
        budget.charge('tree_build')
        if x < y:
            return -1
        budget.charge('tree_build')
        if x > y:
            return 1
        budget.charge('tree_build')
        return -1 if a < b else 1

    indices.sort(key=cmp_to_key(order))
    middle = len(indices) // 2
    budget.charge('tree_build', len(indices))
    low = _build(points, indices[:middle], 1-axis, budget)
    high = _build(points, indices[middle:], 1-axis, budget)
    a, b = low.bounds, high.bounds
    budget.charge('tree_build', 4)
    return _Node((min(a[0], b[0]), max(a[1], b[1]),
                  min(a[2], b[2]), max(a[3], b[3])), low=low, high=high)


def radius_graph(left: tuple['Point', ...], right: tuple['Point', ...],
                 atol_squared, budget: 'Budget') -> tuple[tuple[int, ...], ...]:
    """Enumerate *all* edges satisfying exact squared distance <= radius²."""
    if not left or not right:
        return tuple(() for _ in left)
    budget.charge('tree_build', len(right))
    root = _build(right, list(range(len(right))), 0, budget)
    rows = []
    for point in left:
        row = []
        stack = [root]
        while stack:
            budget.charge('tree_visits')
            node = stack.pop()
            if box_squared_distance(point, node.bounds) > atol_squared:
                continue
            if node.indices:
                for index in node.indices:
                    budget.charge('tree_visits')
                    if squared_distance(point, right[index]) <= atol_squared:
                        budget.charge('edges')
                        row.append(index)
            else:
                stack.append(node.high)
                stack.append(node.low)

        def order(a, b):
            budget.charge('tree_visits')
            if a < b:
                return -1
            budget.charge('tree_visits')
            return 1 if a > b else 0

        row.sort(key=cmp_to_key(order))
        rows.append(tuple(row))
    return tuple(rows)
