"""Exact, bounded unordered comparison of stored finite binary64 values."""
from .compare import compare
from .bottleneck import bottleneck
from .verify import verify_comparison, verify_bottleneck
from .contract import Limits
from .models import (ComparisonResult, BottleneckResult, VerificationResult,
                     HallEvidence, ResourceEvidence)
from .codec import to_dict

__version__ = '0.1.0'
__all__ = ['compare', 'bottleneck', 'verify_comparison', 'verify_bottleneck', 'Limits',
           'ComparisonResult', 'BottleneckResult', 'VerificationResult', 'HallEvidence',
           'ResourceEvidence', 'to_dict', '__version__']
