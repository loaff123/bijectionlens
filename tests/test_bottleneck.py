"""Exact minimax assignment and both sides of its threshold certificate."""
from fractions import Fraction
import importlib
import itertools
import math
import random
import sys
import unittest


def bottleneck_fn():
    assert importlib.util.find_spec('bijectionlens.bottleneck') is not None, 'bottleneck module has not been implemented'
    return importlib.import_module('bijectionlens.bottleneck').bottleneck


def exact_points(values):
    return [(Fraction(float(complex(x).real)),Fraction(float(complex(x).imag))) for x in values]


def distances(left,right):
    a,b = exact_points(left),exact_points(right)
    return [[(x[0]-y[0])**2+(x[1]-y[1])**2 for y in b] for x in a]


def result_q(result):
    return Fraction(int(result.q_numerator),int(result.q_denominator))


class BottleneckTests(unittest.TestCase):
    def assert_certificate(self, actual, expected, result):
        self.assertEqual(result.status, 'optimal')
        q = result_q(result)
        d = distances(actual,expected)
        self.assertEqual(sorted(i for i,j in result.pairs), list(range(len(actual))))
        self.assertEqual(sorted(j for i,j in result.pairs), list(range(len(expected))))
        self.assertTrue(all(d[i][j] <= q for i,j in result.pairs))
        if q:
            h = result.strict_hall
            self.assertIsNotNone(h)
            neighbors = {j for i in h.left_indices for j in range(len(expected)) if d[i][j] < q}
            self.assertEqual(neighbors,set(h.neighbor_indices))
            self.assertEqual(h.deficiency,len(h.left_indices)-len(neighbors))
            self.assertGreater(h.deficiency,0)
        else:
            self.assertIsNone(result.strict_hall)
        text = result.least_finite_binary64_atol
        if text is None:
            self.assertLess(Fraction(sys.float_info.max)**2,q)
        else:
            t = float.fromhex(text)
            self.assertGreaterEqual(Fraction(t)**2,q)
            if q:
                self.assertLess(Fraction(math.nextafter(t,0))**2,q)
            else:
                self.assertEqual(text,'0x0.0p+0')
        return q

    def test_minimum_total_distance_is_not_minimum_bottleneck(self):
        r = bottleneck_fn()([0,3],[0,-1+2.5j])
        self.assertEqual(self.assert_certificate([0,3],[0,-1+2.5j],r),9)
        self.assertEqual(r.pairs,((0,1),(1,0)))
        self.assertEqual(r.least_finite_binary64_atol,(3.).hex())

    def test_zero_empty_and_duplicate_optima(self):
        fn=bottleneck_fn()
        for left,right in [([],[]),([0],[0]),([0,0,1],[1,0,0]),([-0.0],[0.0])]:
            self.assertEqual(self.assert_certificate(left,right,fn(left,right)),0)

    def test_irrational_threshold_and_positive_subnormal_minimum(self):
        fn=bottleneck_fn()
        r=fn([0],[1+1j])
        self.assertEqual(self.assert_certificate([0],[1+1j],r),2)
        self.assertAlmostEqual(float(r.approximate_atol),math.sqrt(2))
        tiny=complex(5e-324,5e-324)
        self.assert_certificate([0],[tiny],fn([0],[tiny]))
        self.assertEqual(float.fromhex(fn([0],[tiny]).least_finite_binary64_atol),1e-323)

    def test_no_finite_binary64_radius_can_cover_extreme_pair(self):
        a,b=[complex(1e308,1e308)],[complex(-1e308,-1e308)]
        r=bottleneck_fn()(a,b)
        self.assert_certificate(a,b,r)
        self.assertIsNone(r.least_finite_binary64_atol)
        self.assertIsInstance(r.approximate_atol,str)
        self.assertNotIn('Infinity',r.approximate_atol)

    def test_unequal_sizes_and_invalid_input(self):
        fn=bottleneck_fn()
        r=fn([0],[])
        self.assertEqual(r.status,'size_mismatch')
        self.assertIsNone(r.q_numerator)
        self.assertEqual(r.pairs,())
        with self.assertRaises(ValueError):
            fn([float('nan')],[])
        with self.assertRaises(TypeError):
            fn((x for x in [0]),[0])

    def test_small_seeded_cases_against_permutation_oracle(self):
        fn=bottleneck_fn()
        rng=random.Random(97251)
        for _ in range(80):
            n=rng.randrange(1,6)
            a=[complex(rng.randrange(-4,5),rng.randrange(-4,5)) for _ in range(n)]
            b=[complex(rng.randrange(-4,5),rng.randrange(-4,5)) for _ in range(n)]
            d=distances(a,b)
            q=min(max(d[i][j] for i,j in enumerate(p)) for p in itertools.permutations(range(n)))
            r=fn(a,b)
            self.assertEqual(self.assert_certificate(a,b,r),q)

    def test_each_budget_phase_is_inconclusive(self):
        fn=bottleneck_fn()
        from bijectionlens.contract import Limits
        for phase in ('bottleneck_pairs','filtration_steps','filtration_checks','edges','matching_scans'):
            with self.subTest(phase=phase):
                r=fn([0,3],[0,-1+2.5j],limits=Limits(**{'max_'+phase:0}))
                self.assertEqual(r.status,'resource_limited')
                self.assertEqual(r.resource.phase,phase)
                self.assertIsNone(r.q_numerator)
                self.assertIsNone(r.q_denominator)
                self.assertIsNone(r.strict_hall)
                self.assertEqual(r.pairs,())

    def test_budget_counters_accumulate_across_filtration_passes(self):
        fn=bottleneck_fn()
        from bijectionlens.contract import Limits
        args=([0,3],[0,-1+2.5j])
        expected=fn(*args)
        counts=dict(expected.counts)
        self.assertEqual(counts['bottleneck_pairs'],4)
        self.assertGreater(counts['filtration_checks'],4)
        for phase in ('bottleneck_pairs','filtration_steps','filtration_checks','edges','matching_scans'):
            n=counts[phase]
            self.assertEqual(fn(*args,limits=Limits(**{'max_'+phase:n})),expected)
            r=fn(*args,limits=Limits(**{'max_'+phase:n-1}))
            self.assertEqual(r.status,'resource_limited')
            self.assertEqual(r.resource.phase,phase)

    def test_binary64_minimality_across_exponents(self):
        fn=bottleneck_fn()
        for x in (5e-324,math.ldexp(1.,-500),.5,1.,math.nextafter(1.,math.inf),1e100,sys.float_info.max):
            r=fn([0],[x])
            self.assert_certificate([0],[x],r)
            self.assertEqual(r.least_finite_binary64_atol,x.hex())

    def test_display_is_independent_of_ambient_decimal_context(self):
        from decimal import localcontext, ROUND_FLOOR
        fn=bottleneck_fn()
        expected=fn([0],[complex(1e100,1e100)])
        with localcontext() as context:
            context.prec=3
            context.Emax=2
            context.Emin=-2
            context.rounding=ROUND_FLOOR
            observed=fn([0],[complex(1e100,1e100)])
        self.assertEqual(observed,expected)

    def test_custom_metaclass_cannot_run_during_sequence_rejection(self):
        fn=bottleneck_fn()
        calls=[]
        class HostileMeta(type):
            def __eq__(cls, other):
                calls.append('called')
                raise RuntimeError('schema validation invoked untrusted equality')
        class Hostile(metaclass=HostileMeta):
            pass
        with self.assertRaises(TypeError):
            fn(Hostile(),[])
        self.assertEqual(calls,[])

    def test_display_is_independent_of_mutable_decimal_default_context(self):
        from decimal import DefaultContext, Inexact, ROUND_FLOOR
        fn=bottleneck_fn()
        inputs=[([0],[1+1j]),([0],[complex(1e100,1e100)])]
        expected=[fn(a,b) for a,b in inputs]
        saved=DefaultContext.copy()
        try:
            DefaultContext.traps[Inexact]=True
            DefaultContext.rounding=ROUND_FLOOR
            DefaultContext.Emin=-2
            DefaultContext.Emax=2
            DefaultContext.capitals=0
            DefaultContext.clamp=1
            observed=[fn(a,b) for a,b in inputs]
        finally:
            for name in ('prec','rounding','Emin','Emax','capitals','clamp','flags','traps'):
                setattr(DefaultContext,name,getattr(saved,name))
        self.assertEqual(observed,expected)
