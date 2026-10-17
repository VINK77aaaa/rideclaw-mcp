#!/usr/bin/env python3
"""调用龙下出行（RideClaw）标准 MCP 端点（JSON-RPC 2.0）。

用法：
  # 拉取全部公开工具列表
  python3 mcp_call.py list

  # 查看某工具的完整定义（含 inputSchema）
  python3 mcp_call.py describe flight_search

  # 调用工具（参数用 JSON 字符串或 --arg k=v，二选一）
  python3 mcp_call.py call flight_search '{"trip_mode":"domestic","trip_type":"oneway","from_code":"CAN","to_code":"SHA","depart_date":"2026-10-18","passengers":{"adult":1},"page_size":5}'
  python3 mcp_call.py call flight_search --arg trip_mode=domestic --arg trip_type=oneway --arg from_code=CAN --arg to_code=SHA --arg depart_date=2026-10-18

  # 可选：--no-retry 关闭退避重试；--timeout 秒数（默认 30）

Token：优先环境变量 RIDECLAW_TOKEN，其次 --token（避免进 shell history）。
退出码：0 成功 / 2 用法或 Token 问题 / 1 协议与传输层错误 / 3 工具执行错误 / 4 平台业务错误。
错误分类与 request_id 透传见 scripts/rideclaw_common.py 的模块注释。
"""
import argparse
import json
import sys

from rideclaw_common import MCP_URL, finish, get_token, mask, rpc_with_retry


def parse_args():
    p = argparse.ArgumentParser(description="RideClaw 标准 MCP 调用器")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--token", default=None, help="Bearer Token（优先用环境变量 RIDECLAW_TOKEN）")
        sp.add_argument("--timeout", type=int, default=30, help="单次请求超时秒数，默认 30")
        sp.add_argument("--no-retry", action="store_true", help="关闭限流/偶发错误的退避重试")
        sp.add_argument("--retry-backoff", type=float, default=1.0,
                        help="退避初始秒数（默认 1.0，指数递增），测试用")
        sp.add_argument("--url", default=None, help="覆盖端点 URL（测试注入用，勿在生产使用）")

    p_list = sub.add_parser("list", help="列出全部公开工具")
    add_common(p_list)

    p_desc = sub.add_parser("describe", help="查看某工具的完整定义与 inputSchema")
    p_desc.add_argument("name", help="工具名，如 flight_search")
    add_common(p_desc)

    p_call = sub.add_parser("call", help="调用工具")
    p_call.add_argument("name", help="工具名，如 flight_search")
    p_call.add_argument("json_args", nargs="?", default=None,
                        help="JSON 参数字符串，与 --arg 互斥")
    p_call.add_argument("--arg", action="append", default=[],
                        help="k=v 形式参数，可多次传递；值尽量按 JSON 解析（数字/布尔/对象）")
    add_common(p_call)

    return p.parse_args()


def parse_kvs(pairs):
    """--arg k=v 列表 → dict；值按 JSON 解析，失败退回字符串；缺 '=' 报用法错误。"""
    out = {}
    for kv in pairs:
        k, sep, v = kv.partition("=")
        if not sep or not k:
            print(f"错误: --arg 需要 k=v 形式，收到: {kv!r}", file=sys.stderr)
            sys.exit(2)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def main():
    args = parse_args()
    token = get_token(args)
    timeout = args.timeout
    retries = 0 if args.no_retry else 4
    url = args.url or MCP_URL

    if args.cmd == "list":
        outcome = rpc_with_retry(url, token, "tools/list", {}, timeout=timeout,
                                 retries=retries, backoff=args.retry_backoff)
        if not outcome.ok:
            finish(outcome)
        tools = outcome.data.get("tools", [])
        print(f"工具总数: {len(tools)}（以本响应为准，文档中的数字可能漂移）")
        for t in tools:
            print(f"- {t['name']}: {t.get('description', '')[:80]}")
        return

    if args.cmd == "describe":
        outcome = rpc_with_retry(url, token, "tools/list", {}, timeout=timeout,
                                 retries=retries, backoff=args.retry_backoff)
        if not outcome.ok:
            finish(outcome)
        for t in outcome.data.get("tools", []):
            if t.get("name") == args.name:
                print(json.dumps(t, ensure_ascii=False, indent=2))
                return
        print(f"错误: 未找到工具 {args.name!r}，先跑 list 核对名称。", file=sys.stderr)
        sys.exit(2)

    # call
    if args.json_args and args.arg:
        print("错误: json_args 与 --arg 只能二选一", file=sys.stderr)
        sys.exit(2)
    if args.json_args:
        try:
            arguments = json.loads(args.json_args)
        except json.JSONDecodeError as e:
            print(f"错误: JSON 参数解析失败: {e}", file=sys.stderr)
            sys.exit(2)
    elif args.arg:
        arguments = parse_kvs(args.arg)
    else:
        arguments = {}

    outcome = rpc_with_retry(url, token, "tools/call",
                             {"name": args.name, "arguments": arguments},
                             timeout=timeout, retries=retries, backoff=args.retry_backoff)
    if not outcome.ok:
        finish(outcome)
    finish(outcome)


if __name__ == "__main__":
    main()
