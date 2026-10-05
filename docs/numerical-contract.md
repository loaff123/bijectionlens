# Numerical contract

## Inputs and scope

`compare(actual, expected, *, atol, limits=None)` and
`bottleneck(actual, expected, *, limits=None)` accept builtin lists or tuples.
Each occurrence is identified by its zero-based position. Accepted values are
finite builtin floats, finite builtin complex values, and builtin integers whose
conversion to binary64 is finite and exact. For example, `2**53` is accepted and
`2**53 + 1` is rejected. Larger exactly representable powers of two may be
accepted; this is a representability rule, not a `2**53` magnitude cutoff.

Booleans, NumPy scalar objects, Decimal, Fraction, subclasses/custom numeric
objects, generators, NaN and infinity are not accepted API values. Use an array's
`.tolist()` for ordinary NumPy float64/complex128 values. This conversion does not
make a higher-precision source exact: the comparison contract begins with the
accepted stored binary64 values. Invalid bounded input raises `TypeError` or
`ValueError`; documented resource exhaustion is distinct.

`atol` accepts a finite nonnegative builtin float or an exactly binary64-representable
builtin integer. The tolerance is absolute. No relative tolerance, componentwise
complex tolerance, nonfinite policy, arbitrary callback, record schema or solver
accuracy claim is implicit.

## Exact relation

For accepted stored values `a` and `b`, an edge exists if

```
(real(a) - real(b))² + (imag(a) - imag(b))² <= atol²
```

Every subtraction, square and comparison deciding this relation is exact rational
or integer arithmetic. A rounded complex subtraction, square root, or float norm
never decides an edge. Exact boundary equality is included. This avoids numerical
overflow and underflow in the authoritative predicate, including subnormal inputs
and opposite extreme values. Positive and negative zero normalize to positive zero.

The deterministic spatial tree prunes only when an exact bounding-box lower bound
is outside the radius. It must enumerate all legal partners. Nearest-k clipping
and greedy exact-value cancellation would change this relation and are not used.
A maximum matching then finds the greatest feasible number of disjoint occurrence
pairs. For fixed inputs, output is deterministic; input permutations preserve
verdict, cardinality and optimum threshold, but may change the selected pair indices.

## Comparison results and independent verification

`ComparisonResult.status` is `matched`, `mismatch`, `size_mismatch`, or
`resource_limited`. `pairs` is an immutable tuple of `(actual_index, expected_index)`
pairs; its length is the reported matching cardinality. Models deliberately reject
implicit boolean coercion. `actual_size`, `expected_size`, `counts`, `reason`,
`resource`, `version` and `verification_status` expose the stated context.

For a `mismatch`, `hall.left_indices` identifies a left subset S and
`hall.neighbor_indices` is its complete compatible right neighborhood N(S).
`hall.deficiency = |S| - |N(S)| = n - len(pairs) > 0`. A feasible matching plus this
shortage proves maximum cardinality. The witness is not necessarily minimal,
unique, or the most intuitive explanation.

`verify_comparison(actual, expected, *, atol, result, limits=None)` checks every
pair's indices, uniqueness and exact feasibility. For a shortage it independently
recomputes **every neighbor** of S against the complete expected input; trusting a
provided graph would be unsound. Length mismatch has a direct length certificate.
The verifier does not import the production matcher or spatial tree.

`VerificationResult.status` is `valid`, `invalid`, or `resource_limited`. A valid
solver result and a later inconclusive verification can coexist. Solver models
retain `verification_status="not_run"`; a separate verifier result supplies the
actual check status. Do not call evidence independently verified unless that
check returned `valid`. Verification attests the mathematical certificate and the
least usable binary64 tolerance, not the accuracy of execution counters or the
display approximation.

## Exact squared bottleneck

For equal sizes, the minimum possible maximum squared pair distance is `q`.
`BottleneckResult.status="optimal"` supplies its reduced decimal integer strings
`q_numerator` and `q_denominator`, a full matching at distances ≤ q, and a
`strict_hall` shortage for the graph of distances < q. This proves feasibility at
the threshold and impossibility below it. `verify_bottleneck` recomputes the full
strict neighborhood from original inputs without invoking the optimizer.

