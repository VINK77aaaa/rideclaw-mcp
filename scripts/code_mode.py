#!/usr/bin/env python3
"""调用龙下出行（RideClaw）Code Mode 端点（run_code，沙箱执行 JS）。

用于需要多步/条件/循环编排的复杂查询，例如：
  "先查今天的航班，若最低价超 2000 再查明天"。

用法：
  python3 code_mode.py --code 'const r=await rideclaw.flight.search({...}); return JSON.stringify(r);' [--token TOKEN]
  python3 code_mode.py --file /path/to/code.js [--token TOKEN]

Token 优先级：--token > 环境变量 RIDECLAW_TOKEN。
Code Mode 的 Token 由平台自动注入沙箱，脚本仅用于鉴权访问端点，run_code 内部无需传 Token。
"""
import argparse
import json
import os
import sys
import urllib.request

CODE_URL = "https://api.longxiachuxing.com/open/v1/mcp/code"


def rpc(url: str, token: str, code: str):
    body = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "run_code", "arguments": {"code": code}},
        "id": 1,
    }
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
    p = argparse.ArgumentParser(description="RideClaw Code Mode 调用器")
    p.add_argument("--code", default=None, help="要执行的 JavaScript 代码")
    p.add_argument("--file", default=None, help="JS 代码文件路径，与 --code 二选一")
    p.add_argument("--token", default=None)
    args = p.parse_args()

    if bool(args.code) == bool(args.file):
        print("错误: --code 与 --file 必须且只能提供一个", file=sys.stderr); sys.exit(2)

    token = args.token or os.environ.get("RIDECLAW_TOKEN") or ""
    if not token:
        print("错误: 缺少 Token。请通过 --token 参数或环境变量 RIDECLAW_TOKEN 提供。", file=sys.stderr)
        sys.exit(2)

    code = args.code if args.code else open(args.file, encoding="utf-8").read()

    res = rpc(CODE_URL, token, code)
    if "error" in res:
        print(json.dumps(res, ensure_ascii=False)); sys.exit(1)
    result = res["result"]
    if result.get("isError"):
        txt = result.get("content", [{}])[0].get("text", "")
        print(f"[工具错误] {txt}", file=sys.stderr); sys.exit(3)
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
