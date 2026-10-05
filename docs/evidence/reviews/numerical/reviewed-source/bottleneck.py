"""Bounded exact minimax assignment with positive and strict-lower witnesses.

All distance/threshold tests use rationals. The decimal radius is display-only.
Counters accumulate across sorting, every threshold graph, both certificate
matchings, and the exact bit-ordered binary64 search. In particular ``edges``
counts *all* retained edges across graphs, a stricter envelope than peak memory.
"""
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from functools import cmp_to_key
import struct

from .contract import Budget, ResourceLimit, format_certificate_decimal, normalize_points
from .geometry import squared_distance
from .matching import hall_shortage, maximum_matching
from .models import BottleneckResult, ResourceEvidence

_MAX_FINITE_BITS = 0x7FEFFFFFFFFFFFFF


def _from_bits(bits):
    return struct.unpack('>d', struct.pack('>Q', bits))[0]


def _least_binary64(q: Fraction, budget: Budget) -> str | None:
    if q == 0:
        return (0.0).hex()
    budget.charge('filtration_checks')
    if Fraction.from_float(_from_bits(_MAX_FINITE_BITS))**2 < q:
        return None
    low, high = 0, _MAX_FINITE_BITS
    while low < high:
        budget.charge('filtration_steps')
        middle = (low + high) // 2
        budget.charge('filtration_checks')
        if Fraction.from_float(_from_bits(middle))**2 >= q:
            high = middle
        else:
            low = middle + 1
    return _from_bits(low).hex()


def _threshold_graph(matrix, q, strict, budget):
    budget.charge('filtration_steps')
    rows = []
    for distances in matrix:
        row = []
        for j, distance in enumerate(distances):
            budget.charge('filtration_checks')
            accepts = distance < q if strict else distance <= q
            if accepts:
                budget.charge('edges')
                row.append(j)
        rows.append(tuple(row))
    return tuple(rows)


def _sorted_thresholds(matrix, budget):
    budget.charge('filtration_checks', sum(len(row) for row in matrix))
    values = [distance for row in matrix for distance in row]

    def order(a, b):
        budget.charge('filtration_checks')
        if a < b:
            return -1
        budget.charge('filtration_checks')
        return 1 if a > b else 0

    values.sort(key=cmp_to_key(order))
    unique = []
    for value in values:
        budget.charge('filtration_checks')
        if not unique or value != unique[-1]:
            unique.append(value)
    return unique


def bottleneck(actual, expected, *, limits=None) -> BottleneckResult:
    """Find exact minimum squared absolute radius, or an inconclusive limit.

    ``q_numerator/q_denominator`` is authoritative. ``approximate_atol`` is a
    decimal display of sqrt(q); ``least_finite_binary64_atol`` is an exact,
    separately certified upward radius, or None if no finite radius suffices.
    """
    budget = Budget(limits)
    if ((type(actual) is not list and type(actual) is not tuple)
            or (type(expected) is not list and type(expected) is not tuple)):
        raise TypeError('actual and expected must be builtin lists or tuples')
    actual_size, expected_size = len(actual), len(expected)
    try:
        for size in (actual_size, expected_size):
            if size > budget.limits.max_items:
                raise ResourceLimit('items', 0, size, budget.limits.max_items)
        left = normalize_points(actual, budget.limits)
        right = normalize_points(expected, budget.limits)
        if actual_size != expected_size:
            return BottleneckResult('size_mismatch', actual_size, expected_size,
                                    counts=budget.snapshot())
        if not left:
            return BottleneckResult('optimal', 0, 0, q_numerator='0',
                                    q_denominator='1', approximate_atol='0',
                                    least_finite_binary64_atol=(0.0).hex(),
                                    counts=budget.snapshot())
        matrix = []
        for a in left:
            row = []
            for b in right:
                budget.charge('bottleneck_pairs')
                row.append(squared_distance(a, b))
            matrix.append(row)
        thresholds = _sorted_thresholds(matrix, budget)
        low, high = 0, len(thresholds) - 1
        best_index, best_matching = -1, None
        while low < high:
            middle = (low + high) // 2
            graph = _threshold_graph(matrix, thresholds[middle], False, budget)
            matching = maximum_matching(graph, expected_size, budget)
            if matching.cardinality == actual_size:
                high = middle
                best_index, best_matching = middle, matching
            else:
                low = middle + 1
        q = thresholds[low]
        if best_index != low:
            graph = _threshold_graph(matrix, q, False, budget)
            best_matching = maximum_matching(graph, expected_size, budget)
        strict_hall = None
        if q > 0:
            strict_graph = _threshold_graph(matrix, q, True, budget)
            strict_matching = maximum_matching(strict_graph, expected_size, budget)
            strict_hall = hall_shortage(strict_graph, strict_matching, budget)
        least = _least_binary64(q, budget)
        budget.charge('filtration_steps')
        with localcontext(Context(prec=18, rounding=ROUND_HALF_EVEN,
                                  Emin=-999999, Emax=999999, capitals=1,
                                  clamp=0, flags=[], traps=[])):
            approximation = str((Decimal(q.numerator)/Decimal(q.denominator)).sqrt())
        return BottleneckResult('optimal', actual_size, expected_size,
                                q_numerator=format_certificate_decimal(q.numerator),
                                q_denominator=format_certificate_decimal(q.denominator),
                                pairs=best_matching.pairs, strict_hall=strict_hall,
                                approximate_atol=approximation,
                                least_finite_binary64_atol=least,
                                counts=budget.snapshot())
    except ResourceLimit as error:
        return BottleneckResult('resource_limited', actual_size, expected_size,
                                counts=budget.snapshot(), reason=str(error),
                                resource=ResourceEvidence.from_error(error))
