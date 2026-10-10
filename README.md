# 3X-UI 的 Clash/Mihomo 路由规则

本项目将 [ACL4SSR](https://github.com/ACL4SSR/ACL4SSR) 的规则展开，生成供 3X-UI 订阅服务使用的 `dist/3x-ui.yaml`。文件包含策略组和内联路由规则，**不包含节点**。3X-UI 会把它与每位用户的节点合并，生成完整的 Clash/Mihomo 订阅。

使用时有两个不同的地址：

| 地址 | 填写位置 | 内容 |
| --- | --- | --- |
| [GitHub 规则文件](https://raw.githubusercontent.com/kuchiki111/3x-ui-clash-ymal/main/dist/3x-ui.yaml) | 3X-UI 的「全局路由规则」 | 策略组和规则，没有节点 |
| 3X-UI 为用户生成的 Clash/Mihomo 订阅地址 | Clash Verge Rev 的远程订阅 | 该用户的节点、策略组和规则 |

**不要把 GitHub 规则地址直接导入 Clash Verge Rev。**它不是完整的节点订阅。用户订阅地址包含访问凭据，不要公开分享。

## 一、让 GitHub 自动更新规则

仓库已配置 [Sync ACL4SSR rule data](.github/workflows/sync.yml)：每天约北京时间 06:00 从 ACL4SSR 获取规则，验证后更新 `dist/3x-ui.yaml`。上游内容没有变化时，不会产生新提交。GitHub 的定时任务可能延迟。

1. 确认仓库公开、默认分支为 `main`，并在 [Actions 页面](https://github.com/kuchiki111/3x-ui-clash-ymal/actions)找到 **Sync ACL4SSR rule data**。如果显示 **Enable workflow**，先启用它。
2. 建议点 **Run workflow**，选择 `main`，手动运行一次。出现绿色对勾，就说明当前更新流程可以执行。
3. 以后无需每天点击；需要立即更新时，再手动运行一次即可。

如果工作流失败，点开该次运行查看失败步骤。仓库必须允许 GitHub Actions 运行；工作流已声明 `contents: write`，用于提交生成文件。

## 二、在 3X-UI 配置路由

1. 打开 **面板设置 → 订阅**，启用订阅服务和 **Clash/Mihomo** 订阅。
2. 在 **Clash/Mihomo** 设置中启用路由，将以下地址填入 **全局路由规则**，然后保存：

   ```text
   https://raw.githubusercontent.com/kuchiki111/3x-ui-clash-ymal/main/dist/3x-ui.yaml
   ```

3. 确认 3X-UI 服务器能够访问该地址。若面板不接受远程地址，请检查所用 3X-UI 版本是否支持远程 Clash 路由；不要把 URL 当作 YAML 内容粘贴。

这个地址是公开的规则文件，不是用户订阅。生成文件中的 `RULE-SET` 已被展开，不需要客户端再下载规则提供者文件。

## 三、在 Clash Verge Rev 导入用户订阅

1. 在 3X-UI 的客户端详情中，复制该用户的 **Clash/Mihomo 订阅地址**。优先使用面板给出的地址；较新的 3X-UI 也提供 `/mihomo/<Sub ID>` 入口。不要复制普通的 `vless://` 节点分享链接或上面的 GitHub 规则地址。
2. 打开 **Clash Verge Rev → 订阅/配置**，新建远程订阅，粘贴 **3X-UI 用户订阅地址**，保存并选中它。
3. 更新订阅，运行模式选 **规则**。确认配置里有实际节点，以及可见的「节点选择」和「兜底选择」策略组。

GitHub 更新规则后，3X-UI 需要重新读取远程规则，Clash Verge Rev 也需要刷新用户订阅；更新不一定即时出现在客户端。

## 当前路由是怎样工作的

规则按从上到下的顺序匹配，先命中的规则生效：

| 来源或规则 | 处理方式 |
| --- | --- |
| `LocalAreaNetwork`、`UnBan` | 直连 |
| `BanAD`、`BanProgramAD` | 拒绝 |
| `ProxyGFWlist` | 交给 `PROXY` |
| `ChinaDomain`、`ChinaIp`、`GEOIP,CN` | 直连 |
| 最后的 `MATCH` | 交给「兜底选择」 |

策略组的关系如下：

```text
ProxyGFWlist 命中 → PROXY → 节点选择 → 当前选中的节点或 DIRECT
其他规则都未命中 → 兜底选择 → 节点选择或 DIRECT
```

- 「节点选择」自动收录订阅中的节点，也提供 `DIRECT`；你可以在客户端手动选节点。
- `PROXY` 只是规则使用的中转组，固定指向「节点选择」。它标记为隐藏，但仍参与路由。
- 「兜底选择」保持可见，可独立选「节点选择」或 `DIRECT`。选「节点选择」时，最终仍取决于该组当前选中的节点；若「节点选择」选了 `DIRECT`，经过它的流量也会直连。

完整规则以 [生成文件](dist/3x-ui.yaml) 为准；规则源、顺序和策略组定义在 [策略文件](config/policy.yaml)。

## 修改规则与本地构建

只需编辑 `config/policy.yaml`：

- `providers` 指定构建时读取的 ACL4SSR 规则源。
- `proxy-groups` 定义客户端看到的策略组。
- `custom_rules` 放在所有上游规则之前，适合加入自己的优先规则，默认留空。
- `rules` 决定规则源的顺序和目标策略，最后一条必须是 `MATCH`。

例如需要让企业域名直连，可以在 `custom_rules` 中加入 `DOMAIN-SUFFIX,internal.example.com,DIRECT`。修改并推送到 `main` 后，手动运行一次 GitHub 工作流即可重新生成文件。

也可以在本地生成和检查：

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build.py
python3 -m unittest discover -s tests -v
```

本地构建需要访问 GitHub Raw。构建器检查规则格式、最低条数和输出大小；生成文件超过 2 MiB 时会失败。它不会读取用户订阅、UUID 或令牌。
