"""Proof replay for bottleneck certificates, including hostile raw inputs."""
from importlib import import_module
from fractions import Fraction
import math
import sys
import unittest
from unittest.mock import patch


def verifier():
    try:
        module = import_module('bijectionlens.verify')
    except ModuleNotFoundError:
        raise AssertionError('Independent bottleneck verifier is not implemented')
    assert hasattr(module, 'verify_bottleneck'), 'Independent bottleneck verifier is not implemented'
    return module.verify_bottleneck


def certificate(n=1, numerator='0', denominator='1', **changes):
    cert = dict(status='optimal', actual_size=n, expected_size=n,
                q_numerator=numerator, q_denominator=denominator,
                pairs=[[i, i] for i in range(n)], strict_hall=None,
                approximate_atol='0.0', least_finite_binary64_atol='0x0.0p+0',
                counts=[], reason=None, resource=None, version=1,
                verification_status='not_run')
    cert.update(changes)
    return cert


def hall(left=(0,), neighbors=(), deficiency=1):
    return dict(left_indices=list(left), neighbor_indices=list(neighbors), deficiency=deficiency)


def check(actual, expected, cert, limits=None):
    verify = verifier()
    from bijectionlens.contract import Limits
    limits = Limits(**limits) if type(limits) is dict else limits
    return verify(actual, expected, result=cert, limits=limits)


class BottleneckVerificationTests(unittest.TestCase):
    def test_accepts_zero_empty_duplicates_and_models(self):
        for values in ([], [0], [0, 0], [1j, -0.0]):
            self.assertEqual(check(values, values, certificate(len(values))).status, 'valid')
        from bijectionlens.models import BottleneckResult
        model = BottleneckResult('optimal', 1, 1, q_numerator='0', q_denominator='1',
                                 pairs=((0, 0),), least_finite_binary64_atol='0x0.0p+0')
        self.assertEqual(check([0], [0], model).status, 'valid')

    def test_accepts_q9_exact_optimum_with_strict_hall(self):
        cert = certificate(2, '9', pairs=[[0, 1], [1, 0]],
                           strict_hall=hall((1,)), least_finite_binary64_atol=(3.).hex())
        self.assertEqual(check([0, 3], [0, -1+2.5j], cert).status, 'valid')

    def test_accepts_irrational_threshold_with_exact_binary64_ceiling(self):
        cert = certificate(numerator='2', strict_hall=hall(),
                           least_finite_binary64_atol=math.sqrt(2).hex())
        self.assertEqual(check([0], [1+1j], cert).status, 'valid')

    def test_rejects_feasible_but_nonoptimal_threshold(self):
        cert = certificate(numerator='4', strict_hall=hall(), least_finite_binary64_atol=(2.).hex())
        self.assertEqual(check([0], [1], cert).status, 'invalid')

    def test_rejects_missing_strict_neighbor(self):
        # Matching at 1 exists; the claimed strict Hall set actually reaches both right points.
        cert = certificate(2, '1', strict_hall=hall((0, 1), (0,)),
                           least_finite_binary64_atol=(1.).hex())
        self.assertEqual(check([0, 0], [0, 0], cert).status, 'invalid')

    def test_positive_q_requires_hall_and_zero_q_forbids_negative_lower_bound_claim(self):
        self.assertEqual(check([0], [1], certificate(numerator='1', least_finite_binary64_atol=(1.).hex())).status, 'invalid')
        self.assertEqual(check([0], [0], certificate(strict_hall=hall())).status, 'invalid')

    def test_strict_hall_need_not_have_maximum_deficiency(self):
        cert = certificate(2, '1', strict_hall=hall(), least_finite_binary64_atol=(1.).hex())
        self.assertEqual(check([0, 0], [1, 1], cert).status, 'valid')

    def test_threshold_must_make_all_supplied_pairs_feasible(self):
        cert = certificate(numerator='1', strict_hall=hall(), least_finite_binary64_atol=(1.).hex())
        self.assertEqual(check([0], [2], cert).status, 'invalid')

    def test_binary64_answer_must_be_minimal_and_not_missing(self):
        for value in (math.nextafter(1., 0.).hex(), math.nextafter(1., 2.).hex(), None,
                      '-0x0.0p+0', '1.0', '0X1.0000000000000P+0', float(1), 'inf'):
            with self.subTest(value=value):
                cert = certificate(numerator='1', strict_hall=hall(), least_finite_binary64_atol=value)
                self.assertEqual(check([0], [1], cert).status, 'invalid')

    def test_zero_requires_positive_zero_not_negative_or_missing(self):
        for value in ('-0x0.0p+0', None, (5e-324).hex()):
            with self.subTest(value=value):
                self.assertEqual(check([0], [0], certificate(least_finite_binary64_atol=value)).status, 'invalid')

    def test_no_finite_tolerance_for_opposite_maximum_values(self):
        m = sys.float_info.max
        q = (2 * Fraction.from_float(m)) ** 2
        cert = certificate(numerator=str(q.numerator), denominator=str(q.denominator),
                           strict_hall=hall(), least_finite_binary64_atol=None)
        self.assertEqual(check([-m], [m], cert).status, 'valid')
        self.assertEqual(check([-m], [m], dict(cert, least_finite_binary64_atol=m.hex())).status, 'invalid')

    def test_canonical_rational_malformed_bounded_is_invalid(self):
        for numerator, denominator in [('00', '1'), ('+1', '1'), ('-1', '1'), ('1', '0'),
                                       ('0', '2'), ('2', '2'), ('1', '-2'), ('1', '01'),
                                       ('١', '1'), ('1_0', '1'), ('1 ', '1'), (1, '1'),
                                       ('', '1'), ('1', '')]:
            with self.subTest(numerator=numerator, denominator=denominator):
                self.assertEqual(check([0], [0], certificate(numerator=numerator, denominator=denominator)).status, 'invalid')

    def test_rational_character_bounds_precede_fraction_construction(self):
        verify = verifier()
        module = import_module('bijectionlens.verify')
        for numerator, denominator in [('1' * 2501, '1'), ('1', '1' * 2501),
                                       (str(1 << 8192), '1'), ('1', str(1 << 8192))]:
            with self.subTest(lengths=(len(numerator), len(denominator))):
                with patch.object(module, 'Fraction', side_effect=AssertionError('Fraction before bounds')):
                    result = verify([0], [0], result=certificate(numerator=numerator, denominator=denominator))
                self.assertEqual(result.status, 'resource_limited')

    def test_malformed_threshold_type_cannot_run_callback(self):
        class HostileString(str):
            def __len__(self):
                raise AssertionError('Subclass callback')
        for name, value in [('q_numerator', HostileString('0')), ('q_denominator', HostileString('1')),
                            ('least_finite_binary64_atol', HostileString('0x0.0p+0')),
                            ('approximate_atol', HostileString('0.0'))]:
            with self.subTest(name=name):
                self.assertEqual(check([0], [0], certificate(**{name: value})).status, 'invalid')

    def test_size_mismatch_is_only_valid_for_unequal_original_sizes(self):
        cert = certificate(0, status='size_mismatch', expected_size=1, q_numerator=None,
                           q_denominator=None, approximate_atol=None, least_finite_binary64_atol=None)
        self.assertEqual(check([], [0], cert).status, 'valid')
        self.assertEqual(check([], [], cert).status, 'invalid')
        self.assertEqual(check([], [float('nan')], cert).status, 'invalid')

    def test_limited_candidate_does_not_become_valid(self):
        cert = certificate(status='resource_limited', pairs=[], approximate_atol=None, q_numerator=None, q_denominator=None,
                           least_finite_binary64_atol=None)
        self.assertEqual(check([0], [0], cert).status, 'resource_limited')

    def test_budget_is_cumulative_across_matching_and_strict_neighborhood(self):
        cert = certificate(numerator='1', strict_hall=hall(), least_finite_binary64_atol=(1.).hex())
        self.assertEqual(check([0], [1], cert, {'max_verify_pairs': 1}).status, 'resource_limited')
        self.assertEqual(check([0], [1], cert, {'max_verify_pairs': 2}).status, 'valid')

