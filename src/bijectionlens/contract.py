"""Strict stored-binary64 inputs and deterministic operation limits.

Limits may only lower the first-release hard envelope. Every Budget charge is
checked before changing its counter, so a caller can charge immediately before
performing or retaining a unit of work.
"""
from dataclasses import dataclass, fields
from fractions import Fraction
import math


@dataclass(frozen=True, slots=True)
class Limits:
    max_items: int = 20_000
    max_input_bytes: int = 8_388_608
    max_edges: int = 100_000
    max_tree_visits: int = 2_000_000
    max_tree_build: int = 4_000_000
    max_matching_scans: int = 20_000_000
    max_verify_pairs: int = 2_000_000
    max_bottleneck_pairs: int = 62_500
    max_result_bytes: int = 33_554_432
    max_wall_seconds: int = 30
    max_filtration_steps: int = 250_000
    max_filtration_checks: int = 8_000_000

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int:
                raise TypeError(f'{field.name} must be a builtin integer')
            if not 0 <= value <= field.default:
                raise ValueError(f'{field.name} must be between 0 and {field.default}')


class ResourceLimit(Exception):
    """Inconclusive exhaustion, including the next unit that was not performed."""

    def __init__(self, phase: str, used: int, requested: int, limit: int):
        if type(phase) is not str or not phase or len(phase) > 64:
            raise TypeError('phase must be a nonempty short builtin string')
        for name, value in [('used', used), ('requested', requested), ('limit', limit)]:
            if type(value) is not int:
                raise TypeError(f'{name} must be a builtin integer')
            if value < 0:
                raise ValueError(f'{name} must be nonnegative')
        self.phase = phase
        self.used = used
        self.requested = requested
        self.limit = limit
        super().__init__(f'{phase} budget exhausted: used {used}, requested {requested}, limit {limit}')


class Budget:
    """Mutable private counters with immutable public snapshots and limits."""

    __slots__ = ('_limits', '_counts')

    def __init__(self, limits: Limits | None = None):
        self._limits = _resolve_limits(limits)
        self._counts = {}

    @property
    def limits(self) -> Limits:
        return self._limits

    @property
    def counts(self) -> tuple[tuple[str, int], ...]:
        return self.snapshot()

    def snapshot(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._counts.items()))

    def charge(self, phase: str, units: int = 1) -> None:
        if type(phase) is not str:
            raise TypeError('phase must be a builtin string')
        if phase not in _PHASES:
            raise ValueError(f'unknown budget phase: {phase}')
        if type(units) is not int:
            raise TypeError('units must be a builtin integer')
        if units < 0:
            raise ValueError('units must be nonnegative')
        used = self._counts.get(phase, 0)
        limit = getattr(self._limits, 'max_' + phase)
        if units > limit - used:
            raise ResourceLimit(phase, used, units, limit)
        self._counts[phase] = used + units


_PHASES = frozenset(field.name.removeprefix('max_') for field in fields(Limits))


def _resolve_limits(limits: Limits | None) -> Limits:
    if limits is None:
        return Limits()
    if type(limits) is not Limits:
        raise TypeError('limits must be Limits or None')
    return limits


def _finite_float(value: float | int) -> float:
    if type(value) is int:
        # The bit check prevents converting a gigantic user-supplied integer.
        if value.bit_length() > 1024:
            raise ValueError('integer is not a finite binary64 value')
        try:
            number = float(value)
        except OverflowError:
            raise ValueError('integer is not a finite binary64 value') from None
        if not math.isfinite(number) or int(number) != value:
            raise ValueError('integer must be exactly representable as binary64')
    elif type(value) is float:
        number = value
    else:
        raise TypeError('value must be a builtin float or exactly representable integer')
    if not math.isfinite(number):
        raise ValueError('coordinates and tolerance must be finite')
    return 0.0 if number == 0.0 else number


def _coordinate_matches(value: Fraction, spelling: str) -> bool:
    if type(value) is not Fraction or type(spelling) is not str:
        return False
    if len(spelling) > 32 or not spelling.isascii():
        return False
    if value.numerator.bit_length() > 1024 or value.denominator.bit_length() > 1075:
        return False
    try:
        number = float.fromhex(spelling)
    except (ValueError, OverflowError):
        return False
    return (math.isfinite(number) and spelling == (0.0 if number == 0 else number).hex()
            and Fraction.from_float(number) == value)


