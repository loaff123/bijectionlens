"""Independent certificate checks; no graph solver is trusted by these tests."""
from importlib import import_module
import unittest
from functools import wraps

def parameterize(names, values):

    def decorate(test):

        @wraps(test)
        def run(self):
            for value in values:
                arguments = value if ',' in names else (value,)
                with self.subTest(arguments=arguments):
                    test(self, *arguments)
        return run
    return decorate

def verifier():
    try:
        return import_module('bijectionlens.verify').verify_comparison
    except ModuleNotFoundError:
        raise AssertionError('Independent comparison verifier is not implemented')

def positive(n=1, **changes):
    cert = dict(status='matched', actual_size=n, expected_size=n, pairs=[[i, i] for i in range(n)], hall=None, counts=[], reason=None, resource=None, version=1, verification_status='not_run')
    cert.update(changes)
    return cert

def negative(**changes):
    cert = positive(3, status='mismatch', pairs=[[0, 0], [2, 1]], hall=dict(left_indices=[0, 1], neighbor_indices=[0], deficiency=1))
    cert.update(changes)
    return cert

def check(actual, expected, result, atol=0, limits=None):
    verify = verifier()
    from bijectionlens.contract import Limits
    limits = Limits(**limits) if type(limits) is dict else limits
    return verify(actual, expected, atol=atol, result=result, limits=limits)

class Hostile:

    def __getattribute__(self, name):
        raise AssertionError('User-defined attribute callback executed')

    def __iter__(self):
        raise AssertionError('User-defined iteration executed')

    def __int__(self):
        raise AssertionError('User-defined integer conversion executed')

    def __eq__(self, other):
        raise AssertionError('User-defined equality executed')

class HostileList(list):

    def __len__(self):
        raise AssertionError('Subclass length callback executed')

    def __iter__(self):
        raise AssertionError('Subclass iteration callback executed')

class HostileDict(dict):

    def keys(self):
        raise AssertionError('Subclass keys callback executed')

    def __getitem__(self, name):
        raise AssertionError('Subclass field callback executed')

