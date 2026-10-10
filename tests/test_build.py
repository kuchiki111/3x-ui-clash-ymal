import tempfile
import unittest
from pathlib import Path
import yaml
from scripts.build import read_rule, validate_rule_line

class RuleTests(unittest.TestCase):
    def test_rule_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'LocalAreaNetwork.yaml').write_text('payload:\n  - DOMAIN-SUFFIX,local\n', encoding='utf-8')
            result = read_rule('LocalAreaNetwork', {'behavior': 'classical','min_entries': 1}, p)
            self.assertEqual(len(result['payload']), 1)
    def test_unknown_reference(self):
        with self.assertRaises(ValueError):
            validate_rule_line('RULE-SET,missing,DIRECT', {'ChinaIp': {}})
    def test_ipcidr_rejects_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'ChinaIp.yaml').write_text('payload:\n  - not-an-ip\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_rule('ChinaIp', {'behavior': 'ipcidr', 'min_entries': 1}, p)

if __name__ == '__main__':
    unittest.main()
