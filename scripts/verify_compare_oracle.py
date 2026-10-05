"""Bounded small-case verifier qualification and field-tamper statistics.

Run from the checkout with: PYTHONPATH=src python scripts/verify_compare_oracle.py
This script deliberately uses a brute-force cardinality oracle. It supplements,
not replaces, the separately retained exhaustive graph and frozen qualification.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import json
import random

from bijectionlens import compare, verify_comparison
from bijectionlens.contract import Limits


def maximum_cardinality(left, right, atol):
    """Small integer-coordinate oracle without production normalization/geometry."""
    graph = [[j for j, b in enumerate(right)
              if (a.real-b.real)**2 + (a.imag-b.imag)**2 <= atol**2]
             for a in left]

    def visit(row, used):
        if row == len(graph):
            return 0
        best = visit(row + 1, used)
        for j in graph[row]:
            if not used & (1 << j):
                best = max(best, 1 + visit(row + 1, used | (1 << j)))
        return best

    return visit(0, 0)


def qualify():
    rng = random.Random(118037)
    counts = Counter()
    cardinalities = Counter()
    cases = [([], [], 0), ([0, 0, 3], [0, 3, 3], 0),
             ([0, .9], [0, -.9], 1)]
    for _ in range(120):
        n = rng.randrange(5)
        cases.append(([complex(rng.randrange(-2, 3), rng.randrange(-2, 3)) for _ in range(n)],
                      [complex(rng.randrange(-2, 3), rng.randrange(-2, 3)) for _ in range(n)],
                      rng.randrange(4)))
    fields_checked = set()
    for actual, expected, atol in cases:
        candidate = compare(actual, expected, atol=atol)
        assert len(candidate.pairs) == maximum_cardinality(actual, expected, atol)
        cardinalities[candidate.status] += 1
        raw = asdict(candidate)
        verdict = verify_comparison(actual, expected, atol=atol, result=raw).status
        assert verdict == 'valid', (actual, expected, atol, verdict)
        counts[verdict] += 1
        mutations = {
            'status': ('invented', 'invalid'),
            'actual_size': (len(actual) + 1, 'invalid'),
            'expected_size': (len(expected) + 1, 'invalid'),
            'pairs': ([[len(actual), 0]], 'invalid'),
            'hall': ({'left_indices': [len(actual)], 'neighbor_indices': [], 'deficiency': 1}, 'invalid'),
            'counts': ({'unrecognized': 0}, 'invalid'),
            'reason': ('x' * 4097, 'resource_limited'),
            'resource': ({'phase': 'items', 'used': 2**64, 'requested': 1, 'limit': 0}, 'resource_limited'),
            'version': (2, 'invalid'),
            'verification_status': ('valid', 'invalid'),
        }
        assert set(mutations) == set(raw)
        for field, (value, wanted) in mutations.items():
            fields_checked.add(field)
            changed = deepcopy(raw)
            changed[field] = value
            verdict = verify_comparison(actual, expected, atol=atol, result=changed).status
            assert verdict == wanted, (field, verdict, wanted)
            counts[verdict] += 1
        bounded = verify_comparison(actual, expected, atol=atol, result=raw,
                                    limits=Limits(max_verify_pairs=0)).status
        assert bounded == ('resource_limited' if actual else 'valid')
        counts[bounded] += 1
    return {'cases': len(cases), 'seed': 118037, 'result_statuses': dict(sorted(cardinalities.items())),
            'verification_statuses': dict(sorted(counts.items())),
            'tampered_fields': sorted(fields_checked)}


if __name__ == '__main__':
    print(json.dumps(qualify(), sort_keys=True, indent=2))
