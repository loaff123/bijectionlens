"""Exact predicates against independent integer cross-product arithmetic."""
from fractions import Fraction
import importlib
import math
import random
import struct
import unittest


def optional_module(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name not in {name, 'bijectionlens'}:
            raise
        return None


contract = optional_module('bijectionlens.contract')
geometry = optional_module('bijectionlens.geometry')


def cross_product_within(a, b, tolerance):
    ar, ad = a.real.as_integer_ratio()
    ai, aid = a.imag.as_integer_ratio()
    br, bd = b.real.as_integer_ratio()
    bi, bid = b.imag.as_integer_ratio()
    tr, td = tolerance.as_integer_ratio()
    rn, rd = ar*bd-br*ad, ad*bd
    inn, ind = ai*bid-bi*aid, aid*bid
    return (rn*rn*ind*ind + inn*inn*rd*rd)*td*td <= tr*tr*rd*rd*ind*ind


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(contract, 'normalization is not implemented')
        self.assertIsNotNone(geometry, 'exact geometry is not implemented')

    def test_three_four_five_boundary_and_nextafter(self):
        a, b = contract.normalize_points([0, 3+4j])
        q = geometry.squared_distance(a, b)
        self.assertEqual(q, Fraction(25))
        self.assertLessEqual(q, contract.normalize_atol(5)**2)
        self.assertGreater(q, contract.normalize_atol(math.nextafter(5, 0))**2)

    def test_subnormal_complex_distance_does_not_underflow(self):
        a, b = contract.normalize_points([0, complex(5e-324, 5e-324)])
        self.assertEqual(geometry.squared_distance(a, b), Fraction(2, 2**2148))
        self.assertGreater(geometry.squared_distance(a, b), contract.normalize_atol(5e-324)**2)

    def test_opposite_extreme_points_do_not_overflow(self):
        a, b = contract.normalize_points([complex(1e308, 1e308), complex(-1e308, -1e308)])
        self.assertEqual(geometry.squared_distance(a, b), 8*Fraction.from_float(1e308)**2)
        self.assertGreater(geometry.squared_distance(a, b), Fraction.from_float(1e308)**2)

    def test_exact_box_minimum_inside_faces_and_corners(self):
        bounds = (Fraction(0), Fraction(3), Fraction(-2), Fraction(4))
        points = contract.normalize_points([1+1j, 5+1j, 6+8j])
        self.assertEqual([geometry.box_squared_distance(p, bounds) for p in points], [0, 4, 25])

    def test_seeded_ten_thousand_integer_cross_product_predicates(self):
        randomizer = random.Random(1102026)
        def finite():
            bits = randomizer.getrandbits(64)
            bits &= ~(0x7ff << 52)
            bits |= randomizer.randrange(2047) << 52
            return struct.unpack('>d', struct.pack('>Q', bits))[0]
        for index in range(10000):
            a = complex(finite(), finite())
            b = complex(finite(), finite())
            tolerance = abs(finite())
            left, right = contract.normalize_points([a, b])
            actual = geometry.squared_distance(left, right) <= contract.normalize_atol(tolerance)**2
            expected = cross_product_within(a, b, tolerance)
            self.assertEqual(actual, expected, f'predicate {index}')


if __name__ == '__main__':
    unittest.main()
