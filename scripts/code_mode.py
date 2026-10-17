#!/usr/bin/env python3
"""调用龙下出行（RideClaw）Code Mode 端点（run_code，goja 沙箱执行 JS）。

用于需要多步/条件/循环编排的复杂查询，例如：
  "先查今天的航班，若最低价超 2000 再查明天"。

用法：
  python3 code_mode.py --code 'const r=await rideclaw.flight.search({...}); return JSON.stringify(r);'
  python3 code_mode.py --file /path/to/code.js
  # 可选：--no-retry 关闭退避重试；--timeout 秒数（默认 30）

沙箱约束（官方 Code Mode 页）：
  - 单次执行最多 20 次能力调用、30 秒 VM 超时；
  - goja：支持 const/let/箭头函数/模板字符串/解构；不支持 class / import / export；
  - 脚本自动包裹为 async IIFE，直接顶层 await + return；
  - 唯一 I/O 是 rideclaw.<domain>.<action>()（可用方法以官方文档沙箱能力清单为准，
    geo/weather 等未开放，需走标准 MCP）；
  - 成功响应为 {value, tool_calls, log[, error]}，console.log 输出随 log 数组返回。

Token：优先环境变量 RIDECLAW_TOKEN，其次 --token。沙箱内由平台自动注入，代码中勿传 Token。
退出码：0 成功 / 2 用法或 Token 问题 / 1 协议与传输层错误 / 3 工具执行错误 / 4 平台业务错误。
"""
import argparse
import json
import sys

from rideclaw_common import CODE_URL, finish, get_token, rpc_with_retry


def main():
    p = argparse.ArgumentParser(description="RideClaw Code Mode 调用器")
    p.add_argument("--code", default=None, help="要执行的 JavaScript 代码")
    p.add_argument("--file", default=None, help="JS 代码文件路径，与 --code 二选一")
    p.add_argument("--token", default=None, help="Bearer Token（优先用环境变量 RIDECLAW_TOKEN）")
    p.add_argument("--timeout", type=int, default=30, help="单次请求超时秒数，默认 30")
    p.add_argument("--no-retry", action="store_true", help="关闭限流/偶发错误的退避重试")
    p.add_argument("--retry-backoff", type=float, default=1.0,
                   help="退避初始秒数（默认 1.0，指数递增），测试用")
    p.add_argument("--url", default=None, help="覆盖端点 URL（测试注入用，勿在生产使用）")
    args = p.parse_args()

    if bool(args.code) == bool(args.file):
        print("错误: --code 与 --file 必须且只能提供一个", file=sys.stderr)
        sys.exit(2)

    token = get_token(args)
    if args.code:
        code = args.code
    else:
        try:
            with open(args.file, encoding="utf-8") as f:
                code = f.read()
        except OSError as e:
            print(f"错误: 读取代码文件失败: {e}", file=sys.stderr)
            sys.exit(2)

    outcome = rpc_with_retry(args.url or CODE_URL, token, "tools/call",
                             {"name": "run_code", "arguments": {"code": code}},
                             timeout=args.timeout, retries=0 if args.no_retry else 4,
                             backoff=args.retry_backoff)
    if outcome.ok:
        # 沙箱脚本错误（编译失败/运行时异常）也走 result.value.error，不是 isError
        result = outcome.data
        content = result.get("content") or []
        for c in content:
            if c.get("type") == "text":
                t = c["text"]
                try:
                    payload = json.loads(t)
                except (json.JSONDecodeError, ValueError):
                    print(t)
                    continue
                if isinstance(payload, dict) and payload.get("error"):
                    print(f"[沙箱脚本错误] {payload['error']}", file=sys.stderr)
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                    sys.exit(3)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
        if result.get("structuredContent"):
            print("--- structuredContent ---")
            print(json.dumps(result["structuredContent"], ensure_ascii=False, indent=2))
    else:
        finish(outcome)


if __name__ == "__main__":
    main()
