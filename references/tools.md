# RideClaw 标准 MCP 工具目录

标准端点 `/open/v1/mcp` 的公开工具以 `tools/list` 实时返回为准（官方文档口径为 **53 个**，且官方各页面间数字有漂移——勿把本表或任何数字当权威，用 `python3 scripts/mcp_call.py list` / `describe <tool>` 查实时定义）。
工具名用下划线；`tools/call` 也兼容点号别名（如 `flight.search`），新接入建议用下划线名。

## 基础字典与机场（5）
| 工具 | 用途 | 关键参数 |
|---|---|---|
| `airlines` | 航司字典 | — |
| `aircraft_types` | 机型字典 | — |
| `airports_top` | 热门机场 | — |
| `airports_top_global` | 全球热门 Top50 机场 | — |
| `airports_top_china` | 国内热门 Top50 机场 | — |

## 机票（12）
| 工具 | 用途 | 关键参数 |
|---|---|---|
| `flight_search` | 航班列表查询 | `trip_mode`(必填), `trip_type`(必填), `from_code`(必填), `to_code`(必填), `depart_date`(必填), `passengers`, `page_size`, `sort_by`；往返需另传 `return_date` |
| `flight_airport_search` | 机场搜索 | `keyword` |
| `flight_airports` | 机场详情 | `iata` |
| `flight_city_airport` | 城市机场查询 | `city` |
| `flight_pricing` | 验价 | `search_offer_id`, `passengers` |
| `flight_order_create` | 创建订单 | `offer_id`, `out_trade_no`, `passengers`, `contact` |
| `flight_order_pay` | 发起支付 | `system_no`, `pay_type`（枚举含 wechat_h5/jsapi/native/app/mini、alipay_app/h5/pc、allinpay_h5/checkout/mini；先 `payment_capabilities` 查可用项） |
| `flight_order_detail` | 订单详情 | `system_no` / `out_trade_no` |
| `flight_order_list` | 订单列表 | `status`, `start_date`, `end_date` |
| `flight_order_cancel_fee` | 查询取消手续费 | `order_id` |
| `flight_order_cancel` | 取消/退票 | `system_no`, `reason` |
| `flight_change_create` | 创建改签申请 | `system_no`, `search_offer_id` |

## 酒店（8）
| 工具 | 用途 | 关键参数 |
|---|---|---|
| `hotel_search` | 酒店列表 | `destination`, `check_in`, `check_out`（check_out 必须晚于 check_in，不可过去日期，单次最多 50 条） |
| `hotel_detail` | 酒店详情 | `hotel_id` |
| `hotel_rooms` | 房型与可订产品 | `search_offer_id` |
| `hotel_order_create` | 创建酒店订单 | `offer_id`（**必须来自 `hotel_rooms` 的产品级 offer_id，不可用 `search_offer_id`**）, `out_trade_no`, `guests`, `contact` |
| `hotel_order_pay` | 发起酒店支付 | `order_no`, `pay_type` |
| `hotel_order_list` | 订单列表 | `status`, `start_date`, `end_date` |
| `hotel_order_detail` | 订单详情 | `order_no` |
| `hotel_order_cancel` | 取消酒店订单 | `order_no`, `reason` |

## 打车（8）
| 工具 | 用途 | 关键参数 |
|---|---|---|
| `taxi_estimate` | 打车估价 | `from_lng`, `from_lat`, `from_name`, `to_lng`, `to_lat`, `to_name` |
| `taxi_order_create` | 创建打车订单 | `offer_id`, `out_trade_no`, `contact_phone` |
| `taxi_order_detail` | 订单详情 | `system_no` |
| `taxi_order_list` | 订单列表 | `status`, `system_no`, `out_trade_no`, `page` |
| `taxi_order_sync` | 同步供应商订单状态 | `system_no` |
| `taxi_order_cancel_fee` | 查询取消费 | `system_no` |
| `taxi_order_cancel` | 取消打车订单 | `system_no`, `fee_confirmed` |
| `taxi_order_pay` | 发起打车支付 | `system_no`, `pay_type` |

