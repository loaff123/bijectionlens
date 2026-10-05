#!/usr/bin/env python3
"""Reproducible production checks using independent mathematical oracles.

No optimizer, graph builder, or production arithmetic is used to compute an
expected answer. Production functions are imported only as test targets in
ProductionTargets. NumPy/SciPy are optional, test-only full-profile baselines.
Run against an installed package; this script does not alter sys.path.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import random
import struct
import subprocess
import sys
import time


# Independent integer arithmetic: no production imports in these oracles.
def distance_ratio(a, b):
    """Return an unreduced exact squared-distance numerator and denominator."""
    a, b = complex(a), complex(b)
    ar, ad = a.real.as_integer_ratio()
    br, bd = b.real.as_integer_ratio()
    cr, cd = a.imag.as_integer_ratio()
    dr, dd = b.imag.as_integer_ratio()
    x, xd = ar * bd - br * ad, ad * bd
    y, yd = cr * dd - dr * cd, cd * dd
    return x * x * yd * yd + y * y * xd * xd, xd * xd * yd * yd


def exact_edge(a, b, atol):
    dn, dd = distance_ratio(a, b)
    tn, td = float(atol).as_integer_ratio()
    return dn * td * td <= tn * tn * dd


def oracle_graph(actual, expected, atol):
    return tuple(tuple(j for j, b in enumerate(expected) if exact_edge(a, b, atol))
                 for a in actual)


def oracle_cardinality(graph):
    """Exhaustive subset-state DP, independent of augmenting-path matching."""
    states = {0}
    for row in graph:
        previous = states
        states = previous | {mask | (1 << j) for mask in previous for j in row
                             if not mask & (1 << j)}
    return max(map(int.bit_count, states))


def oracle_bottleneck(actual, expected):
    assert len(actual) == len(expected)
    matrix = [[Fraction(*distance_ratio(a, b)) for b in expected] for a in actual]
    return min(max((matrix[i][j] for i, j in enumerate(perm)), default=Fraction(0))
               for perm in itertools.permutations(range(len(actual))))


def check_graph_certificate(graph, right_size, pairs, hall, expected_cardinality=None):
    """Check pair validity and the FULL neighborhood; Hall = (S, N(S), d)."""
    assert len({i for i, _ in pairs}) == len(pairs), "repeated left pair index"
    assert len({j for _, j in pairs}) == len(pairs), "repeated right pair index"
    assert all(0 <= i < len(graph) and 0 <= j < right_size and j in graph[i]
               for i, j in pairs), "infeasible pair"
    if expected_cardinality is None:
        expected_cardinality = oracle_cardinality(graph)
    assert len(pairs) == expected_cardinality, "nonmaximum matching"
    if len(pairs) == len(graph):
        assert hall is None, "unexpected Hall shortage on left-perfect matching"
        return
    assert hall is not None, "missing Hall shortage"
    left, right, deficiency = hall
    assert len(set(left)) == len(left) and len(set(right)) == len(right)
    assert all(0 <= i < len(graph) for i in left)
    assert all(0 <= j < right_size for j in right)
    assert set(right) == {j for i in left for j in graph[i]}, "omitted or extra neighbor"
    assert len(left) - len(right) == deficiency == len(graph) - len(pairs) > 0


def check_binary64_ceiling(q, tolerance):
    if tolerance is None:
        n, d = sys.float_info.max.as_integer_ratio()
        assert n * n < q * d * d, "a finite tolerance suffices"
        return
    assert type(tolerance) is float and math.isfinite(tolerance) and tolerance >= 0
    n, d = tolerance.as_integer_ratio()
    assert n * n >= q * d * d
    if q == 0:
        assert tolerance == 0 and math.copysign(1, tolerance) == 1
    else:
        previous = math.nextafter(tolerance, 0.0)
        n, d = previous.as_integer_ratio()
        assert n * n < q * d * d, "tolerance is not least binary64 value"


def encode(values):
    return [[complex(x).real.hex(), complex(x).imag.hex()] for x in values]


def frozen_cases():
    rng = random.Random(10467011)
    for case in range(600):
        n = rng.randrange(8)
        actual = [complex(rng.randrange(-3, 4), rng.randrange(-3, 4)) for _ in range(n)]
        expected = [complex(rng.randrange(-3, 4), rng.randrange(-3, 4)) for _ in range(n)]
        yield f"random-{case:03d}", actual, expected, rng.choice([0, .5, 1, 2, 4])


def permutation_cases():
    for i, actual in enumerate(itertools.permutations([.75, 0, 8])):
        for j, expected in enumerate(itertools.permutations([0, 1.5, 8])):
            yield f"permutation-{i}-{j}", list(actual), list(expected), .8


def boundary_cases():
    tiny = 5e-324
    yield from [
        ("pythagorean", [3 + 4j], [0], 5),
        ("pythagorean-below", [3 + 4j], [0], math.nextafter(5, 0)),
        ("pythagorean-above", [3 + 4j], [0], math.nextafter(5, math.inf)),
        ("huge-opposite", [1e308 + 1e308j], [-1e308 - 1e308j], 1e308),
        ("huge-equal", [1e308 + 1e308j], [1e308 + 1e308j], 0),
        ("huge-real-limit", [1e308], [0], 1e308),
        ("tiny-real-limit", [tiny], [0], tiny),
        ("tiny-complex-outside", [complex(tiny, tiny)], [0], tiny),
        ("tiny-opposite", [tiny], [-tiny], tiny),
        ("tiny-equal", [complex(tiny, tiny)], [complex(tiny, tiny)], 0),
        ("signed-zero", [-0.0, complex(-0.0, -0.0)], [0.0, 0j], 0),
        ("exact-cancel-trap", [0, .9], [0, -.9], 1),
        ("duplicate-shortage", [0, 0, 3], [0, 3, 3], .1),
        ("empty", [], [], 0),
        ("repeated-exact", [1j] * 4, [1j] * 4, 0),
        ("no-edges", [0, 1], [10, 11], .25),
    ]


def utility_cases():
    yield from [
        ("complex-sort", [-.001 + 1j, .001 - 1j], [.001 + 1j, -.001 - 1j], .01),
        ("first-fit-overlap", [.75, 0], [0, 1.5], .8),
        ("min-sum-is-not-bottleneck", [0j, 3 + 0j], [0j, -1 + 2.5j], 3),
        ("all-baselines-work", [0, .1 + 3j, 7], [7.01, .01, .11 + 3j], .02),
        ("hall-duplicate-shortage", [0, 0, 3], [0, 3, 3], .1),
    ]


def frozen_bottleneck_cases():
    rng = random.Random(10467012)
    for case in range(80):
        n = rng.randrange(7)
        actual = [complex(rng.randrange(-3, 4), rng.randrange(-3, 4)) for _ in range(n)]
        expected = [complex(rng.randrange(-3, 4), rng.randrange(-3, 4)) for _ in range(n)]
        yield f"frozen-bottleneck-{case:03d}", actual, expected


def additional_bottleneck_cases():
    """500 cases, including 25 size-seven and 75 size-six factorial checks."""
    rng = random.Random(10467013)
    for case in range(500):
        n = 7 if case < 25 else 6 if case < 100 else rng.randrange(6)
        exponent = rng.choice([-1074, -1022, -500, -1, 0, 100, 1000])
        step = math.ldexp(1., exponent)
        actual = [complex(rng.randrange(-3, 4) * step, rng.randrange(-3, 4) * step)
                  for _ in range(n)]
        expected = [complex(rng.randrange(-3, 4) * step, rng.randrange(-3, 4) * step)
                    for _ in range(n)]
        yield f"additional-bottleneck-{case:03d}", actual, expected


def sorting_baseline(actual, expected, atol):
    key = lambda z: (complex(z).real, complex(z).imag)
    return len(actual) == len(expected) and all(
        exact_edge(a, b, atol) for a, b in zip(sorted(actual, key=key), sorted(expected, key=key)))


def first_fit_baseline(actual, expected, atol):
    remaining = list(range(len(expected)))
    for a in actual:
        for j in remaining:
            if exact_edge(a, expected[j], atol):
                remaining.remove(j)
                break
        else:
            return False
    return not remaining


def random_finite(rng):
    while True:
        value = struct.unpack(">d", rng.getrandbits(64).to_bytes(8, "big"))[0]
        if math.isfinite(value):
            return value


def hall_tuple(hall):
    if hall is None:
        return None
    return hall.left_indices, hall.neighbor_indices, hall.deficiency


class ProductionTargets:
    """Production imports are isolated here and used only as the test subject."""
    def __init__(self):
        import bijectionlens
        from bijectionlens.contract import Budget, Limits, normalize_atol, normalize_points
        from bijectionlens.geometry import squared_distance
        from bijectionlens.matching import maximum_matching, hall_shortage
        from bijectionlens.spatial import radius_graph
        self.api = bijectionlens
        self.Budget, self.Limits = Budget, Limits
        self.normalize_atol, self.normalize_points = normalize_atol, normalize_points
        self.squared_distance = squared_distance
        self.maximum_matching, self.hall_shortage = maximum_matching, hall_shortage
        self.radius_graph = radius_graph
        self.source_dir = Path(bijectionlens.__file__).resolve().parent

    def graph(self, graph, right_size, expected_cardinality=None):
        budget = self.Budget(self.Limits())
        matching = self.maximum_matching(graph, right_size, budget)
        pairs = tuple((i, j) for i, j in enumerate(matching.left) if j >= 0)
        hall = self.hall_shortage(graph, matching, budget) if len(pairs) < len(graph) else None
        check_graph_certificate(graph, right_size, pairs, hall_tuple(hall), expected_cardinality)
        assert len(matching.left) == len(graph) and len(matching.right) == right_size
        assert all(matching.right[j] == i for i, j in pairs)
        return {"cardinality": len(pairs), "pairs": pairs, "hall": hall_tuple(hall)}

    def spatial(self, actual, expected, atol):
        limits = self.Limits()
        points = self.normalize_points(actual, limits)
        other = self.normalize_points(expected, limits)
        q = self.normalize_atol(atol) ** 2
        got = self.radius_graph(points, other, q, self.Budget(limits))
        want = oracle_graph(actual, expected, atol)
        assert tuple(map(tuple, got)) == want, "spatial graph omits or invents an edge"
        return {"edges": sum(map(len, want))}

    def predicate(self, a, b, atol):
        limits = self.Limits()
        x, y = self.normalize_points([a, b], limits)
        got = self.squared_distance(x, y) <= self.normalize_atol(atol) ** 2
        expected = exact_edge(a, b, atol)
        assert got == expected, "exact integer-cross-product predicate disagreement"
        return expected

    def comparison(self, actual, expected, atol, scipy_card=None):
        graph = oracle_graph(actual, expected, atol)
        want = oracle_cardinality(graph)
        if scipy_card is not None:
            assert want == scipy_card(graph, len(expected))
        result = self.api.compare(actual, expected, atol=atol)
        assert result.status == ("matched" if want == len(actual) else "mismatch")
        assert result.actual_size == len(actual) and result.expected_size == len(expected)
        assert len(result.pairs) == want
        check_graph_certificate(graph, len(expected), result.pairs, hall_tuple(result.hall), want)
        verification = self.api.verify_comparison(actual, expected, atol=atol, result=result)
        assert verification.status == "valid", verification
        return {"status": result.status, "cardinality": want, "pairs": result.pairs,
                "hall": hall_tuple(result.hall), "verification": verification.status,
                "scipy_cardinality": want if scipy_card is not None else None}

    def bottleneck(self, actual, expected):
        want = oracle_bottleneck(actual, expected)
        result = self.api.bottleneck(actual, expected)
        assert result.status == "optimal", result
        q = Fraction(int(result.q_numerator), int(result.q_denominator))
        assert q == want, "bottleneck differs from all-permutations oracle"
        graph = tuple(tuple(j for j, b in enumerate(expected)
                            if Fraction(*distance_ratio(a, b)) <= q) for a in actual)
        check_graph_certificate(graph, len(expected), result.pairs, None, len(actual))
        if q > 0:
            strict = tuple(tuple(j for j, b in enumerate(expected)
                                 if Fraction(*distance_ratio(a, b)) < q) for a in actual)
            left, right, deficiency = hall_tuple(result.strict_hall)
            assert len(set(left)) == len(left) and len(set(right)) == len(right)
            assert all(0 <= i < len(actual) for i in left)
            assert set(right) == {j for i in left for j in strict[i]}
            assert len(left) - len(right) == deficiency > 0
        else:
            assert result.strict_hall is None
        tolerance = result.least_finite_binary64_atol
        tolerance = float.fromhex(tolerance) if tolerance is not None else None
        check_binary64_ceiling(q, tolerance)
        verification = self.api.verify_bottleneck(actual, expected, result=result)
        assert verification.status == "valid", verification
        return {"q_numerator": str(q.numerator), "q_denominator": str(q.denominator),
                "pairs": result.pairs, "strict_hall": hall_tuple(result.strict_hall),
                "least_finite_binary64_atol": result.least_finite_binary64_atol,
                "verification": verification.status}


def scipy_tools():
    import numpy as np
    import scipy
    from scipy.optimize import linear_sum_assignment
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import maximum_bipartite_matching

    def cardinality(graph, right_size):
        rows = [i for i, row in enumerate(graph) for _ in row]
        cols = [j for row in graph for j in row]
        matrix = csr_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)),
                            shape=(len(graph), right_size))
        return int(np.count_nonzero(maximum_bipartite_matching(matrix, perm_type="column") >= 0))

    def minsum(actual, expected, atol):
        costs = np.array([[abs(a - b) for b in expected] for a in actual])
        ri, ci = linear_sum_assignment(costs)
        pairs = [(int(i), int(j)) for i, j in zip(ri, ci)]
        return all(exact_edge(actual[i], expected[j], atol) for i, j in pairs), pairs

    return np, scipy, cardinality, minsum


def numpy_cases(np):
    for n in (2, 3, 4, 5, 6, 8, 12, 16):
        coefficients = np.zeros(n + 1)
        coefficients[0] = coefficients[-1] = 1
        yield (f"initial-control-x{n}-plus-one", np.roots(coefficients).tolist(),
               np.polynomial.polynomial.polyroots(coefficients).tolist(), 1e-12)
    for i, roots in enumerate(((-1j, 0, 1j), (-1j, 1j), (-1j, 0, 1j, 2),
                               (-2j, -1j, 0, 1j, 2j))):
        coefficients = np.polynomial.polynomial.polyfromroots(roots)
        yield (f"known-root-{i}", np.polynomial.polynomial.polyroots(coefficients).tolist(),
               list(roots), 1e-12)


def source_hashes(target):
    return {f"bijectionlens/{path.name}": hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(target.source_dir.glob("*.py"))}


def run(output_dir, profile):
    assert __debug__, "qualification requires assertions; do not run Python with -O"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Never silently replace a previous qualification receipt.
    receipt = output_dir / "summary.json"
    rows_path = output_dir / "results.jsonl"
    if receipt.exists() or rows_path.exists():
        raise FileExistsError("use a fresh output directory for each qualification run")
    target = ProductionTargets()
    before = source_hashes(target)
    versions = {"python": platform.python_version(), "numpy": None, "scipy": None}
    np = scipy_card = minsum = None
    if profile == "full":
        np, scipy, scipy_card, minsum = scipy_tools()
        versions.update(numpy=np.__version__, scipy=scipy.__version__)
    summary = {"classification": "fresh production qualification", "profile": profile,
               "status": "running", "versions": versions, "checks": {},
               "source_sha256": before,
               "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "seeds": {"frozen": 10467011, "frozen_bottleneck": 10467012,
                         "additional_bottleneck": 10467013, "graphs": 1104202605,
                         "spatial": 1104202606, "predicate": 1104202607},
               "remote_ci": "not established by this local run"}
    started = time.monotonic()
    counts = summary["checks"]
    with rows_path.open("x", encoding="utf-8") as stream:
        def record(group, identity, details):
            stream.write(json.dumps({"group": group, "id": identity, **details}, sort_keys=True) + "\n")
            counts[group] = counts.get(group, 0) + 1

        def phase(name):
            stream.flush()
            print(f"checking {name}", file=sys.stderr, flush=True)

        try:
            phase("all square graphs through 4 by 4")
            for n in range(5):
                for mask in range(1 << (n * n)):
                    graph = tuple(tuple(j for j in range(n) if mask & (1 << (i * n + j)))
                                  for i in range(n))
                    record("exhaustive_square_graphs", f"{n}:{mask}", target.graph(graph, n))
            assert counts["exhaustive_square_graphs"] == 66067
            rng = random.Random(1104202605)
            phase("rectangular and SciPy graphs")
            for case in range(500):
                n, m = rng.randrange(9), rng.randrange(9)
                graph = tuple(tuple(j for j in range(m) if rng.random() < .45) for _ in range(n))
                expected = oracle_cardinality(graph)
                if scipy_card is not None:
                    assert scipy_card(graph, m) == expected
                record("rectangular_graphs", case, {"graph": graph, "right_size": m,
                       **target.graph(graph, m, expected)})
            if scipy_card is not None:
                for case in range(2000):
                    n, m = rng.randrange(19), rng.randrange(19)
                    density = rng.choice([0, .05, .2, .5, .9, 1])
                    graph = tuple(tuple(j for j in range(m) if rng.random() < density)
                                  for _ in range(n))
                    expected = scipy_card(graph, m)
                    record("scipy_random_graphs", case, {"graph": graph, "right_size": m,
                           "scipy_cardinality": expected, **target.graph(graph, m, expected)})
            phase("extreme spatial graphs")
            rng = random.Random(1104202606)
            for case in range(240):
                n = rng.randrange(9, 43)
                if case % 3 == 0:
                    actual = [complex(random_finite(rng), random_finite(rng)) for _ in range(n)]
                    expected = [complex(random_finite(rng), random_finite(rng)) for _ in range(n)]
                    atol = abs(random_finite(rng))
                else:
                    step = math.ldexp(1., rng.choice([-1074, -1050, -1022, -1000, -500, -3, 0, 400, 900, 1018]))
                    actual = [complex(rng.randrange(-10, 11) * step, rng.randrange(-10, 11) * step)
                              for _ in range(n)]
                    expected = [complex(rng.randrange(-10, 11) * step, rng.randrange(-10, 11) * step)
                                for _ in range(n)]
                    atol = rng.randrange(8) * step
                record("extreme_spatial_graphs", case, {"actual_hex": encode(actual),
                       "expected_hex": encode(expected), "atol_hex": float(atol).hex(),
                       **target.spatial(actual, expected, atol)})
            phase("10000 exact predicate checks")
            rng = random.Random(1104202607)
            for case in range(10000):
                if case % 3 == 0:
                    step = math.ldexp(1., rng.choice([-1074, -1050, -1022, -500, -1, 0, 100, 1000]))
                    a = complex(rng.randrange(-3, 4) * step, rng.randrange(-3, 4) * step)
                    b = complex(rng.randrange(-3, 4) * step, rng.randrange(-3, 4) * step)
                    atol = rng.randrange(5) * step
                else:
                    a = complex(random_finite(rng), random_finite(rng))
                    b = complex(random_finite(rng), random_finite(rng))
                    atol = abs(random_finite(rng))
                record("exact_predicates", case, {"points_hex": encode([a, b]),
                       "atol_hex": float(atol).hex(), "edge": target.predicate(a, b, atol)})
            phase("frozen comparisons, permutations, boundaries and baselines")
            for group, cases in (("frozen_comparisons", frozen_cases()),
                                 ("permutations", permutation_cases()), ("boundaries", boundary_cases())):
                for name, actual, expected, atol in cases:
                    record(group, name, {"actual_hex": encode(actual), "expected_hex": encode(expected),
                           "atol_hex": float(atol).hex(), **target.comparison(actual, expected, atol, scipy_card)})
            for name, actual, expected, atol in utility_cases():
                result = target.comparison(actual, expected, atol, scipy_card)
                baselines = {"sort_then_exact_predicate": sorting_baseline(actual, expected, atol),
                             "first_fit_then_remove": first_fit_baseline(actual, expected, atol),
                             "scipy_tolerance_graph": None if scipy_card is None else result["status"] == "matched"}
                if minsum is not None:
                    baseline_pass, pairs = minsum(actual, expected, atol)
                    baselines.update(minimum_sum_then_threshold=baseline_pass, minimum_sum_pairs=pairs)
                if name == "complex-sort":
                    assert not baselines["sort_then_exact_predicate"] and result["status"] == "matched"
                elif name == "first-fit-overlap":
                    assert not baselines["first_fit_then_remove"] and result["status"] == "matched"
                elif name == "min-sum-is-not-bottleneck" and minsum is not None:
                    assert not baselines["minimum_sum_then_threshold"] and result["status"] == "matched"
                elif name == "all-baselines-work":
                    assert all(v for k, v in baselines.items() if v is not None and not k.endswith("pairs"))
                record("utility_baselines", name, {"actual_hex": encode(actual), "expected_hex": encode(expected),
                       "atol_hex": float(atol).hex(), "baselines": baselines, **result})
            phase("580 permutation bottleneck checks")
            for group, cases in (("frozen_bottleneck", frozen_bottleneck_cases()),
                                 ("additional_bottleneck", additional_bottleneck_cases())):
                for name, actual, expected in cases:
                    record(group, name, {"actual_hex": encode(actual), "expected_hex": encode(expected),
                           **target.bottleneck(actual, expected)})
            if np is not None:
                phase("12 exploratory NumPy root cases")
                sorting_passes = 0
                for name, actual, expected, atol in numpy_cases(np):
                    # The size-sixteen sparse graph still makes subset DP inexpensive.
                    result = target.comparison(actual, expected, atol, scipy_card)
                    assert result["status"] == "matched"
                    sorted_pass = bool(np.allclose(np.sort_complex(actual), np.sort_complex(expected),
                                                  atol=atol, rtol=0))
                    sorting_passes += sorted_pass
                    record("numpy_exploratory", name, {"actual_hex": encode(actual), "expected_hex": encode(expected),
                           "atol_hex": float(atol).hex(), "sorted_allclose": sorted_pass, **result})
                summary["numpy_sorting"] = {"passes": sorting_passes, "false_negatives": 12 - sorting_passes,
                                            "classification": "exploratory, not held out; every case retained"}
            after = source_hashes(target)
            assert before == after, "production source changed during qualification"
            summary.update(status="passed", discrepancies=0)
        except Exception as exc:
            summary.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            summary["seconds"] = round(time.monotonic() - started, 6)
            stream.flush()
            summary["results_sha256"] = hashlib.sha256(rows_path.read_bytes()).hexdigest()
            receipt.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary



def capacity_case_spec(name):
    if name == "sparse-10000":
        expected = [complex(x, y) for x in range(100) for y in range(100)]
        actual = [z + .125 + .125j for z in expected]
        random.Random(10467011).shuffle(actual)
        return {"kind": "compare", "actual": actual, "expected": expected,
                "atol": .25, "limits": {}}
    if name == "dense-400":
        return {"kind": "compare", "actual": [0.] * 400, "expected": [0.] * 400,
                "atol": 0., "limits": {"max_edges": 20000}}
    if name in ("extreme-bottleneck-250", "extreme-bottleneck-500"):
        n = 250 if name.endswith("-250") else 500
        # Huge and subnormal components coexist in almost every exact distance.
        # 250 squared is the reduced hard pair cap; 500 is an over-cap control.
        rng = random.Random(10467015)
        large = math.ldexp(1., 1000)
        tiny = math.ldexp(1., -1074)
        actual = [complex(rng.choice([-3, -1, 1, 3]) * large,
                          rng.randrange(-7, 8) * tiny) for _ in range(n)]
        expected = [complex(rng.choice([-2, 0, 2]) * large,
                            rng.randrange(-7, 8) * tiny) for _ in range(n)]
        return {"kind": "bottleneck", "actual": actual, "expected": expected, "limits": {}}
    raise ValueError("unknown capacity profile")


def capacity_worker(name):
    target = ProductionTargets()
    spec = capacity_case_spec(name)
    actual, expected = spec["actual"], spec["expected"]
    limits = target.Limits(**spec["limits"])
    start = time.monotonic()
    if spec["kind"] == "compare":
        result = target.api.compare(actual, expected, atol=spec["atol"], limits=limits)
    else:
        result = target.api.bottleneck(actual, expected, limits=limits)
    solver_seconds = time.monotonic() - start
    if name == "sparse-10000":
        assert result.status == "matched" and len(result.pairs) == 10000
        assert len({i for i, _ in result.pairs}) == len({j for _, j in result.pairs}) == 10000
        assert all(exact_edge(actual[i], expected[j], spec["atol"]) for i, j in result.pairs)
        verification = target.api.verify_comparison(actual, expected, atol=spec["atol"], result=result)
        assert verification.status == "valid"
    elif name == "dense-400":
        assert result.status == "resource_limited" and not result.pairs and result.hall is None
        assert result.resource.phase == "edges" and result.resource.used == 20000
        verification = None
    elif name == "extreme-bottleneck-500":
        assert result.status == "resource_limited"
        assert result.resource.phase == "bottleneck_pairs"
        assert result.resource.limit == 62500
        assert 0 <= result.resource.used <= result.resource.limit
        assert result.resource.used + result.resource.requested > result.resource.limit
        assert not result.pairs and result.q_numerator is None
        verification = None
    else:
        assert result.status in ("optimal", "resource_limited")
        if result.status == "optimal":
            verification = target.api.verify_bottleneck(actual, expected, result=result)
            assert verification.status == "valid"
        else:
            assert not result.pairs and result.q_numerator is None and result.q_denominator is None
            verification = None
    peak_rss = None
    try:
        import resource
        measured = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform.startswith("linux"):
            peak_rss = measured * 1024
        elif sys.platform == "darwin":
            peak_rss = measured
    except ImportError:
        pass
    resource_evidence = (None if result.resource is None else
                         {key: getattr(result.resource, key) for key in ("phase", "used", "requested", "limit")})
    return {"id": name, "status": result.status, "solver_seconds": round(solver_seconds, 6),
            "total_seconds": round(time.monotonic() - start, 6), "peak_rss_bytes": peak_rss,
            "peak_rss_scope": "fresh child process, including imports and independent verification",
            "counts": dict(result.counts), "resource": resource_evidence,
            "verification": None if verification is None else verification.status,
            "source_sha256": source_hashes(target), "python": platform.python_version(),
            "platform": platform.system(), "hard_memory_limit_enforced": False}


def run_capacities(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt = output_dir / "summary.json"
    if receipt.exists():
        raise FileExistsError("use a fresh output directory for each capacity run")
    cases = []
    for name in ("sparse-10000", "dense-400", "extreme-bottleneck-250", "extreme-bottleneck-500"):
        print(f"measuring {name} in a fresh subprocess", file=sys.stderr, flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), "--capacity-case", name]
        try:
            child = subprocess.run(command, capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired:
            # subprocess.run kills and waits for the child. This is a harness
            # observation, not a completed production mathematical result.
            cases.append({"id": name, "status": "harness_timeout", "seconds": 45,
                          "peak_rss_bytes": None, "mathematical_result": None})
            continue
        (output_dir / f"{name}.stderr.log").write_text(child.stderr, encoding="utf-8")
        if child.returncode:
            cases.append({"id": name, "status": "failed", "returncode": child.returncode})
        else:
            cases.append(json.loads(child.stdout))
    summary = {"classification": "representative capacity observations, not universal guarantees",
               "profile": "capacity", "cases": cases,
               "status": ("failed" if any(x["status"] == "failed" for x in cases)
                          else "completed_with_timeout" if any(x["status"] == "harness_timeout" for x in cases)
                          else "completed"),
               "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    receipt.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert summary["status"] != "failed", "capacity check failed; inspect child stderr"
    return summary


def main():
    if not __debug__:
        raise RuntimeError("qualification requires assertions; do not use Python -O")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "full", "capacity"), default="core")
    parser.add_argument("--output-dir", help="fresh directory for JSONL cases and receipt")
    parser.add_argument("--capacity-case", choices=("sparse-10000", "dense-400", "extreme-bottleneck-250", "extreme-bottleneck-500"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.capacity_case:
        result = capacity_worker(args.capacity_case)
    elif not args.output_dir:
        parser.error("--output-dir is required")
    elif args.profile == "capacity":
        result = run_capacities(args.output_dir)
    else:
        result = run(args.output_dir, args.profile)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
