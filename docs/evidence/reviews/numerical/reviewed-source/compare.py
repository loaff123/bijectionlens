"""Exact bounded comparison, with no numerical verdict after exhaustion."""
from .contract import Budget, ResourceLimit, normalize_atol, normalize_points
from .matching import hall_shortage, maximum_matching
from .models import ComparisonResult, ResourceEvidence
from .spatial import radius_graph


def compare(actual, expected, *, atol, limits=None) -> ComparisonResult:
    """Compare finite stored-binary64 multisets under an absolute modulus radius.

    Every occurrence stays in the complete tolerance graph, including exact
    common values. Check ``status`` explicitly; resource limits are inconclusive.
    """
    budget = Budget(limits)
    tolerance = normalize_atol(atol)
    if ((type(actual) is not list and type(actual) is not tuple)
            or (type(expected) is not list and type(expected) is not tuple)):
        raise TypeError('actual and expected must be builtin lists or tuples')
    actual_size, expected_size = len(actual), len(expected)
    try:
        # Check both lengths before creating either normalized coordinate array.
        for size in (actual_size, expected_size):
            if size > budget.limits.max_items:
                raise ResourceLimit('items', 0, size, budget.limits.max_items)
        left = normalize_points(actual, budget.limits)
        right = normalize_points(expected, budget.limits)
        if actual_size != expected_size:
            return ComparisonResult('size_mismatch', actual_size, expected_size,
                                    counts=budget.snapshot())
        graph = radius_graph(left, right, tolerance*tolerance, budget)
        matching = maximum_matching(graph, len(right), budget)
        if matching.cardinality == actual_size:
            return ComparisonResult('matched', actual_size, expected_size,
                                    pairs=matching.pairs, counts=budget.snapshot())
        hall = hall_shortage(graph, matching, budget)
        return ComparisonResult('mismatch', actual_size, expected_size,
                                pairs=matching.pairs, hall=hall,
                                counts=budget.snapshot())
    except ResourceLimit as error:
        return ComparisonResult('resource_limited', actual_size, expected_size,
                                counts=budget.snapshot(), reason=str(error),
                                resource=ResourceEvidence.from_error(error))
