---
name: rideclaw-mcp
description: 调用龙下出行（RideClaw）开放平台的 MCP 服务。当需要查询机票、酒店、打车、城际巴士、高铁、地理/天气，或创建/支付/退改订单时使用；也用于通过 Code Mode 的 run_code 沙箱执行 JS 编排多步/条件查询。命中场景：用户要查机票价格与航班、订酒店、打车估价、查长途大巴班次、查高铁车次、查天气或 POI，以及需要"先查这个再判断查那个"的复合出行查询。
---

# RideClaw MCP（龙下出行开放平台）

## 概述

两套 JSON-RPC 2.0 端点，同一把 Bearer Token 鉴权（Token 形如 `rdak_live_...`，来自用户偏好，Agent 调用前从上下文取得，通过环境变量 `RIDECLAW_TOKEN` 传入，脚本会自动加 `Bearer ` 前缀）：

- **标准 MCP**：`https://api.longxiachuxing.com/open/v1/mcp`，公开工具以 `tools/list` 实时返回为准（本文档写作时为 53 个：机票/酒店/打车/巴士/高铁/地理/天气 + 订单/退改/支付；官方文档不同页面的数字有漂移，勿硬信任何数字）。
- **Code Mode**：`https://api.longxiachuxing.com/open/v1/mcp/code`，仅 `run_code`，沙箱执行 JS，用 `rideclaw.<domain>.<action>()` 编排多步/条件查询。

## 快速开始（标准 MCP）

优先用自带脚本，避免手写 JSON-RPC：

```bash
# Token 从用户偏好取得后先放进环境变量（不要写进命令行参数，会进 shell history）
export RIDECLAW_TOKEN=rdak_live_xxx

# 列出全部工具（工具数量与名称以本命令实时输出为准）
python3 scripts/mcp_call.py list

# 查看某工具的完整 inputSchema（拿不准参数名/必填项时先 describe）
python3 scripts/mcp_call.py describe flight_search

# 查询航班（JSON 参数）
python3 scripts/mcp_call.py call flight_search \
  '{"trip_mode":"domestic","trip_type":"oneway","from_code":"CAN","to_code":"SHA","depart_date":"2026-10-18","passengers":{"adult":1},"page_size":5}'

# 查询航班（k=v 参数；trip_mode/trip_type 为必填，不可省略）
python3 scripts/mcp_call.py call flight_search \
  --arg trip_mode=domestic --arg trip_type=oneway \
  --arg from_code=CAN --arg to_code=SHA --arg depart_date=2026-10-18
```

可选参数：`--timeout 30`（单次请求超时秒数）、`--no-retry`（关闭限流/偶发错误的退避重试）。

## 工作流

1. **判定端点**：单步查询（查机票/酒店/巴士/火车/天气/POI）→ 标准 MCP 的对应工具；多步、条件分支、循环编排 → Code Mode 的 `run_code`。
2. **取 Token**：从用户偏好中取龙下出行 Token（`rdak_live_...`），`export RIDECLAW_TOKEN=...` 后调用。**不要把 Token 写进日志、回复、命令行参数或任何产物。**
3. **调工具**：用 `scripts/mcp_call.py` 调标准工具（拿不准参数先 `describe`），用 `scripts/code_mode.py` 跑 JS。
4. **解析结果**：工具返回 `content[].text`（多为 JSON 字符串）与可选 `structuredContent`。Agent 只取关键信息回给用户（如最便宜的前 3 班），避免上下文溢出。
5. **错误修正**：按下方「错误处理」分诊，不要盲目重试。

## 错误处理（脚本已按官方三层模型归一化）

脚本把所有失败打到 stderr 的单行 `[错误] ...` 中，并按类别给退出码。Agent 先看退出码和错误类别再行动：

| 退出码 | 类别 | 含义与 Agent 动作 |
|---|---|---|
| 0 | 成功 | 正常解析 stdout。 |
| 2 | 用法/Token | 本地快速失败（缺 Token、前缀不像 `rdak_live_`）：核对凭据，不发网络请求。 |
| 1 | JSON-RPC 协议错误 / 网络传输错误 | `-32601` 工具名拼错→先 `list`；`-32602` 参数错→核对 inputSchema；传输错误（超时/非 JSON）→检查网络后重试。 |
| 3 | 工具执行错误（`isError=true`） | 按错误文本补参/重新验价后重试（如 `offer_id 过期`→重新验价；`trip_mode 必填`→补必填项）。 |
| 4 | 平台业务错误（HTTP 层 `{"code","message","request_id"}` 信封） | 按错误码分诊（见下），**错误信息里始终带 `request_id`，向平台排查时附上**。 |

