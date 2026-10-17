---
name: rideclaw-mcp
description: 调用龙下出行（RideClaw）开放平台的 MCP 服务。当需要查询机票、酒店、打车、城际巴士、高铁、地理/天气，或创建/支付/退改订单时使用；也用于通过 Code Mode 的 run_code 沙箱执行 JS 编排多步/条件查询。命中场景：用户要查机票价格与航班、订酒店、打车估价、查长途大巴班次、查高铁车次、查天气或 POI，以及需要"先查这个再判断查那个"的复合出行查询。
---

# RideClaw MCP（龙下出行开放平台）

## 概述

两套 JSON-RPC 2.0 端点，同一把 Bearer Token 鉴权（Token 来自用户偏好，Agent 调用前从上下文取得，通过 `--token` 或环境变量 `RIDECLAW_TOKEN` 传入）：

- **标准 MCP**：`https://api.longxiachuxing.com/open/v1/mcp`，公开 59 个工具（机票/酒店/打车/巴士/高铁/地理/天气 + 订单/退改/支付）。
- **Code Mode**：`https://api.longxiachuxing.com/open/v1/mcp/code`，仅 `run_code`，沙箱执行 JS，用 `rideclaw.<domain>.<action>()` 编排多步/条件查询。

## 快速开始（标准 MCP）

优先用自带脚本，避免手写 JSON-RPC：

```bash
# 列出全部工具
python3 scripts/mcp_call.py list --token "$RIDECLAW_TOKEN"

# 查询航班（JSON 参数）
python3 scripts/mcp_call.py call flight_search \
  '{"trip_mode":"domestic","trip_type":"oneway","from_code":"CAN","to_code":"SHA","depart_date":"2026-10-18","passengers":{"adult":1},"page_size":5}' \
  --token "$RIDECLAW_TOKEN"

# 查询航班（k=v 参数，适合少量字段）
python3 scripts/mcp_call.py call flight_search \
  --arg from_code=CAN --arg to_code=SHA --arg depart_date=2026-10-18 --token "$RIDECLAW_TOKEN"
```

Token 也可通过环境变量 `RIDECLAW_TOKEN` 提供（`export RIDECLAW_TOKEN=<token>`），脚本会优先读 `--token`，其次环境变量。

## 工作流

1. **判定端点**：单步查询（查机票/酒店/巴士/火车/天气/POI）→ 标准 MCP 的对应工具；多步、条件分支、循环编排 → Code Mode 的 `run_code`。
2. **取 Token**：从用户偏好中取龙下出行 Token，传给脚本。**不要把 Token 写进日志、回复或任何产物。**
3. **调工具**：用 `scripts/mcp_call.py` 调标准工具，用 `scripts/code_mode.py` 跑 JS。
4. **解析结果**：工具返回 `content[].text`（多为 JSON 字符串）与可选 `structuredContent`。Agent 只取关键信息回给用户（如最便宜的前 3 班），避免上下文溢出。
5. **错误修正**：`result.isError=true` 是工具执行错误（如缺参数、offer_id 过期），按错误文本补参/重新验价后重试；JSON-RPC 层 `error` 才是协议错误。

## 交易链路（下单类）

```
搜索(→search_offer_id) → 验价(→offer_id) → 创建订单(→system_no) → 支付
```
- `search_offer_id` / `offer_id` 有效期 **10 分钟**，超时重新搜索/验价。
- 订单创建幂等键 `<app_id, out_trade_no>`；重复调用返回首次订单。
- `order_pay` 省略 `pay_type` 时默认 `alipay_h5`；可用支付方式先调 `payment_capabilities`，从 `available_pay_types` 中选择。
- **下单/支付/退改属于外部写操作，执行前必须先取得用户明确确认。**

## Code Mode 用法

```bash
python3 scripts/code_mode.py --code \
'const r=await rideclaw.flight.search({trip_mode:"domestic",trip_type:"oneway",from_code:"CAN",to_code:"SHA",depart_date:"2026-10-18",passengers:{adult:1},page_size:3});
const top3=r.flights.map(f=>({no:f.flight_no,dep:f.dep_time,arr:f.arr_time,lowest:f.cabins[0].lowest_price}));
return JSON.stringify({total:r.total,top3});' --token "$RIDECLAW_TOKEN"
```
- 代码可 `await` 且必须 `return` 最终结果；中间数据留在沙箱。
- Token 由平台自动注入沙箱，`run_code` 参数里**不要**手动传 Token 字段。
- 典型编排："先查今天，价格超 2000 再看明天"、多城市比价、批量查多段行程。

## 工具目录

完整 59 工具清单、分类、关键参数与令牌流转见 `references/tools.md`。查询前如需精确参数名/枚举，先 `mcp_call.py list` 看实时 `inputSchema`（以工具返回为准）。

## 边界与注意

- 所有价格/余票/班次均以工具实时返回为准，不做虚构或记忆填充。
- 涉及支付、下单、退改、取消等写操作，需用户确认后执行。
- Token 属敏感信息，不写入日志、脚本注释、产物或对外回复。
