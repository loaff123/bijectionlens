"""Deterministic iterative Hopcroft--Karp and full-neighborhood Hall evidence.

``matching_scans`` covers vertex initialization/visits, edge inspections, and
path rewrites. It is a cumulative work counter, including Hall extraction.
These internal helpers consume already bounded, complete adjacency tuples.
"""
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contract import Budget
    from .models import HallEvidence


@dataclass(frozen=True, slots=True)
class Matching:
    """Original occurrence partners; -1 denotes an unmatched occurrence."""

    left: tuple[int, ...]
    right: tuple[int, ...]

    @property
    def cardinality(self) -> int:
        return sum(v >= 0 for v in self.left)

    @property
    def pairs(self) -> tuple[tuple[int, int], ...]:
        return tuple((u, v) for u, v in enumerate(self.left) if v >= 0)


def maximum_matching(graph, right_size: int, budget: 'Budget') -> Matching:
    """Return a maximum matching without recursive augmenting-path traversal."""
    n = len(graph)
    budget.charge('matching_scans', n)
    budget.charge('matching_scans', right_size)
    left = [-1] * n
    right = [-1] * right_size
    unreachable = n + 1
    while True:
        # Multi-source BFS locates the shortest augmenting-path layer.
        distance = [unreachable] * n
        queue = deque()
        for u in range(n):
            budget.charge('matching_scans')
            if left[u] == -1:
                distance[u] = 0
                queue.append(u)
        shortest = unreachable
        while queue:
            budget.charge('matching_scans')
            u = queue.popleft()
            if distance[u] >= shortest:
                continue
            for v in graph[u]:
                budget.charge('matching_scans')
                mate = right[v]
                if mate == -1:
                    shortest = distance[u] + 1
                elif distance[mate] == unreachable:
                    distance[mate] = distance[u] + 1
                    queue.append(mate)
        if shortest == unreachable:
            break
        budget.charge('matching_scans', n)
        cursor = [0] * n
        for root in range(n):
            budget.charge('matching_scans')
            if left[root] != -1 or distance[root] == unreachable:
                continue
            # via[k] is the edge from stack[k] to the mate stack[k+1].
            stack = [root]
            via = []
            augmented = False
            while stack and not augmented:
                u = stack[-1]
                advanced = False
                while cursor[u] < len(graph[u]):
                    budget.charge('matching_scans')
                    v = graph[u][cursor[u]]
                    cursor[u] += 1
                    mate = right[v]
                    if mate == -1 and distance[u] + 1 == shortest:
                        budget.charge('matching_scans', len(stack))
                        left[u] = v
                        right[v] = u
                        for k in range(len(via) - 1, -1, -1):
                            a, b = stack[k], via[k]
                            left[a] = b
                            right[b] = a
                        augmented = True
                        break
                    if (mate != -1 and distance[mate] == distance[u] + 1
                            and distance[mate] < shortest):
                        stack.append(mate)
                        via.append(v)
                        advanced = True
                        break
                if not augmented and not advanced:
                    budget.charge('matching_scans')
                    distance[u] = unreachable
                    stack.pop()
                    if via:
                        via.pop()
    return Matching(tuple(left), tuple(right))


def hall_shortage(graph, matching: Matching, budget: 'Budget') -> 'HallEvidence':
    """All left-reachable occurrences and their complete right neighborhood."""
    from .models import HallEvidence

    budget.charge('matching_scans', len(matching.left) + len(matching.right))
    seen_left = [False] * len(matching.left)
    seen_right = [False] * len(matching.right)
    queue = deque()
    for u, v in enumerate(matching.left):
        budget.charge('matching_scans')
        if v == -1:
            seen_left[u] = True
            queue.append(u)
    while queue:
        budget.charge('matching_scans')
        u = queue.popleft()
        for v in graph[u]:
            budget.charge('matching_scans')
            if seen_right[v]:
                continue
            seen_right[v] = True
            mate = matching.right[v]
            if mate != -1 and not seen_left[mate]:
                seen_left[mate] = True
                queue.append(mate)
    budget.charge('matching_scans', len(seen_left) + len(seen_right))
    left_indices = tuple(i for i, seen in enumerate(seen_left) if seen)
    neighbor_indices = tuple(i for i, seen in enumerate(seen_right) if seen)
    return HallEvidence(left_indices, neighbor_indices,
                        len(left_indices) - len(neighbor_indices))
