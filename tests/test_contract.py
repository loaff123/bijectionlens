"""Numerical input, operation-budget, and immutable-result contracts."""
import dataclasses
from fractions import Fraction
import importlib
import math
import unittest


def optional_module(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name not in {name, 'bijectionlens'}:
            raise
        return None


contract = optional_module('bijectionlens.contract')
models = optional_module('bijectionlens.models')


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(contract, 'exact bounded contract is not implemented')

    def test_points_are_exact_canonical_and_signed_zero_is_normalized(self):
        points = contract.normalize_points([3, 4.5, complex(-0.0, -0.0), 2+3j])
        self.assertEqual((points[1].real, points[1].imag), (Fraction(9, 2), Fraction(0)))
        self.assertEqual(points[0].real_hex, float(3).hex())
        self.assertEqual((points[2].real_hex, points[2].imag_hex), ('0x0.0p+0', '0x0.0p+0'))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            points[0].real = Fraction(99)

    def test_only_exactly_binary64_representable_builtin_integers(self):
        self.assertEqual(contract.normalize_points([2**53])[0].real, Fraction(2**53))
        self.assertEqual(contract.normalize_atol(2**53), Fraction(2**53))
        for value in [2**53+1, -(2**53+1), 10**10000]:
            with self.subTest(value_bits=value.bit_length()):
                with self.assertRaises(ValueError):
                    contract.normalize_points([value])
                with self.assertRaises(ValueError):
                    contract.normalize_atol(value)

    def test_bool_and_custom_numeric_types_are_rejected(self):
        class FloatSubclass(float):
            pass
        class Custom:
            def __float__(self):
                raise AssertionError('custom conversion must never run')
        for value in [True, False, FloatSubclass(1), Fraction(1), Custom(), '1']:
            with self.subTest(type=type(value)):
                with self.assertRaises(TypeError):
                    contract.normalize_points([value])
                with self.assertRaises(TypeError):
                    contract.normalize_atol(value)

    def test_nonfinite_coordinate_rejection(self):
        for value in [math.inf, -math.inf, math.nan, complex(math.inf, 0), complex(0, math.nan)]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    contract.normalize_points([value])

    def test_atol_must_be_nonnegative_finite_real(self):
        for value in [-1, -0.1, math.inf, -math.inf, math.nan]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    contract.normalize_atol(value)
        for value in [1+0j, True]:
            with self.assertRaises(TypeError):
                contract.normalize_atol(value)
        self.assertEqual(contract.normalize_atol(-0.0), Fraction(0))
        self.assertEqual(contract.normalize_atol(5e-324), Fraction(1, 2**1074))

    def test_builtin_bounded_sequence_only(self):
        class ListSubclass(list):
            pass
        for values in [(x for x in []), range(3), ListSubclass([1]), object(), '123']:
            with self.subTest(type=type(values)):
                with self.assertRaises(TypeError):
                    contract.normalize_points(values)
        self.assertEqual(contract.normalize_points(()), ())

    def test_length_limit_checked_before_coordinate_conversion(self):
        class Bad:
            def __float__(self):
                raise AssertionError('must reject length before conversion')
        with self.assertRaises(contract.ResourceLimit) as caught:
            contract.normalize_points([Bad(), Bad()], contract.Limits(max_items=1))
        error = caught.exception
        self.assertEqual((error.phase, error.used, error.requested, error.limit), ('items', 0, 2, 1))

    def test_limits_have_fixed_hard_caps(self):
        expected = dict(max_items=20000, max_input_bytes=8388608, max_edges=100000,
                        max_tree_visits=2000000, max_tree_build=4000000,
                        max_matching_scans=20000000, max_verify_pairs=2000000,
                        max_bottleneck_pairs=62500, max_result_bytes=33554432,
                        max_wall_seconds=30, max_filtration_steps=250000,
                        max_filtration_checks=8000000)
        limits = contract.Limits()
        self.assertEqual(dataclasses.asdict(limits), expected)
        for key, maximum in expected.items():
            self.assertEqual(getattr(contract.Limits(**{key: 0}), key), 0)
            with self.assertRaises(ValueError):
                contract.Limits(**{key: maximum+1})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            limits.max_items = 1

    def test_invalid_and_unknown_limits_rejected(self):
        for value in [True, 1.0, math.nan, -1, '1', None, 2**100]:
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    contract.Limits(max_edges=value)
        with self.assertRaises(TypeError):
            contract.Limits(max_unknown=1)
        with self.assertRaises(TypeError):
            contract.normalize_points([], {})
        with self.assertRaises(TypeError):
            contract.Budget({})

    def test_budget_charges_before_work_and_preserves_exact_boundary(self):
        budget = contract.Budget(contract.Limits(max_edges=2))
        budget.charge('edges', 2)
        before = budget.snapshot()
        with self.assertRaises(contract.ResourceLimit) as caught:
            budget.charge('edges')
        self.assertEqual((caught.exception.phase, caught.exception.used,
                          caught.exception.requested, caught.exception.limit), ('edges', 2, 1, 2))
        self.assertEqual(budget.snapshot(), before)
        self.assertEqual(dict(before)['edges'], 2)
        self.assertIs(type(before), tuple)
        self.assertTrue(all(type(item) is tuple for item in before))
        budget.charge('tree_visits')
        self.assertEqual(dict(before).get('tree_visits', 0), 0)
        self.assertEqual(budget.counts, budget.snapshot())
        with self.assertRaises(AttributeError):
            budget.limits = contract.Limits()

    def test_budget_phase_mapping_and_invalid_units(self):
        limits = contract.Limits(**{field.name: 0 for field in dataclasses.fields(contract.Limits)})
        for field in dataclasses.fields(contract.Limits):
            budget = contract.Budget(limits)
            phase = field.name.removeprefix('max_')
            budget.charge(phase, 0)
            with self.assertRaises(contract.ResourceLimit):
                budget.charge(phase)
        for units in [True, 0.0, -1, '1', None]:
            with self.assertRaises((TypeError, ValueError)):
                contract.Budget().charge('edges', units)
        with self.assertRaises(ValueError):
            contract.Budget().charge('unknown')

    def test_point_constructor_preserves_coordinate_invariants(self):
        with self.assertRaises((TypeError, ValueError)):
            contract.Point(Fraction(1), Fraction(0), '0x0.0p+0', '0x0.0p+0')
        with self.assertRaises((TypeError, ValueError)):
            contract.Point(Fraction(1, 3), Fraction(0), float(1/3).hex(), '0x0.0p+0')


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(models, 'immutable evidence models are not implemented')

    def test_nested_aliases_are_copied_and_frozen(self):
        left = [0, 1]
        neighbors = [0]
        pairs = [[0, 0]]
        counts = {'edges': 2}
        hall = models.HallEvidence(left, neighbors, 1)
        result = models.ComparisonResult('mismatch', 2, 2, pairs, hall, counts)
        left.clear(); neighbors.clear(); pairs[0][0] = 99; counts['edges'] = 99
        self.assertEqual(result.pairs, ((0, 0),))
        self.assertEqual(result.hall.left_indices, (0, 1))
        self.assertEqual(result.hall.neighbor_indices, (0,))
        self.assertEqual(dict(result.counts), {'edges': 2})
        self.assertEqual(result.verification_status, 'not_run')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.status = 'matched'

    def test_results_never_offer_a_truth_value(self):
        results = [models.ComparisonResult('matched', 0, 0),
                   models.ComparisonResult('resource_limited', 0, 0),
                   models.BottleneckResult('optimal', 0, 0, '0', '1'),
                   models.VerificationResult('valid')]
        for result in results:
            with self.subTest(type=type(result)):
                with self.assertRaises(TypeError):
                    bool(result)

    def test_models_reject_mutable_custom_and_bool_integer_fields(self):
        for values in [(x for x in []), {0}, object()]:
            with self.assertRaises(TypeError):
                models.HallEvidence(values, (), 0)
        for value in [True, 1.0, '1', -1, 2**65]:
            with self.assertRaises((TypeError, ValueError)):
                models.ComparisonResult('matched', value, 0)
            with self.assertRaises((TypeError, ValueError)):
                models.HallEvidence([value], [], 1)
        with self.assertRaises(TypeError):
            models.ComparisonResult('matched', 1, 1, [[True, 0]])
        with self.assertRaises(TypeError):
            models.ComparisonResult('matched', 0, 0, counts={'edges': True})

    def test_oversized_evidence_rejected_before_reading_elements(self):
        with self.assertRaises((ValueError, contract.ResourceLimit)):
            models.HallEvidence([object()] * 20001, (), 1)
        with self.assertRaises((ValueError, contract.ResourceLimit)):
            models.ComparisonResult('matched', 1, 1, [object()] * 20001)

    def test_resource_evidence_copies_exception(self):
        error = contract.ResourceLimit('edges', 3, 1, 3)
        resource = models.ResourceEvidence.from_error(error)
        result = models.ComparisonResult('resource_limited', 1, 1, resource=resource)
        self.assertEqual((result.resource.phase, result.resource.used, result.resource.requested,
                          result.resource.limit), ('edges', 3, 1, 3))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            resource.used = 99

    def test_invalid_status_and_verified_claim_rejected(self):
        with self.assertRaises(ValueError):
            models.ComparisonResult('valid', 0, 0)
        with self.assertRaises(ValueError):
            models.ComparisonResult('matched', 0, 0, verification_status='valid')
        with self.assertRaises(ValueError):
            models.BottleneckResult('matched', 0, 0)
        with self.assertRaises(ValueError):
            models.VerificationResult('matched')

    def test_resource_limited_preserves_original_overlong_input_sizes(self):
        comparison = models.ComparisonResult('resource_limited', 20001, 20002)
        bottleneck = models.BottleneckResult('resource_limited', 20001, 20002)
        for result in (comparison, bottleneck):
            self.assertEqual((result.actual_size, result.expected_size), (20001, 20002))
        with self.assertRaises(ValueError):
            models.ComparisonResult('matched', 20001, 20001)
        with self.assertRaises(ValueError):
            models.ComparisonResult('resource_limited', 2**64, 0)

    def test_resource_limited_cannot_carry_a_claimed_solution(self):
        with self.assertRaises(ValueError):
            models.ComparisonResult('resource_limited', 1, 1, pairs=[(0, 0)])
        with self.assertRaises(ValueError):
            models.BottleneckResult('resource_limited', 1, 1, q_numerator='1', q_denominator='1')


if __name__ == '__main__':
    unittest.main()