class BottleneckPrevalidationTests(unittest.TestCase):
    def test_second_original_length_checked_before_first_coordinate(self):
        self.assertEqual(check([object()], [0] * 20001, certificate()).status, 'resource_limited')

class UninitializedBottleneckModelTests(unittest.TestCase):
    def test_missing_builtin_model_slots_are_invalid(self):
        from bijectionlens.models import BottleneckResult
        self.assertEqual(check([], [], object.__new__(BottleneckResult)).status, 'invalid')

class RestrictedIntegerConversionTests(unittest.TestCase):
    def test_smallest_subnormal_and_extreme_optima_survive_supported_640_digit_limit(self):
        from bijectionlens import bottleneck
        settings = sys.get_int_max_str_digits()
        cases = [([0], [5e-324]), ([-sys.float_info.max], [5e-324+5e-324j])]
        # These pre-existing certificates must stay replayable after a caller
        # selects CPython's minimum supported finite conversion limit.
        original = [(a, b, bottleneck(a, b)) for a, b in cases]
        try:
            sys.set_int_max_str_digits(640)
            for actual, expected, certificate_before_setting in original:
                with self.subTest(actual=actual, expected=expected):
                    self.assertEqual(check(actual, expected, certificate_before_setting).status, 'valid')
                    generated = bottleneck(actual, expected)
                    self.assertEqual(generated.status, 'optimal')
                    self.assertEqual(check(actual, expected, generated).status, 'valid')
                    self.assertEqual(generated.q_numerator, certificate_before_setting.q_numerator)
                    self.assertEqual(generated.q_denominator, certificate_before_setting.q_denominator)
                    self.assertEqual(sys.get_int_max_str_digits(), 640)
        finally:
            sys.set_int_max_str_digits(settings)

class RestrictedIntegerGenerationTests(unittest.TestCase):
    def test_solver_generation_works_under_640_digit_limit(self):
        from bijectionlens import bottleneck
        old = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(640)
            result = bottleneck([0], [5e-324])
            self.assertEqual(result.status, 'optimal')
            self.assertEqual(check([0], [5e-324], result).status, 'valid')
        finally:
            sys.set_int_max_str_digits(old)
