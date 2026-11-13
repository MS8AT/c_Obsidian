import os
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prism_core import PrismStore


class PrismCoreTests(unittest.TestCase):
    def test_example_case_evaluates_with_explicit_schema(self):
        with tempfile.TemporaryDirectory(prefix='cobsidian-prism-') as tmp:
            store = PrismStore(Path(tmp))
            model = store.create_example()
            evaluation = store.evaluate(model['id'])

        self.assertEqual(model['schema'], 'c-obsidian.prism/v1')
        self.assertEqual(evaluation['schema'], 'c-obsidian.prism-evaluation/v1')
        self.assertEqual(evaluation['engine'], 'c-obsidian.prism-rules/v1')
        self.assertTrue(evaluation['results'])


if __name__ == '__main__':
    unittest.main()
