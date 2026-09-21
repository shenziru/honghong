#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jev_proxy.py —— 「她说 · Her Mood」本地 CORS 代理（零依赖，仅用 Python 标准库）

为什么需要它：
    官方 api.typesafe.ai 不返回 Access-Control-Allow-Origin，
    浏览器直接 fetch 时 OPTIONS 预检会被拒（表现为 "Failed to fetch"）。
    本脚本在本机起一个允许跨域的中转：浏览器 -> 本代理 -> 官方 API。
    你的 API Key 只是经本机转发给官方，不会被记录或上传到别处。

用法：
    python jev_proxy.py                 # 默认端口 8010
    python jev_proxy.py --port 9000     # 自定义端口

然后在游戏「配置问题与答案 -> 连接」里：
    判决引擎：真实 Jev API
    API 端点：填本脚本启动时打印的地址（例如 http://127.0.0.1:8010）
    API Key ：你的 ts_... 密钥
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM_BASE = "https://api.typesafe.ai"
DEFAULT_PATH = "/v1/systemone"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
    "Access-Control-Max-Age": "86400",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "JevLocalProxy/1.0"

    # ---------- helpers ----------
    def _reply(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[jev_proxy] %s\n" % (fmt % args))

    # ---------- routes ----------
    def do_GET(self):
        # 健康检查：浏览器直接打开代理地址可看到这段说明
        msg = ("jev_proxy 运行中。\n"
               "请把游戏配置里的 API 端点填为本服务地址，"
               "游戏会以 POST 方式经这里转发到官方 API。\n").encode("utf-8")
        self._reply(200, msg)

    def do_OPTIONS(self):
        # 关键：官方不回应 CORS 预检，这里代答 204 + 允许跨域头
        self._reply(204)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        payload = self.rfile.read(length) if length else b"{}"
        auth = self.headers.get("Authorization", "")

        # 若请求路径形如 /v1/... 则透传路径，否则落到默认的 /v1/systemone
        path = self.path if self.path.startswith("/v1/") else DEFAULT_PATH
        url = UPSTREAM_BASE + path

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if auth:
            req.add_header("Authorization", auth)

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                self._reply(resp.status, data, "application/json")
        except urllib.error.HTTPError as e:
            # 官方返回的业务错误（401/403/422 等）原样透传，方便游戏面板诊断
            data = e.read() or b""
            self._reply(e.code, data, "application/json")
        except Exception as e:  # 网络/超时等
            body = json.dumps(
                {"error": "proxy upstream failure", "detail": str(e)},
                ensure_ascii=False,
            ).encode("utf-8")
            self._reply(502, body, "application/json")


def main():
    ap = argparse.ArgumentParser(description="Jev 本地 CORS 代理（零依赖）")
    ap.add_argument("--port", type=int, default=8010, help="监听端口，默认 8010")
    args = ap.parse_args()

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("=" * 58)
    print("jev_proxy 已启动（仅监听本机，转发到 %s）" % (UPSTREAM_BASE + DEFAULT_PATH))
    print("在游戏配置里，把 API 端点填为： http://127.0.0.1:%d" % args.port)
    print("按 Ctrl+C 停止")
    print("=" * 58)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
