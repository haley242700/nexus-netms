"""锐捷睿易会话工具：登录并返回已认证的 requests.Session。

只负责登录，不负责任何业务调用。复用 test.py 的加密逻辑。
凭据从 login.env 读取，绝不打印。
"""
import os
import time

import requests
import urllib3

from test import aes_encrypt_openssl, fetch_device_key

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env(path: str = "login.env") -> dict:
    """解析简单的 KEY=VALUE env 文件（跳过注释和空行）。"""
    config = {}
    if not os.path.exists(path):
        return config
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip().strip('"').strip("'")
    return config


def login(cfg: dict | None = None) -> requests.Session:
    cfg = cfg or load_env()
    eg_url = cfg.get("EG_URL", "").strip().rstrip("/")
    username = cfg.get("EG_USERNAME", "admin").strip()
    plain_pass = cfg.get("EG_PASSWORD", "")
    if not eg_url or not plain_pass:
        raise RuntimeError("缺少 EG_URL / EG_PASSWORD")

    timeout = float(cfg.get("EG_TIMEOUT", "8") or 8)
    sess = requests.Session()
    device_key = fetch_device_key(sess, eg_url, False, timeout)
    payload = {
        "method": "login",
        "params": {
            "username": username,
            "time": str(int(time.time())),
            "encry": True,
            "pwd": aes_encrypt_openssl(plain_pass, device_key),
            "isCheckReadAgreement": "true",
        },
    }
    resp = sess.post(
        f"{eg_url}/cgi-bin/luci/api/auth",
        json=payload,
        verify=False,
        timeout=timeout,
        headers={"Referer": f"{eg_url}/cgi-bin/luci/", "Origin": eg_url},
    )
    result = resp.json()
    data = result.get("data") or {}
    sid = data.get("sid") or sess.cookies.get("sysauth")
    if not sid:
        raise RuntimeError(f"登录失败：{result}")
    sess.headers["X-Auth-Sid"] = str(sid)
    sess._eg_url = eg_url  # type: ignore[attr-defined]
    sess._sid = str(sid)  # type: ignore[attr-defined]
    return sess


def api_get(sess: requests.Session, path: str, params: dict | None = None) -> requests.Response:
    """带 auth 查询参数 GET 一个 luci api 路径。"""
    eg_url = sess._eg_url  # type: ignore[attr-defined]
    merged = {"auth": sess._sid}  # type: ignore[attr-defined]
    if params:
        merged.update(params)
    return sess.get(f"{eg_url}{path}", params=merged, verify=False, timeout=8)


def api_post(sess: requests.Session, path: str, body: dict) -> requests.Response:
    eg_url = sess._eg_url  # type: ignore[attr-defined]
    return sess.post(
        f"{eg_url}{path}?auth={sess._sid}",  # type: ignore[attr-defined]
        json=body,
        verify=False,
        timeout=8,
        headers={"Referer": f"{eg_url}/cgi-bin/luci/", "Origin": eg_url},
    )
