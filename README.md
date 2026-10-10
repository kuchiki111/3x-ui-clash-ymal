# 3X-UI 内联 ACL4SSR 路由规则

这个项目定时读取 ACL4SSR 的规则数据，将每一条规则直接展开到 `dist/3x-ui.yaml`。生成文件包含 `proxy-groups` 和 `rules`，没有 `rule-providers`、规则文件链接、节点或用户密钥。路由顺序由 `config/policy.yaml` 决定，实际节点仍由 3X-UI 为每个订阅用户生成。

## 使用

1. 将本仓库设为公开，并确认默认分支为 `main`。
2. 确认仓库里已有 `dist/3x-ui.yaml`。需要立即更新时，在 GitHub Actions 中手动运行 **Sync ACL4SSR rule data**。此后工作流每天约北京时间 06:00 自动更新；GitHub 不保证定时任务精确准点执行。
3. 在 **3X-UI → 面板设置 → 订阅 → Clash/Mihomo** 中启用路由，把下面的地址填入 **全局路由规则**：

   `https://raw.githubusercontent.com/kuchiki111/3x-ui-clash-ymal/main/dist/3x-ui.yaml`

这个地址仅用于让面板读取完整的 YAML 文件。文件内部的路由规则已经展开，不会再引用其他规则文件。也可以打开生成文件，将完整内容直接粘贴到支持内联 YAML 的 3X-UI 版本中；该文件包含上万条规则，使用远程文件通常更方便。

生成内容示例：

```yaml
proxy-groups:
- name: 节点选择
  type: select
  include-all-proxies: true
  proxies:
  - DIRECT
- name: PROXY
  type: select
  proxies:
  - 节点选择
rules:
- DOMAIN-SUFFIX,lan,DIRECT
- IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
- DOMAIN-KEYWORD,admarvel,REJECT
- DOMAIN-WILDCARD,*.pimg.tw,PROXY
- IP-CIDR,1.0.1.0/24,DIRECT
- GEOIP,CN,DIRECT
- MATCH,PROXY
```

示例省略了中间上万条规则；完整内容见 `dist/3x-ui.yaml`。

保存后刷新 Clash/Mihomo 订阅，确认订阅里有用户节点、`节点选择` 与 `PROXY` 两个策略组，以及展开后的路由规则。`节点选择` 自动收录该订阅的所有节点，也提供 `DIRECT` 选项；`PROXY` 作为规则使用的固定名称，指向 `节点选择`。如果在「节点选择」中选中 `DIRECT`，命中 `PROXY` 的流量也会直连。首次刷新后请确认选中的是想使用的节点。此文件不包含实际节点，不能单独作为完整的 Mihomo 配置导入。

## 生成逻辑

- `config/policy.yaml` 指定策略组、规则源、匹配顺序和目标策略。`RULE-SET` 条目只在构建阶段使用，生成文件中会替换成具体的 `DOMAIN-SUFFIX`、`IP-CIDR` 等规则。
- 上游 `classical` 规则会保留 `no-resolve` 标记并插入目标策略；其中 `DOMAIN-SUFFIX,*.` 会改为 Mihomo 对应的 `DOMAIN-WILDCARD,*.`。`ipcidr` 列表会展开成 `IP-CIDR` 或 `IP-CIDR6` 规则。
- 每次生成都会检查规则文件结构、最小条数、支持的规则类型以及最终文件大小。任何一步失败，工作流都不会提交这次产物，上次成功生成的文件继续保留。
- 输出文件限制为 2 MiB，以适配 3X-UI 当前远程路由的大小上限。规则源目前只支持 `classical` 和 `ipcidr`。

## 修改策略

在 `config/policy.yaml` 中调整 `proxy-groups`、`providers` 和有序的 `rules` 列表，然后手动运行工作流。最后一条必须是 `MATCH,PROXY`。`custom_rules` 会放在所有上游规则之前。

`custom_rules` 默认是空列表。例如需要让企业域名直连，可写入 `DOMAIN-SUFFIX,internal.example.com,DIRECT`。广告拦截规则可能误拦网站功能，可按需要删除 `BanAD`、`BanProgramAD` 对应的规则条目。

## 本地构建

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build.py
python3 -m unittest discover -s tests -v
```

本地构建需要能够访问 GitHub Raw。构建过程中只读取公开规则，不读取或写入用户订阅、UUID、令牌等敏感数据。

上游规则来源：[ACL4SSR](https://github.com/ACL4SSR/ACL4SSR)。