高频业务错误码：

- `40111/40112/40113/40114`：Token 格式非法/无效/已吊销/已过期 → 请用户重新提供有效 Token，勿重试。
- `40303`：**来源 IP 不在白名单**（官方要求所有接口过白名单校验）→ 提示用户到开放平台后台登记本机公网出口 IP，**勿盲目重试**。
- `40201/40202`：参数不合法/缺失（HTTP 200 + code 信封）→ 修正参数后重试。
- `42901/42902`：QPS / 日配额上限 → 脚本已自动指数退避重试（官方建议初始 1s、最多 5 次）；仍失败说明配额耗尽，勿继续轰炸。**注意：官方警告短时间重复提交相同搜索请求会被临时锁定。**
- `50001/50401`：偶发内部错误 / 上游数据源超时 → 脚本已自动重试；仍失败等 1~2 秒再试一次。

## 交易链路（下单类）

```
搜索(→search_offer_id) → 验价(→offer_id) → 创建订单(→system_no) → 支付
```
- `search_offer_id` / `offer_id` 有效期 **10 分钟**，超时重新搜索/验价。
- **机票**：订单创建后有支付窗口 `pay_expire_time`（一般 15 分钟，超时自动关单）。
- **酒店是两步下单**：`search_offer_id` 只能查房型（`hotel_rooms`），必须用房型产品返回的产品级 `offer_id` 下单；**不可直接拿 `search_offer_id` 去下单**。
- **机票往返**：`trip_type=roundtrip` 时必须同时传 `depart_date` 和 `return_date`。
- 订单创建幂等键 `<app_id, out_trade_no>`；重复调用返回首次订单。
- `pay_type` 官方枚举见 `payment_capabilities` 或 `describe <tool>`；**下单/支付/退改属于外部写操作，执行前必须先取得用户明确确认。**

## Code Mode 用法

```bash
python3 scripts/code_mode.py --code \
'const r=await rideclaw.flight.search({trip_mode:"domestic",trip_type:"oneway",from_code:"CAN",to_code:"SHA",depart_date:"2026-10-18",passengers:{adult:1},page_size:3});
const top3=r.flights.map(f=>({no:f.flight_no,dep:f.dep_time,arr:f.arr_time,lowest:f.cabins[0].lowest_price}));
return JSON.stringify({total:r.total,top3});'
```
- 代码可 `await` 且必须 `return` 最终结果；中间数据留在沙箱。
- Token 由平台自动注入沙箱，`run_code` 参数里**不要**手动传 Token 字段。
- 典型编排："先查今天，价格超 2000 再看明天"、多城市比价、批量查多段行程。

**沙箱硬约束（官方 Code Mode 文档）：**
- 单次执行最多 **20 次能力调用**、**30 秒超时**；分页等循环要设上限。
- goja 沙箱：支持 `const/let`、箭头函数、模板字符串、解构；**不支持 `class`/`import`/`export`**（用普通函数代替）；顶层 `await` 已自动包裹，勿再手写 async IIFE。
- 可用能力是**官方文档沙箱清单里的 15 个方法**（flight 9 个、hotel 3 个、`taxi.estimate`、`train.search`、`bus.search`）；**geo/weather 及大部分订单操作不在 Code Mode 里**，写 `rideclaw.weather.current` 会失败——地理/天气走标准 MCP。
- 成功响应为 `{value, tool_calls, log[, error]}`；`console.log()` 输出随 `log` 数组返回，可用 `log` 判断脚本执行到哪一步。脚本检测到 `error` 字段会以退出码 3 报「沙箱脚本错误」。

## 工具目录

`references/tools.md` 是官方 53 工具的静态对照表（参数摘要）。**精确参数名/必填项/枚举以 `mcp_call.py describe <tool>` 的实时 `inputSchema` 为准**——官方文档自身在漂移（不同页面写 15/53 个工具、退改签"待上线"但工具已在列），勿把静态表当权威。

## 边界与注意

- 所有价格/余票/班次均以工具实时返回为准，不做虚构或记忆填充。
- 涉及支付、下单、退改、取消等写操作，需用户确认后执行。
- Token 属敏感信息，不写入日志、脚本注释、产物或对外回复；脚本输出已对 `rdak_live_/rdak_test_` 前缀 Token 做掩码。
- 脚本按官方要求默认 30s 超时 + 指数退避重试（限流/偶发错误）；大规模批量查询请放慢节奏，避免触发限流锁定。