@dataclass(frozen=True, slots=True)
class Point:
    real: Fraction
    imag: Fraction
    real_hex: str
    imag_hex: str

    def __post_init__(self):
        if not (_coordinate_matches(self.real, self.real_hex)
                and _coordinate_matches(self.imag, self.imag_hex)):
            raise ValueError('Point coordinates must match canonical finite binary64 hex')


def normalize_points(values: list | tuple, limits: Limits | None = None) -> tuple[Point, ...]:
    """Normalize a bounded builtin list/tuple, preserving occurrence order.

    The item cap applies separately to each input sequence. Its length is checked
    before a single coordinate is inspected or an output list is allocated.
    """
    limits = _resolve_limits(limits)
    if (type(values) is not list and type(values) is not tuple):
        raise TypeError('values must be a builtin list or tuple')
    size = len(values)
    if size > limits.max_items:
        raise ResourceLimit('items', 0, size, limits.max_items)
    result = []
    for value in values:
        if type(value) is complex:
            real, imag = _finite_float(value.real), _finite_float(value.imag)
        else:
            real, imag = _finite_float(value), 0.0
        result.append(Point(Fraction.from_float(real), Fraction.from_float(imag), real.hex(), imag.hex()))
    return tuple(result)


def normalize_atol(value: float | int) -> Fraction:
    """Return the exact nonnegative binary64 tolerance, without squaring it."""
    number = _finite_float(value)
    if number < 0:
        raise ValueError('atol must be nonnegative')
    return Fraction.from_float(number)


_CERTIFICATE_DECIMAL_DIGITS = 2_500
_CERTIFICATE_INTEGER_BITS = 8_192
_DECIMAL_CHUNK_BASE = 1_000_000_000


def parse_certificate_decimal(value: str) -> int:
    """Parse bounded canonical nonnegative decimal without ambient digit limits.

    CPython permits callers to lower its global decimal conversion limit to 640
    digits. Exact binary64 squared denominators can be longer, so only chunks
    of at most nine digits are passed to ``int``. No global setting is changed.
    Character bounds precede parsing; integer bounds precede caller arithmetic.
    """
    if type(value) is not str:
        raise TypeError('certificate decimal must be a builtin string')
    if len(value) > _CERTIFICATE_DECIMAL_DIGITS:
        raise ResourceLimit('certificate_decimal_digits', 0, len(value),
                            _CERTIFICATE_DECIMAL_DIGITS)
    if not value or not value.isascii() or not value.isdecimal():
        raise ValueError('certificate decimal must contain only ASCII decimal digits')
    if len(value) > 1 and value[0] == '0':
        raise ValueError('certificate decimal must use canonical spelling')
    first = len(value) % 9 or 9
    number = int(value[:first])
    for position in range(first, len(value), 9):
        number = number * _DECIMAL_CHUNK_BASE + int(value[position:position + 9])
        if number.bit_length() > _CERTIFICATE_INTEGER_BITS:
            raise ResourceLimit('certificate_integer_bits', 0, number.bit_length(),
                                _CERTIFICATE_INTEGER_BITS)
    return number


def format_certificate_decimal(value: int) -> str:
    """Format a bounded nonnegative integer with only nine-digit conversions."""
    if type(value) is not int:
        raise TypeError('certificate integer must be a builtin non-bool integer')
    if value.bit_length() > _CERTIFICATE_INTEGER_BITS:
        raise ResourceLimit('certificate_integer_bits', 0, value.bit_length(),
                            _CERTIFICATE_INTEGER_BITS)
    if value < 0:
        raise ValueError('certificate integer must be nonnegative')
    if value == 0:
        return '0'
    chunks = []
    while value:
        value, remainder = divmod(value, _DECIMAL_CHUNK_BASE)
        chunks.append(remainder)
    result = str(chunks.pop()) + ''.join(str(part).zfill(9) for part in reversed(chunks))
    # The bit envelope implies this digit envelope; retain an explicit check so
    # either constant can safely be tightened independently in a future schema.
    if len(result) > _CERTIFICATE_DECIMAL_DIGITS:
        raise ResourceLimit('certificate_decimal_digits', 0, len(result),
                            _CERTIFICATE_DECIMAL_DIGITS)
    return result
