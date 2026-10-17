> **本仓库已合并至 [agent-skills](https://github.com/VINK77aaaa/agent-skills)** — 统一入口，clone 一次即可装全部技能。本仓库仅作历史留存，不再更新。

# rideclaw-mcp

龙虾出行（RideClaw）开放平台 MCP 调用技能：标准 MCP 工具（以 `tools/list` 实时返回为准，2026-10-18 实测 **59 个**）+ Code Mode 沙箱编排。

## 结构

- `SKILL.md` — Agent 技能入口：工作流、错误处理分诊、交易链路规则、Code Mode 沙箱约束。
- `scripts/mcp_call.py` — 标准 MCP 调用器（`list` / `describe <tool>` / `call`）。
- `scripts/code_mode.py` — Code Mode `run_code` 调用器。
- `scripts/rideclaw_common.py` — 共享库：官方三层错误模型归一化、环境与域名解析、超时与指数退避重试、Token 校验与输出掩码。
- `references/tools.md` — 官方工具静态对照表（写作时 53 个，2026-10-18 实测已增至 59 个；权威以实时 `inputSchema` 为准）。
- `tests/test_scripts.py` — 单元测试 + 本地 mock 端点端到端（`python3 tests/test_scripts.py`）。

## 环境与域名

官方只公布了生产域名，sandbox 域名未公开，因此脚本不做任何猜测性硬编码：

| 场景 | 用法 |
|---|---|
| 生产（默认） | `--env prod` 或省略，走 `https://api.longxiachuxing.com` |
| sandbox | `export RIDECLAW_SANDBOX_BASE=https://<官方给的 sandbox 域名>` 后加 `--env sandbox` |
| 任意域名 | `--base-url https://...`，或 `export RIDECLAW_BASE_URL=https://...` |

域名解析优先级：`--url`（完整端点，仅测试注入）> `--base-url` > `RIDECLAW_BASE_URL` > `--env` 映射。

**令牌环境一致性**：官方生产域名对 `rdak_test_` 令牌直接返回 `40302 令牌环境与当前平台不一致（platform=prod, token=sandbox）`。脚本在本地就拦掉这种组合（退出码 2，不发请求），避免 Agent 拿着一条无操作性的错误空转。

## 鉴权

`/open/v1/*`（含 MCP 与 Code Mode）统一使用 **Bearer Token**，官方《鉴权说明》原文：「无需自行计算签名」。

- 请求头只需 `Authorization: Bearer rdak_live_xxx`，脚本自动补 `Bearer ` 前缀。
- 不要额外发送 `X-App-Key`：实测一旦带上它，网关会转而要求 `X-Timestamp` / `X-Nonce` / `X-Sign`（缺失返回 `40102`，签名不对返回 `40105`）。这是另一条签名鉴权通道，与 MCP 调用无关，官网首页那段 `curl` 配置容易让人误判。
- `40302` 是令牌环境不匹配（`live` 令牌打 sandbox、或 `test` 令牌打生产），不是签名问题。

## 凭据来源

优先级：`--token` > 环境变量 `RIDECLAW_TOKEN` > 凭据文件 `~/.rideclaw/credentials.env`。

凭据文件是纯文本 `KEY=VALUE`（读取时不做 shell 展开），与私密仓库 `rideclaw-credentials` 同步：

```bash
git clone https://github.com/VINK77aaaa/rideclaw-credentials.git ~/rideclaw-credentials
mkdir -p ~/.rideclaw && cp ~/rideclaw-credentials/credentials.env ~/.rideclaw/
```

配好之后直接 `python3 scripts/mcp_call.py list` 即可，不需要每次 export。

## 脚本行为约定

- Token：`--token` > `RIDECLAW_TOKEN` > `~/.rideclaw/credentials.env`；本地校验 `rdak_live_/rdak_test_` 前缀与环境匹配后快速失败。
- 错误模型：JSON-RPC `error` / `result.isError` / HTTP 层 `{"code","message","request_id"}` 信封（含 HTTP 200 + code 的 40201/40202/50401）统一归一化，`request_id` 始终透传。
- 退出码：0 成功 / 2 用法或 Token / 1 协议与传输 / 3 工具执行 / 4 平台业务错误。
- 默认 30s 超时；429xx / 50001 / 50301 / 50401 / 传输错误自动指数退避重试（初始 1s，最多 5 次尝试），可用 `--no-retry` 关闭。
- 输出对 `rdak_live_/rdak_test_` Token 掩码。

## 许可证

MIT，见 `LICENSE`。
