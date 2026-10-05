# Motivation and prior art

Source review date: 2026-10-05. Live documentation may change independently of
the tested dependency versions. No third-party source code is redistributed.

## A specific, old numerical-testing request

[NumPy issue 10467](https://github.com/numpy/numpy/issues/10467) requests an
unordered approximate multiset comparison for polynomial roots, preserving
multiplicity. The research review recorded the issue as open, created and last
updated in January 2018. This is direct niche demand, not evidence of current
momentum or broad adoption. The discussion already suggests acceptable-edge
graphs/KD trees and bottleneck assignment. Those ideas are not claimed as new.

[pytest issue 10032](https://github.com/pytest-dev/pytest/issues/10032) is adjacent
unordered-assertion demand. The research review recorded it as open with a June
2024 update. It is not a direct request for exact complex arithmetic.

## Correct strong baselines

[SciPy maximum_bipartite_matching](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.csgraph.maximum_bipartite_matching.html)
already solves maximum-cardinality bipartite matching with Hopcroft–Karp. Given the
correct tolerance graph, it is a correct boolean and cardinality baseline, not a
method this package purports to fix. Its sparse graph is structural: explicitly
stored zeros still represent edges. The qualification runner inserts only legal
edges and uses positive stored entries. SciPy 1.17.0 is the pinned experimental
runtime; live documentation observed during review identified 1.18.0. Reading newer
docs does not establish that a newer runtime was tested.

[GoogleTest's matcher reference](https://google.github.io/googletest/reference/matchers.html)
includes unordered element and unordered pointwise matching with customizable
predicates. Its [matcher implementation](https://github.com/google/googletest/blob/main/googlemock/src/gmock-matchers.cc)
already performs global maximum matching and reports partial pairings. Source review
recorded blob identity `277add6b622ddaba0e432668c2a5566ef6ff0851`. Unordered predicate
matching with useful diagnostics is strong prior art. The inspected interface did
not provide this package's exact binary64 numerical contract, externally replayable
all-neighbor Hall certificate and exact squared-bottleneck verification workflow.
This is a bounded interface comparison, not proof that no equivalent package exists.

## Other approaches and retained controls

- Sorting can work and frequently does. Lexicographic complex ordering can also
  change discontinuously with tiny real-part differences, producing a false negative
  when a tolerance bijection exists. The exploratory NumPy examples retain all nine
  historical sorting successes along with three false negatives
- First-fit removal preserves exact multiplicity under ordinary equality, but
  overlapping approximate predicates may need reassignment. The inspected
  [pytest-unordered source](https://github.com/utapyngo/pytest-unordered/blob/master/pytest_unordered/__init__.py)
  used first-fit equality/removal; source blob identity was
  `881fd6700edfc1ef3c4ddc23bd99457f357fa28b`. That package was not installed or executed
  in the feasibility experiment. Our general overlap fixture is not a new runtime-tested
  upstream bug report
- [pytest.approx](https://docs.pytest.org/en/stable/reference/reference.html#pytest-approx)
  documents ordered sequence comparison. Its tolerance semantics are not silently
  adopted by BijectionLens
- [SciPy linear_sum_assignment](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html)
  correctly minimizes a sum objective. Thresholding that particular assignment can
  miss a feasible bottleneck assignment. This is an objective mismatch, not a defect
  in the assignment solver
- [DeepDiff's numerical documentation](https://zepworks.com/deepdiff/current/numbers.html#math-epsilon)
  describes limitations of `math_epsilon` with `ignore_order`. Its general structural
  diff has a different contract

The five retained utility fixtures include a sorting false negative, a first-fit
false negative, a minimum-sum-then-threshold false negative, a case where all tested
baselines succeed, and a true duplicate shortage without isolated left vertices.
SciPy's correctly constructed tolerance-graph baseline remains successful on every
admitted positive fixture and agrees on genuine shortages.

## What is and is not claimed

The intended contribution is an explicit bounded numerical workflow: exact predicates
on supplied stored binary64 values, global occurrence matching, independently
checkable shortage evidence, certified squared thresholds, and honest inconclusive
resource states. No new matching theorem, new root solver, general scientific
accuracy, superior asymptotic complexity, universal speed advantage, or broad
unmet market is claimed. Source inspection cannot prove the absence of competitors.

The NumPy root examples follow the documented
[polyroots workflow](https://numpy.org/doc/stable/reference/generated/numpy.polynomial.polynomial.polyroots.html)
and [roots API](https://numpy.org/doc/stable/reference/generated/numpy.roots.html).
They demonstrate result comparison, not the correctness or numerical stability of
those solvers.