class ComparisonVerificationTests(unittest.TestCase):

    def test_accepts_positive_empty_and_duplicate_bijections(self):
        for actual, expected, cert in [([], [], positive(0)), ([0], [0], positive()), ([0, 0], [0, 0], positive(2))]:
            assert check(actual, expected, cert).status == 'valid'

    def test_accepts_real_hall_shortage_without_isolated_occurrences(self):
        result = check([0, 0, 3], [0, 3, 3], negative(), atol=0.1)
        assert result.status == 'valid'
        assert dict(result.counts)['verify_pairs'] == 8

    def test_omitted_neighbor_is_rejected_from_original_inputs(self):
        assert check([0, 0, 3], [0, 0, 3], negative(), atol=0.1).status == 'invalid'

    @parameterize('patch', [{'pairs': [[0, 0], [0, 1]]}, {'pairs': [[0, 0], [1, 0]]}, {'pairs': [[0, 0], [2, 1]]}, {'pairs': [[0, 0]]}, {'actual_size': 3}, {'expected_size': 3}, {'status': 'unrecognized'}, {'version': 2}, {'unknown': 1}, {'hall': {'left_indices': [], 'neighbor_indices': [], 'deficiency': 0}}])
    def test_rejects_corrupt_positive_certificates(self, patch):
        assert check([0, 1], [0, 1], positive(2, **patch)).status == 'invalid'

    def test_rejects_illegal_distance_and_wrong_original_inputs(self):
        assert check([0], [1], positive()).status == 'invalid'
        assert check([0], [0], positive(), atol=-1).status == 'invalid'
        assert check([float('nan')], [0], positive()).status == 'invalid'

    @parameterize('hall', [dict(left_indices=[0, 1], neighbor_indices=[], deficiency=2), dict(left_indices=[0, 1], neighbor_indices=[0, 1], deficiency=0), dict(left_indices=[0, 1], neighbor_indices=[0], deficiency=2), dict(left_indices=[0, 0], neighbor_indices=[0], deficiency=1), dict(left_indices=[0, 1], neighbor_indices=[0, 0], deficiency=1), dict(left_indices=[0, 4], neighbor_indices=[0], deficiency=1), dict(left_indices=[0, 1], neighbor_indices=[5], deficiency=1), dict(left_indices=[], neighbor_indices=[], deficiency=0), None])
    def test_rejects_wrong_hall_shape_or_shortage(self, hall):
        assert check([0, 0, 3], [0, 3, 3], negative(hall=hall), atol=0.1).status == 'invalid'

    def test_extra_hall_neighbor_rejected_even_if_deficiency_claim_matches(self):
        cert = positive(4, status='mismatch', pairs=[[0, 0], [3, 1]], hall=dict(left_indices=[0, 1, 2], neighbor_indices=[0, 2], deficiency=1))
        assert check([0, 0, 0, 3], [0, 3, 9, 9], cert, atol=0.1).status == 'invalid'

    def test_size_mismatch_certificate_checks_original_sizes_and_all_input_values(self):
        cert = positive(0, status='size_mismatch', expected_size=1)
        assert check([], [0], cert).status == 'valid'
        assert check([], [float('inf')], cert).status == 'invalid'
        assert check([], [], cert).status == 'invalid'
        assert check([], [0], dict(cert, pairs=[[0, 0]])).status == 'invalid'

    def test_resource_limited_candidate_never_acquires_numerical_validity(self):
        assert check([0], [0], positive(status='resource_limited', pairs=[])).status == 'resource_limited'
        assert check([0], [0], positive(status='invalid')).status == 'invalid'

    def test_verifier_budget_charges_before_each_exact_pair_check(self):
        limited = check([0, 0, 3], [0, 3, 3], negative(), atol=0.1, limits={'max_verify_pairs': 7})
        assert limited.status == 'resource_limited'
        assert dict(limited.counts)['verify_pairs'] == 7
        assert check([0, 0, 3], [0, 3, 3], negative(), atol=0.1, limits={'max_verify_pairs': 8}).status == 'valid'
        assert check([0], [0], positive(), limits={'max_verify_pairs': 0}).status == 'resource_limited'
        assert check([], [], positive(0), limits={'max_verify_pairs': 0}).status == 'valid'

    @parameterize('cert', [Hostile(), HostileDict(), iter([]), [], None])
    def test_rejects_non_builtin_certificate_without_callbacks(self, cert):
        assert check([], [], cert).status == 'invalid'

    @parameterize('field,value', [('pairs', Hostile()), ('pairs', HostileList()), ('pairs', iter([])), ('pairs', [[Hostile(), 0]]), ('pairs', [[True, 0]]), ('pairs', [[0]]), ('pairs', [HostileList([0, 0])]), ('counts', Hostile()), ('counts', [['verify_pairs', Hostile()]]), ('counts', [['verify_pairs', True]]), ('counts', [['verify_pairs', -1]]), ('status', Hostile()), ('reason', Hostile()), ('actual_size', Hostile()), ('actual_size', True), ('version', True), ('verification_status', Hostile()), ('resource', Hostile())])
    def test_rejects_malformed_bounded_certificate_fields_before_callbacks(self, field, value):
        assert check([0], [0], positive(**{field: value})).status == 'invalid'

    @parameterize('field,value', [('pairs', [[0, 0]] * 20001), ('pairs', [[2 ** 64, 0]]), ('counts', [['verify_pairs', 2 ** 64]]), ('actual_size', 2 ** 64), ('hall', dict(left_indices=[0] * 20001, neighbor_indices=[], deficiency=1)), ('hall', dict(left_indices=[], neighbor_indices=[0] * 20001, deficiency=1)), ('hall', dict(left_indices=[2 ** 64], neighbor_indices=[], deficiency=1)), ('hall', dict(left_indices=[0], neighbor_indices=[], deficiency=2 ** 64))])
    def test_oversized_certificates_are_resource_limited(self, field, value):
        assert check([0], [0], positive(**{field: value})).status == 'resource_limited'

    def test_rejects_custom_original_input_without_running_it(self):
        assert check(HostileList([0]), [0], positive()).status == 'invalid'
        assert check([Hostile()], [0], positive()).status == 'invalid'

    def test_models_are_accepted_only_as_exact_builtin_types(self):
        verifier()
        from bijectionlens.models import ComparisonResult, HallEvidence
        cert = ComparisonResult('matched', 1, 1, pairs=((0, 0),))
        assert check([0], [0], cert).status == 'valid'
        cert = ComparisonResult('mismatch', 3, 3, pairs=((0, 0), (2, 1)), hall=HallEvidence((0, 1), (0,), 1))
        assert check([0, 0, 3], [0, 3, 3], cert).status == 'valid'

        class Derived(ComparisonResult):

            def __getattribute__(self, name):
                raise AssertionError('Result subclass callback executed')
        assert check([0], [0], object.__new__(Derived)).status == 'invalid'

    def test_independence_is_enforced_in_source(self):
        verifier()
        import ast
        module = import_module('bijectionlens.verify')
        with open(module.__file__, encoding='utf-8') as source:
            tree = ast.parse(source.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {'matching', 'spatial', 'bottleneck', 'compare'}

class AdversarialPrevalidationTests(unittest.TestCase):
    def test_pair_arity_three_is_malformed_not_resource_exhaustion(self):
        self.assertEqual(check([0], [0], positive(pairs=[[0, 0, 0]])).status, 'invalid')

    def test_count_arity_three_is_malformed_not_resource_exhaustion(self):
        self.assertEqual(check([0], [0], positive(counts=[['verify_pairs', 1, 2]])).status, 'invalid')

    def test_hostile_metaclass_does_not_run_during_container_type_check(self):
        class HostileMeta(type):
            def __eq__(cls, other):
                raise AssertionError('Custom metaclass equality callback')
        class Arbitrary(metaclass=HostileMeta):
            pass
        self.assertEqual(check([0], [0], positive(pairs=Arbitrary())).status, 'invalid')
        self.assertEqual(check(Arbitrary(), [0], positive()).status, 'invalid')

    def test_second_original_length_checked_before_first_coordinate(self):
        self.assertEqual(check([Hostile()], [0] * 20001, positive()).status, 'resource_limited')

    def test_all_indices_checked_before_distance_arithmetic(self):
        from unittest.mock import patch
        module = import_module('bijectionlens.verify')
        certificates = [positive(2, pairs=[[0, 0], [2, 1]]),
                        positive(2, pairs=[[0, 0], [1, 5]]),
                        positive(2, pairs=[[0, 0], [0, 1]]),
                        negative(hall=dict(left_indices=[0, 4], neighbor_indices=[0], deficiency=1))]
        with patch.object(module, 'squared_distance', side_effect=AssertionError('Arithmetic before indices')):
            for cert in certificates:
                n = cert['actual_size']
                self.assertEqual(check([0] * n, [0] * n, cert).status, 'invalid')

    def test_dictionary_keys_and_field_count_checked_before_any_lookup(self):
        class HostileKey:
            def __hash__(self):
                return hash('status')
            def __eq__(self, other):
                raise AssertionError('Custom key equality callback')
        self.assertEqual(check([], [], {HostileKey(): 0}).status, 'invalid')
        self.assertEqual(check([], [], {str(i): Hostile() for i in range(65)}).status, 'resource_limited')

    def test_counter_keys_and_resource_evidence_are_bounded(self):
        for counts, status in [({'verify_pairs': 1}, 'valid'), ({'unknown': 0}, 'invalid'),
                               ([['verify_pairs', 0]] * 13, 'resource_limited'),
                               ([['verify_pairs', 0], ['verify_pairs', 1]], 'invalid')]:
            with self.subTest(counts=counts):
                self.assertEqual(check([0], [0], positive(counts=counts)).status, status)
        for resource, status in [(dict(phase='verify_pairs', used=0, requested=1, limit=0), 'valid'),
                                  (dict(phase='verify_pairs', used=2**64, requested=1, limit=0), 'resource_limited'),
                                  (dict(phase='verify_pairs', used=True, requested=1, limit=0), 'invalid')]:
            with self.subTest(resource=resource):
                self.assertEqual(check([0], [0], positive(resource=resource)).status, status)

class PublicTypeGuardTests(unittest.TestCase):
    def test_contract_and_model_guards_never_call_metaclass_equality(self):
        from bijectionlens.contract import normalize_points
        from bijectionlens.models import ComparisonResult, HallEvidence
        class HostileMeta(type):
            def __eq__(cls, other):
                raise AssertionError('Metaclass equality called by public API')
        class Arbitrary(metaclass=HostileMeta):
            pass
        cases = [lambda: normalize_points(Arbitrary()),
                 lambda: ComparisonResult('matched', 1, 1, pairs=Arbitrary()),
                 lambda: ComparisonResult('matched', 1, 1, pairs=[Arbitrary()]),
                 lambda: ComparisonResult('matched', 1, 1, counts=[Arbitrary()]),
                 lambda: HallEvidence(Arbitrary(), (), 1)]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(TypeError):
                    case()

class CounterSchemaTests(unittest.TestCase):
    def test_reported_counter_cannot_exceed_its_hard_phase_maximum(self):
        self.assertEqual(check([0], [0], positive(counts={'verify_pairs': 2_000_000})).status, 'valid')
        self.assertEqual(check([0], [0], positive(counts={'verify_pairs': 2_000_001})).status, 'invalid')

class BottleneckEnvelopeCalibrationTests(unittest.TestCase):
    def test_pair_storage_hard_maximum_is_calibrated_to_62500(self):
        from bijectionlens.contract import Limits
        self.assertEqual(Limits().max_bottleneck_pairs, 62_500)
        self.assertEqual(Limits(max_bottleneck_pairs=62_500).max_bottleneck_pairs, 62_500)
        with self.assertRaises(ValueError):
            Limits(max_bottleneck_pairs=62_501)
        self.assertEqual(check([0], [0], positive(counts={'bottleneck_pairs': 62_501})).status, 'invalid')

class UninitializedModelTests(unittest.TestCase):
    def test_missing_builtin_model_slots_are_invalid_without_attribute_leaks(self):
        from bijectionlens.models import ComparisonResult, HallEvidence, ResourceEvidence
        for cert in (object.__new__(ComparisonResult),
                     negative(hall=object.__new__(HallEvidence)),
                     positive(resource=object.__new__(ResourceEvidence))):
            with self.subTest(type=type(cert).__name__):
                self.assertEqual(check([], [], cert).status, 'invalid')

class BoundedDecimalConversionTests(unittest.TestCase):
    def test_bounded_helpers_reject_oversize_before_integer_arithmetic(self):
        import bijectionlens.contract as contract
        self.assertTrue(hasattr(contract, 'parse_certificate_decimal'), 'bounded decimal parser missing')
        self.assertTrue(hasattr(contract, 'format_certificate_decimal'), 'bounded decimal formatter missing')
        with self.assertRaises(contract.ResourceLimit):
            contract.parse_certificate_decimal('1' * 2501)
        with self.assertRaises(contract.ResourceLimit):
            contract.parse_certificate_decimal('9' * 2500)
        with self.assertRaises(contract.ResourceLimit):
            contract.format_certificate_decimal(1 << 8192)
        for value in ('', '00', '+1', '-1', '١', '1_0', True):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                contract.parse_certificate_decimal(value)
        for value in (-1, True, 0.0):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                contract.format_certificate_decimal(value)

    def test_bounded_helpers_roundtrip_at_8192_bits_under_640_digit_limit(self):
        import sys
        import bijectionlens.contract as contract
        self.assertTrue(hasattr(contract, 'parse_certificate_decimal'), 'bounded decimal parser missing')
        self.assertTrue(hasattr(contract, 'format_certificate_decimal'), 'bounded decimal formatter missing')
        old = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(640)
            for value in (0, 1, 999999999, 1000000000, 1 << 2148, (1 << 8192) - 1):
                text = contract.format_certificate_decimal(value)
                self.assertEqual(contract.parse_certificate_decimal(text), value)
                self.assertTrue(text.isascii() and text.isdecimal())
                self.assertLessEqual(len(text), 2500)
                self.assertTrue(text == '0' or not text.startswith('0'))
            self.assertEqual(sys.get_int_max_str_digits(), 640)
        finally:
            sys.set_int_max_str_digits(old)
