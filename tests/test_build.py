import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.build import build, read_rule, validate_rule_line


class RuleTests(unittest.TestCase):
    def test_rule_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixtures = Path(temporary)
            (fixtures / 'LocalAreaNetwork.yaml').write_text(
                'payload:\n  - DOMAIN-SUFFIX,local\n', encoding='utf-8'
            )
            rules = read_rule('LocalAreaNetwork', {'behavior': 'classical', 'min_entries': 1}, fixtures)
            self.assertEqual(rules, ['DOMAIN-SUFFIX,local'])

    def test_unknown_reference(self):
        with self.assertRaises(ValueError):
            validate_rule_line('RULE-SET,missing,DIRECT', {'ChinaIp': {}})

    def test_invalid_routing_rule(self):
        with self.assertRaises(ValueError):
            validate_rule_line('FOO,BAR', {})

    def test_inline_output_preserves_order_and_ip_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            (fixtures / 'LocalAreaNetwork.yaml').write_text(
                'payload:\n  - DOMAIN-SUFFIX,local\n  - DOMAIN-SUFFIX,*.example.com\n  - IP-CIDR,10.0.0.0/8,no-resolve\n',
                encoding='utf-8',
            )
            (fixtures / 'ChinaIp.yaml').write_text(
                'payload:\n  - 1.0.1.0/24\n', encoding='utf-8'
            )
            config = root / 'policy.yaml'
            config.write_text(
                'providers:\n'
                '  LocalAreaNetwork: {behavior: classical, min_entries: 3}\n'
                '  ChinaIp: {behavior: ipcidr, min_entries: 1}\n'
                'proxy-groups:\n'
                '  - name: 节点选择\n'
                '    type: select\n'
                '    include-all-proxies: true\n'
                '    proxies: [DIRECT]\n'
                '  - name: PROXY\n'
                '    type: select\n'
                '    proxies: [节点选择]\n'
                'custom_rules:\n'
                '  - DOMAIN-SUFFIX,corp.example.com,DIRECT\n'
                'rules:\n'
                '  - RULE-SET,LocalAreaNetwork,DIRECT\n'
                '  - RULE-SET,ChinaIp,DIRECT\n'
                '  - MATCH,PROXY\n',
                encoding='utf-8',
            )
            output = root / 'dist/3x-ui.yaml'
            build(config, fixtures, output)
            generated = yaml.safe_load(output.read_text(encoding='utf-8'))
            self.assertEqual(
                generated,
                {'proxy-groups': [
                    {'name': '节点选择', 'type': 'select', 'include-all-proxies': True, 'proxies': ['DIRECT']},
                    {'name': 'PROXY', 'type': 'select', 'proxies': ['节点选择']},
                ], 'rules': [
                    'DOMAIN-SUFFIX,corp.example.com,DIRECT',
                    'DOMAIN-SUFFIX,local,DIRECT',
                    'DOMAIN-WILDCARD,*.example.com,DIRECT',
                    'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve',
                    'IP-CIDR,1.0.1.0/24,DIRECT',
                    'MATCH,PROXY',
                ]},
            )


if __name__ == '__main__':
    unittest.main()
