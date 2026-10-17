#!/usr/bin/env python3
"""rideclaw-mcp 脚本测试：单元测试 + 本地 mock 服务器端到端。

运行：
  python3 tests/test_scripts.py            # 全部
  python3 tests/test_scripts.py TestUnit   # 只跑单元
  python3 tests/test_scripts.py TestE2E    # 只跑端到端

端到端用本地 http.server 起 mock MCP 端点，覆盖官方三层错误模型：
JSON-RPC error / result.isError / HTTP 层 code 信封（含 HTTP 200 + code），
以及空 content、非 JSON 响应、429 退避重试等分支。
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import rideclaw_common as rc  # noqa: E402


class TestUnit(unittest.TestCase):
    def setUp(self):
        # 隔离真实凭据文件，避免本机 ~/.rideclaw/credentials.env 影响断言
        self._orig_creds = rc.CREDENTIALS_FILE
        rc.CREDENTIALS_FILE = os.path.join(tempfile.gettempdir(), "rideclaw-no-such.env")

    def tearDown(self):
        rc.CREDENTIALS_FILE = self._orig_creds

    def test_mask_hides_token(self):
        text = "bad request for rdak_live_abcdef123456xyz done"
        out = rc.mask(text)
        self.assertNotIn("rdak_live_abcdef123456xyz", out)
        self.assertIn("rdak_live_***", out)
        # test 前缀同样掩码
        self.assertNotIn("rdak_test_zzzz", rc.mask("t rdak_test_zzzz"))

    def test_detect_token_problem(self):
        self.assertIn("Bearer", rc.detect_token_problem("Bearer rdak_live_x"))
        self.assertIn("前缀", rc.detect_token_problem("sk-abc123"))
        self.assertIn("前缀", rc.detect_token_problem(" rdak_live_x"))  # 前导空格 → 前缀不符
        self.assertIsNone(rc.detect_token_problem("rdak_live_ok"))
        self.assertIsNone(rc.detect_token_problem("rdak_test_ok"))

    def test_parse_kvs_typed_values(self):
        sys.path.insert(0, SCRIPTS)
        import mcp_call
        self.assertEqual(mcp_call.parse_kvs(["a=1", "b=true", "c=2026-10-18", "d=x=y"]),
                         {"a": 1, "b": True, "c": "2026-10-18", "d": "x=y"})
        with self.assertRaises(SystemExit):
            mcp_call.parse_kvs(["noequals"])

    # ---- 环境切换 / 令牌环境一致性 ----

    def test_base_url_defaults_to_prod(self):
        args = SimpleNamespace(env="prod", base_url=None, url=None)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(rc.BASE_URL_ENV, None)
            os.environ.pop(rc.SANDBOX_BASE_ENV, None)
            self.assertEqual(rc.resolve_base_url(args), rc.PROD_BASE)

    def test_base_url_env_override(self):
        args = SimpleNamespace(env="prod", base_url=None, url=None)
        with mock.patch.dict(os.environ, {rc.BASE_URL_ENV: "https://example.test/"}):
            self.assertEqual(rc.resolve_base_url(args), "https://example.test")

    def test_base_url_flag_beats_env(self):
        args = SimpleNamespace(env="prod", base_url="https://flag.test/", url=None)
        with mock.patch.dict(os.environ, {rc.BASE_URL_ENV: "https://env.test"}):
            self.assertEqual(rc.resolve_base_url(args), "https://flag.test")

    def test_sandbox_requires_explicit_host(self):
        args = SimpleNamespace(env="sandbox", base_url=None, url=None)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(rc.BASE_URL_ENV, None)
            os.environ.pop(rc.SANDBOX_BASE_ENV, None)
            with self.assertRaises(SystemExit):
                rc.resolve_base_url(args)
        with mock.patch.dict(os.environ, {rc.SANDBOX_BASE_ENV: "https://sb.test"}):
            self.assertEqual(rc.resolve_base_url(args), "https://sb.test")

    def test_endpoint_url_paths_and_override(self):
        args = SimpleNamespace(env="prod", base_url=None, url=None)
        self.assertEqual(rc.endpoint_url(args, "mcp"), rc.PROD_BASE + "/open/v1/mcp")
        self.assertEqual(rc.endpoint_url(args, "code"), rc.PROD_BASE + "/open/v1/mcp/code")
        # --url 是完整端点覆盖，测试注入用
        args2 = SimpleNamespace(env="prod", base_url=None, url="http://127.0.0.1:1/mcp")
        self.assertEqual(rc.endpoint_url(args2, "code"), "http://127.0.0.1:1/mcp")

    def test_check_token_env(self):
        self.assertIn("40302", rc.check_token_env("prod", "rdak_test_x"))
        self.assertIn("sandbox", rc.check_token_env("sandbox", "rdak_live_x"))
        self.assertIsNone(rc.check_token_env("prod", "rdak_live_x"))
        self.assertIsNone(rc.check_token_env("sandbox", "rdak_test_x"))

    # ---- 凭据文件兜底 ----

    def test_load_credentials_file(self):
        p = os.path.join(tempfile.gettempdir(), "rideclaw-creds-unit.env")
        with open(p, "w", encoding="utf-8") as f:
            f.write('# 注释\n\nRIDECLAW_TOKEN=rdak_live_filetoken\nQ="quoted"\nbadline\n')
        d = rc.load_credentials_file(p)
        self.assertEqual(d["RIDECLAW_TOKEN"], "rdak_live_filetoken")
        self.assertEqual(d["Q"], "quoted")
        self.assertNotIn("badline", d)
        self.assertEqual(rc.load_credentials_file(p + ".missing"), {})

    def test_token_falls_back_to_credentials_file(self):
        p = os.path.join(tempfile.gettempdir(), "rideclaw-creds-unit2.env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("RIDECLAW_TOKEN=rdak_live_fromfile\n")
        rc.CREDENTIALS_FILE = p
        args = SimpleNamespace(token=None, env="prod")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RIDECLAW_TOKEN", None)
            self.assertEqual(rc.get_token(args), "rdak_live_fromfile")


class MockHandler(BaseHTTPRequestHandler):
    """按请求顺序消费预设响应队列（FakeServerTest.responses），与路径无关。"""

    def log_message(self, *a):  # 静音
        pass

    def do_POST(self):
        spec = FakeServerTest.responses.pop(0)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        FakeServerTest.requests.append(json.loads(body) if body else None)
        status = spec.get("status", 200)
        payload = spec["body"]
        data = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeServerTest(unittest.TestCase):
    """起一个 mock 端点，直接调 rpc_once / 子进程跑脚本。"""

    responses = []
    requests = []
    server = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    @classmethod
    def rpc_caller(cls, response_body, status=200):
        """把 mock 响应塞进队列后调用 rpc_once。"""
        cls.responses.append({"status": status, "body": response_body})
        return rc.rpc_once(f"{cls.base_url}/mcp", "rdak_live_dummy",
                           "tools/call", {"name": "x", "arguments": {}})

    # ---- rpc_once 分层归一化 ----

    def test_rpc_error_normalized(self):
        outcome = self.rpc_caller({"jsonrpc": "2.0", "id": 1,
                                   "error": {"code": -32601, "message": "方法不存在"}})
        self.assertEqual(outcome.kind, "rpc_error")
        self.assertEqual(outcome.data["code"], -32601)
        self.assertIn("-32601", rc.describe_outcome(outcome))

    def test_describe_has_request_id(self):
        outcome = rc.RpcOutcome("api_error", {"code": 40303, "message": "IP 不在白名单"},
                                http_status=403, request_id="req-123")
        desc = rc.describe_outcome(outcome)
        self.assertIn("40303", desc)
        self.assertIn("request_id=req-123", desc)
        self.assertIn("白名单", desc)

    def test_ok_with_text_and_structured(self):
        r = self.rpc_caller({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": '{"a":1}'}],
            "structuredContent": {"b": 2}, "isError": False}})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["structuredContent"], {"b": 2})

    def test_tool_error_and_empty_content(self):
        # content: [] 不再 IndexError
        r = self.rpc_caller({"jsonrpc": "2.0", "id": 1,
                             "result": {"content": [], "isError": True}})
        self.assertEqual(r.kind, "tool_error")
        self.assertEqual(r.data["message"], "")

    def test_api_error_http401_with_envelope(self):
        r = self.rpc_caller({"code": 40112, "message": "Bearer 令牌无效",
                             "data": None, "request_id": "rid-1"}, status=401)
        self.assertEqual(r.kind, "api_error")
        self.assertEqual(r.request_id, "rid-1")
        self.assertIn("40112", rc.describe_outcome(r))

    def test_api_error_http200_envelope(self):
        # 官方：40201/40202/50401 以 HTTP 200 + code 信封返回
        r = self.rpc_caller({"code": 40202, "message": "请求参数缺失",
                             "data": None, "request_id": "rid-2"}, status=200)
        self.assertEqual(r.kind, "api_error")
        self.assertIn("40202", rc.describe_outcome(r))

    def test_non_json_response(self):
        r = self.rpc_caller("<html>502 Bad Gateway</html>", status=502)
        self.assertEqual(r.kind, "api_error")  # 非 JSON 的 HTTPError 也归 api_error
        self.assertIn("502", rc.describe_outcome(r))

    def test_retryable_classification(self):
        r429 = self.rpc_caller({"code": 42901, "message": "触发 QPS 上限",
                                "data": None, "request_id": "r"}, status=429)
        self.assertTrue(rc.is_retryable(r429))
        r403 = self.rpc_caller({"code": 40303, "message": "IP 不在白名单",
                                "data": None, "request_id": "r"}, status=403)
        self.assertFalse(rc.is_retryable(r403))

    # ---- 子进程端到端（真实脚本 + 真实 argv/env 路径）----

    def run_script(self, script, args, token="rdak_live_dummy"):
        env = dict(os.environ, RIDECLAW_TOKEN=token, PYTHONPATH=SCRIPTS)
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, script)] + args,
            capture_output=True, text=True, env=env, timeout=60)

    def test_e2e_call_success(self):
        self.responses.append({"status": 200, "body": {
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": '{"flights":[1,2,3]}'}]}}})
        p = self.run_script("mcp_call.py",
                            ["call", "flight_search", '{"trip_mode":"domestic"}',
                             "--no-retry", "--timeout", "5",
                             "--url", f"{self.base_url}/mcp"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('"flights"', p.stdout)

    def test_e2e_401_tool_error_exit4(self):
        self.responses.append({"status": 401, "body": {
            "code": 40112, "message": "Bearer 令牌无效", "data": None,
            "request_id": "rid-e2e"}})
        p = self.run_script("mcp_call.py",
                            ["call", "flight_search", "{}", "--no-retry",
                             "--url", f"{self.base_url}/mcp"])
        self.assertEqual(p.returncode, 4)
        self.assertIn("40112", p.stderr)
        self.assertIn("rid-e2e", p.stderr)
        self.assertEqual(p.stdout, "")

    def test_e2e_tool_error_exit3(self):
        self.responses.append({"status": 200, "body": {
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text",
                                    "text": "flight_search 参数错误: trip_mode 必填"}],
                       "isError": True}}})
        p = self.run_script("mcp_call.py",
                            ["call", "flight_search", "{}", "--no-retry",
                             "--url", f"{self.base_url}/mcp"])
        self.assertEqual(p.returncode, 3)
        self.assertIn("trip_mode", p.stderr)

    def test_e2e_429_retries_then_success(self):
        # 第 1 次 429，第 2 次成功；backoff=0.05 快速跑完
        self.responses.append({"status": 429, "body": {
            "code": 42901, "message": "触发 QPS 上限", "data": None, "request_id": "r1"}})
        self.responses.append({"status": 200, "body": {
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": '{"ok":true}'}]}}})
        p = self.run_script("mcp_call.py",
                            ["call", "flight_search", "{}", "--retry-backoff", "0.05",
                             "--url", f"{self.base_url}/mcp"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("第 2 次尝试", p.stderr)
        self.assertEqual(len(self.requests[-2:]), 2)

    def test_e2e_token_masked_in_error(self):
        # 服务端把 Token 回显进 message → 输出必须被掩码
        self.responses.append({"status": 401, "body": {
            "code": 40111, "message": "rdak_live_dummy 非法", "data": None,
            "request_id": "r"}})
        p = self.run_script("mcp_call.py",
                            ["call", "x", "{}", "--no-retry",
                             "--url", f"{self.base_url}/mcp"],
                            token="rdak_live_dummy")
        self.assertEqual(p.returncode, 4)
        self.assertNotIn("rdak_live_dummy", p.stdout + p.stderr)

    def test_e2e_bad_token_fails_fast(self):
        n_before = len(self.requests)
        p = self.run_script("mcp_call.py", ["list", "--no-retry"], token="not-a-token")
        self.assertEqual(p.returncode, 2)
        self.assertIn("前缀", p.stderr)
        self.assertEqual(len(self.requests), n_before)  # 无新增请求

    def test_e2e_sandbox_token_on_prod_fails_fast(self):
        """rdak_test_ 令牌打生产环境：本地就拦掉，不发请求（否则只会拿到 40302）。"""
        n_before = len(self.requests)
        p = self.run_script("mcp_call.py", ["list", "--no-retry"], token="rdak_test_abc")
        self.assertEqual(p.returncode, 2)
        self.assertIn("40302", p.stderr)
        self.assertIn("--env sandbox", p.stderr)
        self.assertEqual(len(self.requests), n_before)

    def test_e2e_describe_brief(self):
        self.responses.append({"status": 200, "body": {
            "jsonrpc": "2.0", "id": 1, "result": {"tools": [{
                "name": "flight_search",
                "description": "搜索航班",
                "inputSchema": {"type": "object",
                                "properties": {"trip_mode": {}, "from_code": {},
                                               "to_code": {}},
                                "required": ["trip_mode", "from_code"]}}]}}})
        p = self.run_script("mcp_call.py",
                            ["describe", "flight_search", "--brief", "--no-retry",
                             "--url", f"{self.base_url}/mcp"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("必填: trip_mode, from_code", p.stdout)
        self.assertIn("可选: to_code", p.stdout)

    def test_e2e_code_mode_ok(self):
        self.responses.append({"status": 200, "body": {
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text",
                                    "text": '{"value":{"top3":[]},"tool_calls":1,"log":[]}'}]}}})
        p = self.run_script("code_mode.py",
                            ["--code", "return 1;", "--no-retry",
                             "--url", f"{self.base_url}/mcp"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('"tool_calls": 1', p.stdout)

    def test_e2e_code_mode_sandbox_error(self):
        self.responses.append({"status": 200, "body": {
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text",
                                    "text": '{"error":"SyntaxError: Unexpected token","tool_calls":0}'}]}}})
        p = self.run_script("code_mode.py",
                            ["--code", "const x = {;", "--no-retry",
                             "--url", f"{self.base_url}/mcp"])
        self.assertEqual(p.returncode, 3)
        self.assertIn("沙箱脚本错误", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
