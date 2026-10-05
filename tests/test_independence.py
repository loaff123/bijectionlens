"""Architecture is part of the certificate-verification contract."""
import ast
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

class IndependenceTests(unittest.TestCase):
    def test_verifier_does_not_import_optimizer(self):
        import bijectionlens
        path = Path(bijectionlens.__path__[0]) / 'verify.py'
        self.assertTrue(path.is_file(), 'independent verifier is not implemented')
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or '').split('.')[-1], {'matching', 'spatial', 'compare', 'bottleneck'})
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split('.')[-1], {'matching', 'spatial', 'compare', 'bottleneck'})

    def test_verification_survives_disabled_optimizer(self):
        import bijectionlens as bl
        self.assertTrue(callable(getattr(bl, 'compare', None)), 'comparison API missing')
        result = bl.compare([0, 0, 3], [0, 3, 3], atol=0.1)
        matching = importlib.import_module('bijectionlens.matching')
        spatial = importlib.import_module('bijectionlens.spatial')
        with patch.object(matching, 'maximum_matching', side_effect=AssertionError('optimizer called')), patch.object(spatial, 'radius_graph', side_effect=AssertionError('spatial called')):
            self.assertEqual(bl.verify_comparison([0, 0, 3], [0, 3, 3], atol=0.1, result=result).status, 'valid')

if __name__ == '__main__':
    unittest.main()
