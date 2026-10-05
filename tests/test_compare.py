"""Comparison composition regressions and explicit inconclusive outcomes."""
import dataclasses
import importlib
import itertools
import json
import unittest


def compare_fn():
    assert importlib.util.find_spec('bijectionlens.compare') is not None, 'compare module has not been implemented'
    return importlib.import_module('bijectionlens.compare').compare


class ComparisonTests(unittest.TestCase):
    def test_exact_common_value_must_remain_reassignable(self):
        result = compare_fn()([0,.9], [0,-.9], atol=1)
        self.assertEqual(result.status, 'matched')
        self.assertEqual(result.pairs, ((0,1),(1,0)))

    def test_overlapping_tolerance_requires_global_matching(self):
        result = compare_fn()([.75,0], [0,1.5], atol=.8)
        self.assertEqual(result.status, 'matched')
        self.assertEqual(result.pairs, ((0,1),(1,0)))

    def test_duplicate_shortage_has_maximum_pairing_and_hall_witness(self):
        result = compare_fn()([0,0,3], [0,3,3], atol=.1)
        self.assertEqual(result.status, 'mismatch')
        self.assertEqual(len(result.pairs), 2)
        self.assertEqual(result.hall.left_indices, (0,1))
        self.assertEqual(result.hall.neighbor_indices, (0,))
        self.assertEqual(result.hall.deficiency, 1)
        self.assertEqual(result.verification_status, 'not_run')

    def test_empty_and_unequal_size(self):
        fn = compare_fn()
        self.assertEqual(fn([], [], atol=0).status, 'matched')
        result = fn([0], [], atol=0)
        self.assertEqual(result.status, 'size_mismatch')
        self.assertEqual((result.actual_size,result.expected_size), (1,0))
        self.assertEqual(result.pairs, ())
        self.assertIsNone(result.hall)

    def test_all_36_permutation_pairs_preserve_verdict(self):
        fn = compare_fn()
        for left in itertools.permutations([0,.9,3]):
            for right in itertools.permutations([0,-.9,3]):
                self.assertEqual(fn(list(left),list(right),atol=1).status,'matched')

    def test_repeated_outputs_are_byte_stable(self):
        fn = compare_fn()
        dumps = [json.dumps(dataclasses.asdict(fn([0,0,3],[0,3,3],atol=.1)), sort_keys=True)
                 for _ in range(6)]
        self.assertEqual(len(set(dumps)),1)

    def test_exhaustion_never_reports_partial_verdict(self):
        fn = compare_fn()
        from bijectionlens.contract import Limits
        for phase in ('tree_build','tree_visits','edges','matching_scans'):
            with self.subTest(phase=phase):
                result = fn([0,0,3],[0,3,3],atol=.1,limits=Limits(**{'max_'+phase:0}))
                self.assertEqual(result.status,'resource_limited')
                self.assertEqual(result.pairs,())
                self.assertIsNone(result.hall)
                self.assertEqual(result.resource.phase,phase)
                self.assertTrue(result.reason)

    def test_invalid_coordinates_are_not_hidden_by_size_mismatch(self):
        fn = compare_fn()
        for actual,expected,atol in [([float('nan')],[],0),([],[],True),([True],[0],0)]:
            with self.assertRaises((TypeError,ValueError)):
                fn(actual,expected,atol=atol)

    def test_custom_metaclass_cannot_run_during_sequence_rejection(self):
        fn=compare_fn()
        calls=[]
        class HostileMeta(type):
            def __eq__(cls, other):
                calls.append('called')
                raise RuntimeError('schema validation invoked untrusted equality')
        class Hostile(metaclass=HostileMeta):
            pass
        with self.assertRaises(TypeError):
            fn(Hostile(),[],atol=0)
        self.assertEqual(calls,[])
