"""Exact rational geometry; rounded floating-point distances never decide edges."""
from fractions import Fraction
from .contract import Point


def squared_distance(a: Point, b: Point) -> Fraction:
    real = a.real - b.real
    imag = a.imag - b.imag
    return real * real + imag * imag


def box_squared_distance(point: Point, bounds: tuple[Fraction, Fraction, Fraction, Fraction]) -> Fraction:
    """Distance to a closed (min_real, max_real, min_imag, max_imag) box."""
    min_real, max_real, min_imag, max_imag = bounds
    real = max(min_real - point.real, point.real - max_real, Fraction(0))
    imag = max(min_imag - point.imag, point.imag - max_imag, Fraction(0))
    return real * real + imag * imag