For empty inputs, q is defined as zero. For every q=0 case, nonnegativity proves
the lower bound and no strict Hall shortage is needed. Size mismatch and resource
exhaustion return their explicit statuses without an optimum.

q has squared coordinate units. `approximate_atol` is a display string approximating
sqrt(q). It is not an authoritative acceptance threshold. The separately labelled
`least_finite_binary64_atol` is a canonical float-hex string t such that t² ≥ q and,
for q>0, its immediate finite predecessor has square < q. For q=0 it is positive
zero and no predecessor test applies. It is null when even the largest finite
binary64 tolerance is insufficient. An irrational optimum radius and an optimum
larger than binary64's finite range are valid diagnostic outcomes.

## Default and hard operation limits

Each `Limits` field must be a builtin nonnegative integer, excluding bool. A call
may lower a limit but cannot raise these first-release maxima. Unknown fields are
rejected. Counts are charged before the next operation or retained item; resource
evidence reports phase, used count, next requested units and limit.

| Field | Maximum | Meaning |
| --- | ---: | --- |
| `max_items` | 20,000 | Occurrences per side, before coordinate conversion |
| `max_input_bytes` | 8,388,608 | Input JSON bytes |
| `max_edges` | 100,000 | Cumulative retained edges across all threshold graphs |
| `max_tree_visits` | 2,000,000 | Box-node visits, leaf-distance checks and adjacency-sort scalar work |
| `max_tree_build` | 4,000,000 | Tree-building comparisons/work units |
| `max_matching_scans` | 20,000,000 | Initialization, vertex visits, edge inspections, path rewrites and Hall work |
| `max_verify_pairs` | 2,000,000 | Independent verification pair predicates |
| `max_bottleneck_pairs` | 62,500 | Stored bottleneck pair distances |
| `max_filtration_steps` | 250,000 | Bounded threshold-filtration work |
| `max_filtration_checks` | 8,000,000 | Copies, sort comparisons, deduplication, threshold predicates and binary64 checks |
| `max_wall_seconds` | 30 | Supervised CLI worker elapsed-time limit |
| `max_result_bytes` | 33,554,432 | Serialized result/certificate bytes |

Counters are cumulative within a call, including repeated bottleneck graph/search
iterations. A partially constructed graph cannot support a negative numerical
verdict. A resource-limited solver returns no matching, Hall proof, or purported
optimum. Dense inputs may hit a limit well below the item cap.

The library uses portable deterministic work limits. The CLI additionally starts
a subprocess and terminates it when the wall limit expires. These protections are
not a hard operating-system RAM quota, a real-time guarantee, or a uniform capacity
promise for every input distribution. Peak RSS observations are platform-specific.
Verification can be quadratic in the witnessed left subset and the right input;
its separate cap is intentional.

## Bounded evidence and JSON

The CLI reads at most the byte cap plus one sentinel byte before rejecting an
oversized request. Certificate data is bounded before parsing, copying and expensive
arithmetic. Pair/Hall collections are concrete builtin lists or tuples of at most
20,000 entries; every pair has arity two. Indices and counts are builtin integers
excluding bool, at most 64 bits, followed by semantic range checks. Certificates admit only the 12 known bounded budget phases;
each reported count is checked against its phase maximum. Model construction also
has a defensive 64-field collection cap. Canonical float-hex strings are ASCII
and at most 32 characters.

Squared-threshold numerator and denominator each contain at most 2,500 ASCII decimal
digits and at most 8,192 bits, checked before Fraction/GCD construction. The numerator
is nonnegative, denominator positive, and spelling reduced and canonical. These
bounds accommodate squared binary64 distances; they do not offer arbitrary-precision
input support. Oversized evidence is resource-limited; malformed bounded evidence
is invalid. The [JSON schema](schema-v1.md) defines the exact wire format.

Fingerprints, when provided, detect accidental changes. They are not digital
signatures or authenticity guarantees. No input format executes code, downloads
payloads, or sends telemetry.
