#!/usr/bin/env python3
"""将 ACL4SSR 规则展开为可直接用于 3X-UI 的路由 YAML。"""

import argparse
import ipaddress
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/Providers/'
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
CLASSICAL_TYPES = {'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-WILDCARD', 'DOMAIN-KEYWORD', 'IP-CIDR', 'IP-CIDR6'}
IP_TYPES = {'IP-CIDR', 'IP-CIDR6'}
MAX_ROUTING_BYTES = 2 * 1024 * 1024


def read_rule(name, spec, fixtures=None):
    if fixtures:
        raw = (fixtures / (name + '.yaml')).read_bytes()
    else:
        request = urllib.request.Request(
            UPSTREAM + name + '.yaml',
            headers={'User-Agent': 'company-acl4ssr-sync/1.0'},
        )
        with urllib.request.urlopen(request, timeout=35) as response:
            raw = response.read(8_000_001)
    if not raw or len(raw) > 8_000_000:
        raise ValueError(f'{name}：规则文件为空或过大')
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get('payload'), list):
        raise ValueError(f'{name}：需要包含 payload 列表的 YAML 映射')
    rules = parsed['payload']
    if len(rules) < spec['min_entries']:
        raise ValueError(f'{name}：规则数量 {len(rules)} 低于下限 {spec["min_entries"]}')
    if not all(isinstance(value, str) and value.strip() and len(value) < 2048 for value in rules):
        raise ValueError(f'{name}：存在无效的规则条目')
    return rules


def validate_rule_line(line, names):
    if not isinstance(line, str):
        raise ValueError(f'无效的路由规则：{line!r}')
    parts = line.split(',')
    if not parts or any(not part.strip() for part in parts):
        raise ValueError(f'无效的路由规则：{line!r}')
    kind = parts[0]
    if kind == 'MATCH':
        if parts != ['MATCH', 'PROXY']:
            raise ValueError('兜底规则必须是 MATCH,PROXY')
    elif kind == 'RULE-SET':
        if len(parts) != 3 or parts[1] not in names:
            raise ValueError(f'未知或无效的规则集引用：{line}')
    elif kind in CLASSICAL_TYPES | {'GEOIP'}:
        if len(parts) == 4 and kind in IP_TYPES and parts[3] == 'no-resolve':
            return
        if len(parts) != 3:
            raise ValueError(f'无效的路由规则：{line}')
    else:
        raise ValueError(f'不支持的路由规则类型：{line}')


def expand_provider_rule(name, spec, entry, target):
    if spec['behavior'] == 'ipcidr':
        network = ipaddress.ip_network(entry, strict=False)
        kind = 'IP-CIDR6' if network.version == 6 else 'IP-CIDR'
        return f'{kind},{entry},{target}'
    parts = entry.split(',')
    kind = parts[0]
    if kind not in CLASSICAL_TYPES or len(parts) not in (2, 3) or not parts[1]:
        raise ValueError(f'{name}：无法展开的规则 {entry!r}')
    if len(parts) == 3 and (kind not in IP_TYPES or parts[2] != 'no-resolve'):
        raise ValueError(f'{name}：无法展开的规则 {entry!r}')
    if kind in IP_TYPES:
        network = ipaddress.ip_network(parts[1], strict=False)
        if (kind == 'IP-CIDR6') != (network.version == 6):
            raise ValueError(f'{name}：IP 规则类型与地址不符：{entry}')
    if kind == 'DOMAIN-SUFFIX' and parts[1].startswith('*.'):
        kind = 'DOMAIN-WILDCARD'
    suffix = ',no-resolve' if len(parts) == 3 else ''
    return f'{kind},{parts[1]},{target}{suffix}'


def build(config, fixtures=None, output=None):
    policy = yaml.safe_load(config.read_text(encoding='utf-8'))
    if not isinstance(policy, dict) or not isinstance(policy.get('providers'), dict):
        raise ValueError('策略配置必须包含 providers 映射')
    providers = policy['providers']
    if not providers:
        raise ValueError('未配置任何规则源')
    for name, spec in providers.items():
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(spec, dict):
            raise ValueError(f'无效的规则源：{name}')
        if spec.get('behavior') not in {'classical', 'ipcidr'}:
            raise ValueError(f'{name}：内联模式只支持 classical 和 ipcidr')
        if type(spec.get('min_entries')) is not int or spec['min_entries'] < 1:
            raise ValueError(f'{name}：规则数量下限无效')
    groups = policy.get('proxy-groups')
    if not isinstance(groups, list) or not groups:
        raise ValueError('策略配置必须包含 proxy-groups 列表')
    group_names = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('策略组必须是 YAML 映射')
        group_name = group.get('name')
        if not isinstance(group_name, str) or not group_name.strip() or group_name in group_names:
            raise ValueError(f'策略组名称无效或重复：{group_name!r}')
        if group.get('type') != 'select':
            raise ValueError(f'{group_name}：单节点配置只支持 select 策略组')
        if 'include-all-proxies' in group and type(group['include-all-proxies']) is not bool:
            raise ValueError(f'{group_name}：include-all-proxies 必须是布尔值')
        group_names.add(group_name)
    if 'PROXY' not in group_names:
        raise ValueError('策略组必须包含 PROXY，以匹配现有路由规则')
    for group in groups:
        refs = group.get('proxies', [])
        if not isinstance(refs, list) or any(
            not isinstance(ref, str) or ref not in group_names | {'DIRECT'} for ref in refs
        ):
            raise ValueError(f'{group["name"]}：proxies 引用了未知策略组或节点')
        if not refs and not group.get('include-all-proxies', False):
            raise ValueError(f'{group["name"]}：需要 proxies 或 include-all-proxies')
    custom_rules = policy.get('custom_rules', [])
    policy_rules = policy.get('rules')
    if not isinstance(custom_rules, list) or not isinstance(policy_rules, list):
        raise ValueError('custom_rules 和 rules 必须是列表')
    source_rules = custom_rules + policy_rules
    if not source_rules or source_rules[-1] != 'MATCH,PROXY':
        raise ValueError('最后一条规则必须是 MATCH,PROXY')
    for index, rule in enumerate(source_rules):
        validate_rule_line(rule, providers)
        if rule == 'MATCH,PROXY' and index != len(source_rules) - 1:
            raise ValueError('MATCH,PROXY 只能出现在末尾')

    snapshots = {name: read_rule(name, spec, fixtures) for name, spec in providers.items()}
    expanded = []
    for rule in source_rules:
        parts = rule.split(',')
        if parts[0] == 'RULE-SET':
            name, target = parts[1:]
            expanded.extend(
                expand_provider_rule(name, providers[name], entry, target)
                for entry in snapshots[name]
            )
        else:
            expanded.append(rule)

    content = yaml.safe_dump({'proxy-groups': groups, 'rules': expanded}, allow_unicode=True, sort_keys=False)
    if len(content.encode('utf-8')) > MAX_ROUTING_BYTES:
        raise ValueError('生成的路由文件超过 3X-UI 远程路由的 2 MiB 上限')
    destination = output or ROOT / 'dist/3x-ui.yaml'
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.new-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            file.write(content)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'已生成 {len(expanded)} 条内联规则：{destination}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT / 'config/policy.yaml')
    parser.add_argument('--fixtures', type=Path, help='离线测试规则目录')
    parser.add_argument('--output', type=Path, help='输出文件路径')
    args = parser.parse_args()
    try:
        build(args.config, args.fixtures, args.output)
    except Exception as exc:
        print(f'构建失败：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
