#!/usr/bin/env python3
"""生成 3X-UI 远程路由 YAML，并保存已验证的 ACL4SSR 规则快照。

不包含用户节点或密钥。所有下载内容通过验证后才发布。
"""
import argparse
import ipaddress
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/Providers/'
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
GITHUB_REPO = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')


def read_rule(name, spec, fixtures=None):
    if fixtures:
        raw = (fixtures / (name + '.yaml')).read_bytes()
    else:
        url = UPSTREAM + name + '.yaml'
        req = urllib.request.Request(url, headers={'User-Agent': 'company-acl4ssr-sync/1.0'})
        with urllib.request.urlopen(req, timeout=35) as r:
            raw = r.read(8_000_001)
    if not raw or len(raw) > 8_000_000:
        raise ValueError(f'{name}: empty or oversized rule file')
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get('payload'), list):
        raise ValueError(f'{name}: expected YAML mapping with payload list')
    rules = parsed['payload']
    if len(rules) < spec['min_entries']:
        raise ValueError(f'{name}: {len(rules)} rules below minimum {spec["min_entries"]}')
    if not all(isinstance(v, str) and v.strip() and len(v) < 2048 for v in rules):
        raise ValueError(f'{name}: invalid payload element')
    if spec['behavior'] == 'ipcidr':
        for rule in rules:
            ipaddress.ip_network(rule.strip().strip("'\""), strict=False)
    return {'payload': rules}


def validate_rule_line(line, names):
    if not isinstance(line, str) or ',' not in line:
        raise ValueError(f'Invalid routing rule: {line!r}')
    parts = line.split(',')
    if parts[0] == 'RULE-SET' and (len(parts) < 3 or parts[1] not in names):
        raise ValueError(f'Unknown rule-provider: {line}')
    if parts[0] == 'MATCH' and line != 'MATCH,PROXY':
        raise ValueError('Fallback must be MATCH,PROXY')


def build(repo, config, fixtures=None):
    if not GITHUB_REPO.fullmatch(repo):
        raise ValueError('Set REPOSITORY to GitHub owner/repo, e.g. acme/company-rules')
    policy = yaml.safe_load(config.read_text(encoding='utf-8'))
    providers = policy['providers']
    if not providers:
        raise ValueError('No providers configured')
    for name, spec in providers.items():
        if not NAME.fullmatch(name) or spec['behavior'] not in {'classical', 'ipcidr', 'domain'}:
            raise ValueError(f'Invalid provider: {name}')
        if not isinstance(spec['min_entries'], int) or spec['min_entries'] < 1:
            raise ValueError(f'Invalid minimum for {name}')
    all_rules = policy.get('custom_rules', []) + policy['rules']
    for rule in all_rules:
        validate_rule_line(rule, providers)
    if all_rules[-1] != 'MATCH,PROXY':
        raise ValueError('Last rule must be MATCH,PROXY')
    snapshots = {name: read_rule(name, spec, fixtures) for name, spec in providers.items()}
    base = f'https://raw.githubusercontent.com/{repo}/main/dist/rules/'
    output = {'rule-providers': {}, 'rules': all_rules}
    for name, spec in providers.items():
        output['rule-providers'][name] = {
            'type': 'http', 'behavior': spec['behavior'], 'format': 'yaml',
            'url': base + name + '.yaml',
            'path': './rules/company-acl4ssr/' + name + '.yaml',
            'interval': policy.get('interval', 86400),
        }
    # 不生成 proxy-groups，保留 3X-UI 自动生成的 PROXY 分组。
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    # 写入前先准备所有文件，确保生成的 YAML 内容稳定一致。
    ready = {dist / 'rules' / (n + '.yaml'): yaml.safe_dump(v, allow_unicode=True, sort_keys=False) for n, v in snapshots.items()}
    ready[dist / '3x-ui.yaml'] = yaml.safe_dump(output, allow_unicode=True, sort_keys=False)
    for path, content in ready.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmpname = tempfile.mkstemp(prefix='.new-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(tmpname, path)
        finally:
            if os.path.exists(tmpname):
                os.unlink(tmpname)
    print('Built', len(snapshots), 'ACL4SSR snapshots; published files:')
    for path in ready:
        print(' ', path.relative_to(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=os.getenv('GITHUB_REPOSITORY', ''))
    parser.add_argument('--config', type=Path, default=ROOT / 'config/policy.yaml')
    parser.add_argument('--fixtures', type=Path, help='Offline test fixtures; never use in production')
    args = parser.parse_args()
    try:
        build(args.repo, args.config, args.fixtures)
    except Exception as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
