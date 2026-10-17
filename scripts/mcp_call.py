#!/usr/bin/env python3
"""调用龙下出行（RideClaw）标准 MCP 端点。

用法：
  # 拉取全部公开工具列表
  python3 mcp_call.py list [--token TOKEN]

  # 调用某个工具（参数用 JSON 字符串或 --arg k=v 多次传递）
  python3 mcp_call.py call flight_search '{"trip_mode":"domestic","trip_type":"oneway","from_code":"CAN","to_code":"SHA","depart_date":"2026-10-18","passengers":{"adult":1},"page_size":5}' [--token TOKEN]
  python3 mcp_call.py call flight_search --arg from_code=CAN --arg to_code=SHA --arg depart_date=2026-10-18

Token 优先级：--token > 环境变量 RIDECLAW_TOKEN。
不传时若环境无 Token，会从错误信息提示用户提供。
"""
import argparse
import json
import os
import sys
import urllib.request

MCP_URL = "https://api.longxiachuxing.com/open/v1/mcp"


def get_token(args) -> str:
    t = args.token or os.environ.get("RIDECLAW_TOKEN") or ""
    if not t:
        print("错误: 缺少 Token。请通过 --token 参数或环境变量 RIDECLAW_TOKEN 提供。", file=sys.stderr)
        sys.exit(2)
    return t


def rpc(url: str, token: str, method: str, params=None, rpc_id: int = 1):
    body = {"jsonrpc": "2.0", "method": method, "id": rpc_id}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main():
    p = argparse.ArgumentParser(description="RideClaw 标准 MCP 调用器")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出全部公开工具")
    p_list.add_argument("--token", default=None)

    p_call = sub.add_parser("call", help="调用工具")
    p_call.add_argument("name", help="工具名，如 flight_search")
    p_call.add_argument("json_args", nargs="?", default=None, help="JSON 参数字符串，与 --arg 互斥")
    p_call.add_argument("--arg", action="append", default=[], help="k=v 形式参数，可多次传递")
    p_call.add_argument("--token", default=None)

    args = p.parse_args()
    token = get_token(args)

    if args.cmd == "list":
        res = rpc(MCP_URL, token, "tools/list", rpc_id=1)
        if "error" in res:
            print(json.dumps(res, ensure_ascii=False)); sys.exit(1)
        tools = res["result"]["tools"]
        print(f"工具总数: {len(tools)}")
        for t in tools:
            print(f"- {t['name']}: {t.get('description','')[:80]}")
        return

    # call
    if args.json_args and args.arg:
        print("错误: json_args 与 --arg 只能二选一", file=sys.stderr); sys.exit(2)
    if args.json_args:
        try:
            arguments = json.loads(args.json_args)
        except json.JSONDecodeError as e:
            print(f"错误: JSON 参数解析失败: {e}", file=sys.stderr); sys.exit(2)
    elif args.arg:
        arguments = {}
        for kv in args.arg:
            k, _, v = kv.partition("=")
            # 尽量把数值/布尔转成原生类型
            try:
                arguments[k] = json.loads(v)
            except json.JSONDecodeError:
                arguments[k] = v
    else:
        arguments = {}

    res = rpc(MCP_URL, token, "tools/call", {"name": args.name, "arguments": arguments}, rpc_id=1)
    if "error" in res:
        print(json.dumps(res, ensure_ascii=False)); sys.exit(1)
    result = res["result"]
    if result.get("isError"):
        # 工具执行错误：把错误文本打出来，供 Agent 自我修正后重试
        txt = result.get("content", [{}])[0].get("text", "")
        print(f"[工具错误] {txt}", file=sys.stderr); sys.exit(3)
    # 正常返回：content 里的 text 多为 JSON 字符串，尽量美化输出
    for c in result.get("content", []):
        if c.get("type") == "text":
            t = c["text"]
            try:
                print(json.dumps(json.loads(t), ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                print(t)
    if "structuredContent" in result:
        print("--- structuredContent ---")
        print(json.dumps(result["structuredContent"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
