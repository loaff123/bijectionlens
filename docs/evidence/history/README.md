# Historical feasibility evidence

These are presentation copies from a **throwaway feasibility experiment**, run
before the production package was implemented. They are not evidence that the
production modules or any public commit passed qualification. The experiment's
code is not shipped as the production implementation.

The final experiment used Python 3.12.14, NumPy 2.3.5 and SciPy 1.17.0. It retained:

- 600 frozen random comparisons: 165 matched, 435 genuine mismatches
- 36 input-permutation pairs, 16 numerical boundaries and five utility controls
- 80 exact squared bottleneck comparisons against all permutations
- All 12 subsequent exploratory NumPy examples: 12 matched, nine sorting successes
  and three sorting false negatives. They were not held out
- A sparse 10,000-point grid case and a dense 400×400 resource-negative control
- An independent review of 66,067 square graphs, 500 rectangular graphs,
  240 extreme-exponent spatial graphs and 160 bottleneck cases

Raw JSONL rows retain positives, negatives, chosen pairs, complete-neighbor witnesses,
hexadecimal inputs and baseline outcomes. The SciPy tolerance-graph baseline was
correct. The comparison examples establish no root-solver defect or true scientific
accuracy. Historical capacity measurements establish only those particular cases.

## Earlier defects are preserved

`independent-before-integer-fix.json` records that the early probe silently aliased
an integer not exactly representable in binary64. `independent-after-integer-fix.json`
retains the intermediate review. `review-red.log` and `budget-red.log` show failing
contract tests for integer rounding and invalid budget handling; `green-final.log`
records the final probe tests. Invalid NaN/negative budgets could disable or bypass
bounds before the fix. These were real defects, not successful qualification results.
The final frozen experiment was rerun after both fixes.

`red-corrected.log` also retains the initial missing-implementation tests. Test
failures are historical process evidence, not outstanding assertions about the
production package. Correcting those probe guards did not supply the complete
production resource envelope, independent verifier, CLI, package installation or
multi-version CI; those require separate fresh tests.

## Provenance and presentation-only sanitization

[provenance.json](provenance.json) lists every copied file's original and public
SHA-256. Private checkout paths and research workspace labels in logs were replaced
with generic placeholders. Numerical data, runtime versions, failures and results
were unchanged. Original records were not edited. Operational plans and private
workspace context are intentionally not redistributed.

The historical frozen protocol SHA-256 was
`d55bcdbfb76b9e5c2751954d9abd663de95202dc71869c74bd987a7b09ff6f14`.
The final reviewed probe source SHA-256 was
`8e175c2a06085474eea1b43cea843276a7ac70796cfc5f006cebad24915134c1`.
These identify earlier experiment inputs and are not hashes of the production code.

Use the root-level qualification script for fresh package evidence, and consult
[the provenance guide](../../evidence-provenance.md) before interpreting results.
