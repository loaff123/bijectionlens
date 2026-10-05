# BijectionLens independent numerical review

Review date: 2026-10-05

## Decision and scope

**The numerical-core review passes for the exact source hashes in `REVIEWED_SOURCE_SHA256.txt`, on Python 3.12.14 and 3.13.5. No unresolved critical, important, or minor finding remains in this review's scope.**

Scope: strict stored-binary64 normalization, exact geometry and tree pruning, complete tolerance graphs, maximum matching and Hall evidence, bottleneck minimax thresholds, independent mathematical certificate verification, immutable result representation, and numerical operation limits. The real package initializer and serialization helper were exercised as part of the review.

This is not whole-product release approval. CLI filesystem safety, worker termination, raw JSON byte limits, packaging/install checks, license/distribution audit, and Python 3.11/3.14 qualification are separate gates. This review did not publish software, make a new performance claim, or run a new SciPy experiment.

All final runs recorded source hashes before and after execution. The relevant hashes were stable in every run and agree across both interpreters and the retained source snapshot. Production files and production tests were not edited by this reviewer.

## Independent evidence

The same checks passed on both interpreters. Counts below are per interpreter, not doubled:

| Check | Coverage |
| --- | --- |
| Exhaustive square graphs | All 66,067 graphs for sizes 0 through 4, compared to exhaustive minimum-vertex-cover enumeration |
| Rectangular graphs | 1,500 separately seeded graphs, with cardinality and complete Hall neighborhoods checked |
| Long alternating paths | 20,000 vertices per side; both a full augmenting path and a shortage reaching the entire left side |
| Exact distance | 12,000 predicates and squared distances checked by decoding IEEE754 bits into integers on a 2^-1074 lattice |
| Exact bounding boxes | 2,500 full-exponent boxes, faces and corners checked with integer lattice distances |
| Complete spatial graph | 503 indexed graphs compared edge-for-edge with direct integer-lattice enumeration |
| Integer convenience input | 3,356 signed integer cases, with separate tolerance checks; representability decided by bit length and trailing bits |
| Exact bottleneck | 688 cases; 480,892 complete assignments enumerated, including subnormal and opposite-maximum coordinates |
| Random comparison | 1,000 cases checked against independent graph cardinality; 297 matched and 703 mismatched |
| Synthetic comparison certificates | 12,000 independently classified candidates: 243 valid, 11,757 invalid |
| Synthetic bottleneck certificates | 5,000 independently classified candidates: 90 valid, 4,910 invalid |
| Exhaustive small numerical inputs | 820 bottleneck cases and 2,460 comparisons over all length-0-through-3 real inputs from {-1, 0, 1} |
| Permutations and determinism | All 36 pairs of three-item permutations; 10 repeated byte-equivalent serializations |
| New bounded decimal helpers | 306 boundary/random integers through 8,192 bits, 1,836 conversions under digit caps 640, 0 and 4,300 |

The matching oracle does not implement another augmenting-path algorithm: it enumerates every left portion of a vertex cover and uses König's theorem. Geometry checks do not call the production Fraction predicate: they decode binary64 bits and compare integer squared differences. Bottleneck checks enumerate complete assignments. Synthetic verifier tests determine feasibility and all-neighbor shortages directly from original values. No throwaway feasibility-probe algorithm was used as the review oracle.

The tests also cover immutable nested aliases, explicit rejection of boolean result coercion, malformed/oversized certificate fields before distance or GCD work, omitted real Hall neighbors, feasible but nonoptimal bottleneck thresholds, exact counter boundaries, custom callback rejection, and resource-limited results without numerical proofs.

## Mathematical assessment

- The edge relation uses the exact supplied binary64 coordinates and tolerance. Neither rounded subtraction, a floating-point norm, nor the approximate square root determines an edge
- The tree prunes only by an exact lower bound and retains every legal candidate. Duplicates remain separate occurrences; common exact values are not greedily cancelled
- The iterative matching code returns a feasible maximum matching in the independently tested graph population, including paths beyond Python recursion limits
- Negative comparison certificates recompute the complete neighborhood of S against every original expected occurrence. A feasible matching of size k and deficiency n-k supply matching lower and upper bounds
- Bottleneck feasibility is proved at exact squared threshold q; a full-neighborhood Hall shortage in the strict graph proves that q cannot be lowered. At q=0 the lower bound is nonnegativity
- The least finite binary64 tolerance is checked by exact squaring and its immediate predecessor; null is checked against the largest finite binary64 value
- The verifier does not import or invoke the spatial tree, matcher, comparator, or bottleneck optimizer. Shared normalization/geometry primitives were separately checked by the integer-lattice oracle

