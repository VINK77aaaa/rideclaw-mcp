# rideclaw-mcp

龙下出行（RideClaw）开放平台 MCP 调用技能：标准 MCP 工具（以 `tools/list` 实时返回为准，官方文档口径 53 个）+ Code Mode 沙箱编排。

## 结构

- `SKILL.md` — Agent 技能入口：工作流、错误处理分诊、交易链路规则、Code Mode 沙箱约束。
- `scripts/mcp_call.py` — 标准 MCP 调用器（`list` / `describe <tool>` / `call`）。
- `scripts/code_mode.py` — Code Mode `run_code` 调用器。
- `scripts/rideclaw_common.py` — 共享库：官方三层错误模型归一化、超时与指数退避重试、Token 校验与输出掩码。
- `references/tools.md` — 官方 53 工具静态对照表（权威以实时 `inputSchema` 为准）。
- `tests/test_scripts.py` — 单元测试 + 本地 mock 端点端到端（`python3 tests/test_scripts.py`）。

## 脚本行为约定

- Token：优先环境变量 `RIDECLAW_TOKEN`，其次 `--token`；本地校验 `rdak_live_/rdak_test_` 前缀快速失败。
- 错误模型：JSON-RPC `error` / `result.isError` / HTTP 层 `{"code","message","request_id"}` 信封（含 HTTP 200 + code 的 40201/40202/50401）统一归一化，`request_id` 始终透传。
- 退出码：0 成功 / 2 用法或 Token / 1 协议与传输 / 3 工具执行 / 4 平台业务错误。
- 默认 30s 超时；429xx / 50001 / 50301 / 50401 / 传输错误自动指数退避重试（初始 1s，最多 5 次尝试），可用 `--no-retry` 关闭。
- 输出对 `rdak_live_/rdak_test_` Token 掩码。