## 高铁（1）
| 工具 | 用途 | 关键参数 |
|---|---|---|
| `train_search` | 高铁/动车查询 | `from_station`, `to_station`, `dep_date` |

## 城际巴士（11）
| 工具 | 用途 | 关键参数 |
|---|---|---|
| `bus_search` | 城际巴士班次查询 | `start_city_code`, `end_city_code`, `date` |
| `bus_stations` | 查询上下车站点 | `start_city_code`, `end_city_code` |
| `bus_detail` | 班次详情 | `gid` |
| `bus_pre_order` | 预下单/试算价格 | `line_class_day_gid`, `start_station_gid`, `end_station_gid`, `passengers` |
| `bus_create_order` | 创建巴士订单 | `line_class_day_gid`, `start_station_gid`, `end_station_gid`, `out_trade_no` |
| `bus_order_pay` | 发起巴士支付 | `system_no`, `pay_type` |
| `bus_order_detail` | 巴士订单详情 | `system_no` |
| `bus_order_list` | 巴士订单列表 | `status`, `page` |
| `bus_order_cancel` | 取消未支付巴士订单 | `system_no`, `reason` |
| `bus_refund_rate` | 查询巴士退票手续费 | `system_no` |
| `bus_refund` | 申请巴士退票 | `system_no`, `reason` |

## 地理与天气（8）
| 工具 | 用途 | 关键参数 |
|---|---|---|
| `geo_places_search` | POI/地址关键词搜索 | `keywords` |
| `geo_places_nearby` | 附近 POI 搜索 | `location` |
| `geo_reverse` | 逆地理编码 | `location` 或 `longitude`, `latitude` |
| `geo_geocode` | 地址编码 | `address` |
| `geo_coords_convert` | 坐标系转换 | `locations`, `coordsys` |
| `geo_routes_plan` | 路线规划 | `mode`, `origin`, `destination` |
| `weather_current` | 实时天气 | `destination`（中文名或 6 位 adcode） |
| `weather_forecast` | 天气预报 | `destination`（高德返回当天至第 4 天） |

## 交易链路令牌流转
```
搜索(→search_offer_id) → 验价(→offer_id) → 创建订单(→system_no) → 支付
```
- `search_offer_id` / `offer_id` 有效期 **10 分钟**，超时需重新搜索/验价。
- 机票订单创建后有支付窗口 `pay_expire_time`（一般 15 分钟，超时自动关单）。
- 酒店两步下单：`search_offer_id` 仅用于 `hotel_rooms` 查房型，下单必须用产品级 `offer_id`。
- 订单创建幂等键：`<app_id, out_trade_no>`；重复调用返回首次订单。
- 支付成功后平台异步推进状态，通过 Webhook 推送，不建议轮询 `order_detail`。

## Code Mode（独立端点）
`/open/v1/mcp/code` 只注册 1 个工具：`run_code`（goja 沙箱执行 JS）。
- 可调用 `rideclaw.flight.search()`、`rideclaw.hotel.search()` 等方法；**可用能力仅官方文档沙箱清单的 15 个**（flight 9 个、hotel 3 个、`taxi.estimate`、`train.search`、`bus.search`）——geo/weather 与大部分订单操作不在其中，需走标准 MCP。
- 硬约束：单次最多 **20 次能力调用**、**30 秒超时**；支持 `const/let`/箭头函数/模板字符串/解构，**不支持 `class`/`import`/`export`**；顶层 `await` 自动包裹。
- 代码必须 `return` 最终结果；成功响应为 `{value, tool_calls, log[, error]}`，`console.log` 输出随 `log` 返回。
- Token 由平台自动注入沙箱，`run_code` 参数里不要手动传 Token 字段。
