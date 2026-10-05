"""Distribution discovery must exclude non-package bytecode directories."""
from pathlib import Path
import tomllib
import unittest

class PackagingMetadataTests(unittest.TestCase):
    def test_only_the_explicit_runtime_package_is_discovered(self):
        config_path = Path(__file__).resolve().parents[1] / 'pyproject.toml'
        self.assertTrue(config_path.is_file(), 'copy pyproject.toml with installed test fixtures')
        config = tomllib.loads(config_path.read_text())['tool']['setuptools']
        discovery = config['packages']['find']
        self.assertIs(discovery.get('namespaces'), False, 'implicit namespace discovery can package bytecode directories')
        self.assertEqual(discovery.get('include'), ['bijectionlens'])
        self.assertIs(config.get('include-package-data'), False)

if __name__ == '__main__':
    unittest.main()