Validity covers mathematical evidence and the least binary64 tolerance. It does not attest approximate display accuracy, truth of reported execution counters, provenance, or authenticity. The public numerical-contract documentation now states the display/counter limitation. Ordinary dataclass immutability prevents accidental mutation and alias changes; it is not a security boundary against Python's low-level object mutation mechanisms.

## Resource assessment

Boundary tests reran each used solver phase with its exact required budget and one fewer unit. Exact budgets succeeded; one fewer unit returned `resource_limited`, with used/requested/limit evidence and without a pairing, Hall proof, or claimed optimum. Verification exhaustion stayed inconclusive. Oversized original inputs preserved their real lengths in solver results and were stopped before either coordinate array was materialized.

The reviewed release configuration deliberately lowers `max_bottleneck_pairs` from the pre-build design's 250,000 to **62,500**. A 250-by-250 all-zero case stores exactly 62,500 distances and produces q=0; the 251-by-251 case stops at used=62,500/requested=1 with no mathematical result. This is a boundary fixture, not a guarantee that every 250-item bottleneck problem finishes within other cumulative limits.

Edge, matching and filtration counters are cumulative across threshold searches. The reviewed contract does not promise a hard operating-system memory quota. No broader performance or capacity conclusion follows from these tests.

## Findings resolved and independently retested

### NR-1: Both input lengths must precede normalization (important)

Earlier verifier code normalized the first input before checking the second input's length. With a malformed first occurrence and 20,001 expected values, it returned `invalid` before reaching the required size guard and could allocate a full first coordinate array unnecessarily.

Resolution: both concrete sequence types and both lengths are checked before either normalization. Comparison and bottleneck verifier regressions now return `resource_limited` before first-coordinate inspection.

### NR-2: Approximate display inherited Decimal defaults (important robustness issue)

An intermediate `Context(prec=18)` still inherited mutable `decimal.DefaultContext`. Setting `DefaultContext.traps[Inexact] = True` made `bottleneck([0], [1+1j])` raise `decimal.Inexact` after the exact work succeeded.

Resolution: the display calculation now uses an explicitly configured private context, including rounding, exponent limits, flags and traps. Current-context and DefaultContext changes no longer affect the tested result bytes. This display remains non-authoritative.

### NR-3: Supported Python integer conversion limits broke valid thresholds (important)

With `sys.set_int_max_str_digits(640)`, the legitimate smallest-subnormal problem `bottleneck([0], [5e-324])` raised `ValueError` while formatting its 647-digit denominator. Replaying a previously produced valid certificate under that setting incorrectly returned `invalid`.

Resolution: bounded base-10^9 chunk parsing and formatting honor the 2,500-character/8,192-bit contract without modifying the process-wide setting. Fresh generation and replay now pass for smallest-subnormal and mixed-extreme examples at 640. Random/boundary helper checks also pass. The failing pre-fix evidence is retained as `adversarial-312-before-integer-fix.json` and its log.

### NR-4: Constructor-bypassed exact models leaked AttributeError (minor)

`verify_comparison([], [], atol=0, result=object.__new__(ComparisonResult))` previously leaked `AttributeError` for a missing field. This required local constructor bypass; it was not a CLI false acceptance.

Resolution: missing slots on exact comparison, bottleneck, Hall and resource models now produce `invalid`. This is checked alongside strict callback-free container/type guards.

Previously reported spatial-comparison accounting and hostile-metaclass guard fixes were already present or landed during review; their final behavior was exercised again in the stable-hash runs. No mathematical false acceptance was observed.

## Prior-art and claim boundaries

The reviewed public wording preserves SciPy as a correct maximum-matching baseline given the correct tolerance graph, and GoogleTest as existing global unordered-predicate matching with diagnostics. It does not claim a new matching algorithm, a new Hall theorem, superior asymptotic complexity, solver accuracy, general performance superiority, or broad unmet demand. This review checked those statements against the supplied design and public package wording; it did not repeat live-source research.

## Reproduction and retained evidence

The accompanying review bundle contains:

- `review_core.py`, `review_bottleneck.py`, `review_adversarial.py`, `review_decimal_helpers.py`
- `core-312.json`, `core-313.json`, corresponding bottleneck/adversarial/decimal JSON records, and their command logs
- `REVIEWED_SOURCE_SHA256.txt` and `reviewed-source/` for the exact tested modules
- The preserved failing integer-conversion-limit record

Run each review script with a supported interpreter. `BIJECTIONLENS_SOURCE` may point to the repository root containing `src/bijectionlens`; otherwise the scripts use the original sibling-repository layout. All review oracles use only the standard library. Success requires exit status zero, empty `failures`, and `stable_tested_source: true` in every final JSON record.
