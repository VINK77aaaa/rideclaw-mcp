#!/usr/bin/env python3
"""共享工具：请求、官方三层错误模型解析、Token 处理、输出掩码。

官方错误模型（docs.longxiachuxing.com 错误码页）分三层，本库统一归一化为
``RpcOutcome``，调用方按 ``kind`` 分流：

- ``rpc_error``   JSON-RPC 层 ``error``（-32700/-32600/-32601/-32602/-32603）
- ``tool_error``  ``result.isError=true``（参数缺失、offer_id 过期等，Agent 自我修正后重试）
- ``api_error``   HTTP 层 ``{"code","message","data","request_id"}`` 信封。
                  非 200：401xx 鉴权 / 403xx 权限 / 429xx 限流 / 5xxxx 服务端；
                  HTTP 200 也可能带信封（40201/40202 参数错、50401 上游超时）——
                  官方注意事项页明确「勿仅依赖 HTTP 状态码，请通过 code 字段判断」。
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

MCP_URL = "https://api.longxiachuxing.com/open/v1/mcp"
CODE_URL = "https://api.longxiachuxing.com/open/v1/mcp/code"
DEFAULT_TIMEOUT = 30  # 官方 Python 示例同款：requests.post(..., timeout=30)

# 官方错误码页：可重试类。429xx 退避后重试；50001 偶发内部错误 1~2s 后重试；
# 50401 上游数据源超时（HTTP 200 + code 信封），1~2s 后重试。
RETRYABLE_CODES = {42901, 42902, 50001, 50301, 50401}

TOKEN_RE = re.compile(r"(rdak_(?:live|test)_[A-Za-z0-9]+)")


def mask(text: str) -> str:
    """把文本中形如 rdak_live_xxx 的 Token 掩码，避免误入日志/回显。"""
    return TOKEN_RE.sub(lambda m: m.group(1)[:10] + "***", text)


def detect_token_problem(token: str):
    """本地快速失败：前缀不对（官方固定 rdak_live_/rdak_test_）或明显缺 Bearer 前缀。"""
    if token.startswith("Bearer "):
        return "Token 误带了 'Bearer ' 前缀，请只传 Token 本体（脚本会自动加 Bearer）。"
    if not token.startswith(("rdak_live_", "rdak_test_")):
        return ("Token 前缀异常：官方 Token 形如 rdak_live_... 或 rdak_test_...，"
                "当前值前缀不符，请核对是否复制完整。")
    return None


def get_token(args) -> str:
    t = getattr(args, "token", None) or os.environ.get("RIDECLAW_TOKEN") or ""
    if not t:
        print("错误: 缺少 Token。请通过环境变量 RIDECLAW_TOKEN 提供（优先），或 --token 参数。",
              file=sys.stderr)
        sys.exit(2)
    problem = detect_token_problem(t)
    if problem:
        print("错误: " + problem, file=sys.stderr)
        sys.exit(2)
    return t


class RpcOutcome:
    """一次 JSON-RPC 调用的归一化结果。"""

    def __init__(self, kind, data=None, http_status=None, request_id=None):
        self.kind = kind  # 'ok' | 'rpc_error' | 'tool_error' | 'api_error' | 'transport_error'
        self.data = data
        self.http_status = http_status
        self.request_id = request_id

    @property
    def ok(self):
        return self.kind == "ok"


def _envelope_fields(payload):
    """从 HTTP 层信封取 (code, message, request_id)；非信封 JSON 返回 None。"""
    if isinstance(payload, dict) and "code" in payload and "message" in payload:
        rid = payload.get("request_id")
        return payload.get("code"), payload.get("message"), rid
    return None


def _http_error_detail(e: urllib.error.HTTPError):
    """读 HTTPError 响应体，尽量解析官方信封。"""
    raw = b""
    try:
        raw = e.read()
    except Exception:
        pass
    payload = None
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            payload = None
    env = _envelope_fields(payload)
    if env:
        return env
    snippet = raw.decode("utf-8", "replace").strip()
    return None, (snippet[:300] if snippet else str(e.reason)), None


def rpc_once(url, token, method, params, timeout=DEFAULT_TIMEOUT):
    """单次 JSON-RPC 调用，永不抛网络/HTTP 异常，全部归一化为 RpcOutcome。"""
    body = {"jsonrpc": "2.0", "method": method, "id": 1}
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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as e:
        code, message, rid = _http_error_detail(e)
        return RpcOutcome("api_error", {"code": code, "message": message},
                          http_status=e.code, request_id=rid)
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        return RpcOutcome("transport_error", {"message": str(reason)})

    try:
        res = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        snippet = raw.decode("utf-8", "replace").strip()[:200]
        return RpcOutcome("transport_error",
                          {"message": f"响应不是合法 JSON（HTTP {status}）: {snippet}"},
                          http_status=status)

    if not isinstance(res, dict):
        return RpcOutcome("transport_error",
                          {"message": f"响应结构异常（HTTP {status}）"}, http_status=status)

    # 1) JSON-RPC 协议层错误
    if "error" in res:
        err = res["error"] or {}
        return RpcOutcome("rpc_error", {"code": err.get("code"), "message": err.get("message")},
                          http_status=status)

    # 2) HTTP 层 code 信封（可能随 HTTP 200 一起来，如 40201/40202/50401）
    env = _envelope_fields(res)
    if env:
        code, message, rid = env
        return RpcOutcome("api_error", {"code": code, "message": message},
                          http_status=status, request_id=rid)

    # 3) 工具层：result.isError
    result = res.get("result")
    if not isinstance(result, dict):
        return RpcOutcome("transport_error",
                          {"message": "响应缺少 result（既非 error 也非信封）"}, http_status=status)
    if result.get("isError"):
        content = result.get("content") or [{}]
        text = content[0].get("text", "") if content else ""
        return RpcOutcome("tool_error", {"message": text}, http_status=status)

    return RpcOutcome("ok", result, http_status=status)


def is_retryable(outcome: RpcOutcome):
    """限流/偶发服务端错误/上游超时 → 可退避重试；其余错误让 Agent 自我修正。"""
    if outcome.kind == "api_error" and outcome.data.get("code") in RETRYABLE_CODES:
        return True
    return outcome.kind == "transport_error"


def rpc_with_retry(url, token, method, params, timeout=DEFAULT_TIMEOUT,
                   retries=4, backoff=1.0):
    """带指数退避的重试（官方建议：初始 1s，最多 5 次尝试）。仅对可重试错误生效。"""
    import time
    outcome = rpc_once(url, token, method, params, timeout=timeout)
    attempts = 1
    while (not outcome.ok) and attempts <= retries and is_retryable(outcome):
        wait = backoff * (2 ** (attempts - 1))
        print(f"可重试错误（{describe_outcome(outcome)}），{wait:.0f}s 后第 {attempts + 1} 次尝试…",
              file=sys.stderr)
        time.sleep(wait)
        outcome = rpc_once(url, token, method, params, timeout=timeout)
        attempts += 1
    return outcome


def describe_outcome(outcome: RpcOutcome) -> str:
    """生成面向 Agent 的单行错误描述，始终带 request_id（官方排查优先字段）。"""
    if outcome.kind == "rpc_error":
        hint = _rpc_hint(outcome.data.get("code"))
        return f"JSON-RPC 协议错误 code={outcome.data.get('code')}: {outcome.data.get('message')}{hint}"
    if outcome.kind == "tool_error":
        return f"工具执行错误（isError，需修正参数后重试）: {outcome.data.get('message')}"
    if outcome.kind == "api_error":
        code = outcome.data.get("code")
        return (f"平台业务错误 code={code}（HTTP {outcome.http_status}）: "
                f"{outcome.data.get('message')}{_api_hint(code)}"
                + (f" [request_id={outcome.request_id}]" if outcome.request_id else ""))
    if outcome.kind == "transport_error":
        return f"网络/传输错误: {outcome.data.get('message')}"
    return "ok"


def _rpc_hint(code):
    return {
        -32700: "（JSON 解析失败）",
        -32600: "（无效请求）",
        -32601: "（方法不存在：工具名可能拼错，先跑 list 核对）",
        -32602: "（参数错误：核对 inputSchema）",
        -32603: "（服务端内部错误）",
    }.get(code, "")


def _api_hint(code):
    hints = {
        40110: "（服务端未启用 Bearer Token 鉴权）",
        40111: "（Bearer 令牌格式非法：应为 rdak_live_/rdak_test_ 开头，且勿带 'Bearer ' 前缀）",
        40112: "（Bearer 令牌无效：核对 Token 是否完整复制）",
        40113: "（Token 已吊销：到开放平台后台重新签发）",
        40114: "（Token 已过期）",
        40301: "（应用已禁用）",
        40302: "（Token 环境与平台不一致：live/test 用错了环境）",
        40303: "（来源 IP 不在白名单：把本机公网出口 IP 登记到开放平台后台，勿盲目重试）",
        40304: "（该应用未启用 Bearer Token 鉴权）",
        40305: "（该应用未启用签名鉴权，请使用 Bearer Token）",
        40201: "（请求参数不合法：修正参数后重试，勿原样重发）",
        40202: "（请求参数缺失：补齐必填参数）",
        42901: "（触发 QPS 上限：官方建议指数退避，初始 1s，勿并发轰炸）",
        42902: "（触发日调用量上限：次日 0 点（北京时间）重置，或申请提额）",
        50001: "（服务内部错误：偶发，1~2s 后可重试）",
        50301: "（防重放服务暂不可用：稍后重试）",
        50401: "（上游数据源超时：1~2s 后可重试）",
    }
    return hints.get(code, "")


def print_result(result: dict):
    """成功结果打印：content[].text 尽量美化，structuredContent 追加输出。"""
    content = result.get("content") or []
    for c in content:
        if c.get("type") == "text":
            t = c["text"]
            try:
                print(json.dumps(json.loads(t), ensure_ascii=False, indent=2))
            except (json.JSONDecodeError, ValueError):
                print(t)
    if result.get("structuredContent"):
        print("--- structuredContent ---")
        print(json.dumps(result["structuredContent"], ensure_ascii=False, indent=2))


def finish(outcome: RpcOutcome):
    """统一收尾：成功打印结果；失败打印单行错误到 stderr 并按类别给退出码。
    退出码约定：0 成功 / 2 用法或 Token 问题 / 1 协议与传输层 / 3 工具层 / 4 平台业务层。"""
    if outcome.ok:
        print_result(outcome.data)
        return
    print("[错误] " + mask(describe_outcome(outcome)), file=sys.stderr)
    code_map = {"rpc_error": 1, "transport_error": 1, "tool_error": 3, "api_error": 4}
    sys.exit(code_map.get(outcome.kind, 1))
