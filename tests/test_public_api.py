"""Public API and wheel metadata contract, using only the imported package."""
import json
import unittest


class PublicAPITests(unittest.TestCase):
    def test_public_example_and_explicit_verification(self):
        import bijectionlens as bl
        self.assertTrue(callable(getattr(bl, 'compare', None)), 'compare public API missing')
        result = bl.compare([0, 0.9], [0, -0.9], atol=1)
        self.assertEqual(result.status, 'matched')
        self.assertEqual(result.verification_status, 'not_run')
        checked = bl.verify_comparison([0, 0.9], [0, -0.9], atol=1, result=result)
        self.assertEqual(checked.status, 'valid')
        wire = json.loads(json.dumps(bl.to_dict(result)))
        self.assertEqual(wire['status'], 'matched')
        self.assertEqual(bl.verify_comparison([0, 0.9], [0, -0.9], atol=1, result=wire).status, 'valid')

    def test_diagnostic_example(self):
        import bijectionlens as bl
        self.assertTrue(callable(getattr(bl, 'bottleneck', None)), 'bottleneck public API missing')
        result = bl.bottleneck([0, 3], [0, -1+2.5j])
        self.assertEqual((result.q_numerator, result.q_denominator), ('9', '1'))
        self.assertEqual(bl.verify_bottleneck([0, 3], [0, -1+2.5j], result=result).status, 'valid')

    def test_result_truth_requires_explicit_status(self):
        import bijectionlens as bl
        self.assertTrue(callable(getattr(bl, 'compare', None)), 'compare public API missing')
        for result in (bl.compare([], [], atol=0), bl.bottleneck([], [])):
            with self.assertRaises(TypeError):
                bool(result)

if __name__ == '__main__':
    unittest.main()
