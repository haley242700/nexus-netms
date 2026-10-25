"""锐捷睿易终端-AP 关联查询。

登录管理后台，调用只读接口 devSta.get/sta_list，
根据客户端 IP 反查其连接的 AP 名称、SSID、频段、信号等信息。

凭据从环境变量读取，绝不打印密码 / token / sid。
"""
import os
import threading
import time

import requests
import urllib3

from test import aes_encrypt_openssl, fetch_device_key

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

STA_LIST_TTL = 15  # 终端列表缓存秒数


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _clean(value) -> str:
    """把锐捷返回的占位值（NULL/undefined 等）视为空字符串。"""
    value = str(value or "").strip()
    return "" if value.upper() in {"NULL", "UNDEFINED", "NONE"} else value


class ReyeeClient:
    """带会话缓存与自动重登的锐捷睿易客户端（只读）。"""

    def __init__(self) -> None:
        self.eg_url = _env("EG_URL").rstrip("/")
        self.username = _env("EG_USERNAME", "admin")
        self.password = _env("EG_PASSWORD")
        self.timeout = float(_env("EG_TIMEOUT", "8") or 8)
        self._sess: requests.Session | None = None
        self._sta_list: list[dict] = []
        self._sta_list_at = 0.0
        self._lock = threading.Lock()

    def ready(self) -> bool:
        return bool(self.eg_url and self.password)

    def _login(self) -> None:
        sess = requests.Session()
        device_key = fetch_device_key(sess, self.eg_url, False, self.timeout)
        payload = {
            "method": "login",
            "params": {
                "username": self.username,
                "time": str(int(time.time())),
                "encry": True,
                "pwd": aes_encrypt_openssl(self.password, device_key),
                "isCheckReadAgreement": "true",
            },
        }
        resp = sess.post(
            f"{self.eg_url}/cgi-bin/luci/api/auth",
            json=payload,
            verify=False,
            timeout=self.timeout,
            headers={
                "Referer": f"{self.eg_url}/cgi-bin/luci/",
                "Origin": self.eg_url,
            },
        )
        result = resp.json()
        data = result.get("data") or {}
        sid = data.get("sid") or sess.cookies.get("sysauth")
        if not sid:
            raise RuntimeError("登录失败：未获取 sid")
        self._sess = sess
        self._sid = str(sid)

    def _ensure_session(self) -> None:
        if self._sess is None:
            self._login()

    def _cmd(self, module: str) -> dict:
        """调用只读 devSta.get，认证失效时自动重登一次。"""
        self._ensure_session()
        body = {"method": "devSta.get", "params": {"module": module}}
        for attempt in range(2):
            try:
                resp = self._sess.post(
                    f"{self.eg_url}/cgi-bin/luci/api/cmd?auth={self._sid}",
                    json=body,
                    verify=False,
                    timeout=self.timeout,
                    headers={
                        "Referer": f"{self.eg_url}/cgi-bin/luci/",
                        "Origin": self.eg_url,
                    },
                )
                result = resp.json()
            except (requests.RequestException, ValueError):
                self._sess = None
                self._login()
                continue
            if result.get("code") == 0:
                return result.get("data") or {}
            # 认证类错误：重登一次再试
            self._sess = None
            self._login()
        raise RuntimeError(f"查询模块 {module} 失败")

    def get_sta_list(self) -> list[dict]:
        with self._lock:
            if time.time() - self._sta_list_at < STA_LIST_TTL:
                return self._sta_list
            data = self._cmd("sta_list")
            self._sta_list = list(data.get("list") or [])
            self._sta_list_at = time.time()
            return self._sta_list

    def lookup_by_ip(self, ip: str) -> dict:
        """根据客户端 IP 反查 AP 信息。

        返回 {"connected": bool, ...}；connected=False 表示不在无线终端列表
        （可能是有线设备或未接入本网络）。
        """
        ip = (ip or "").strip()
        if not ip:
            return {"connected": False, "note": "缺少 IP 参数"}
        for sta in self.get_sta_list():
            if (sta.get("userIp") or "") == ip:
                return {
                    "connected": True,
                    "clientIp": ip,
                    "clientMac": _clean(sta.get("mac")),
                    "hostName": _clean(sta.get("hostName")),
                    "apName": _clean(sta.get("deviceAliasName")) or _clean(sta.get("sn")),
                    "apSn": _clean(sta.get("sn")),
                    "ssid": _clean(sta.get("ssid")),
                    "band": _clean(sta.get("band")),
                    "channel": _clean(sta.get("channel")),
                    "rssi": _clean(sta.get("rssi")),
                    "rxRate": _clean(sta.get("rxrate")),
                    "onlineTime": _clean(sta.get("onlineTime")),
                }
        return {"connected": False, "clientIp": ip, "note": "不在无线终端列表中（有线设备或未接入本网络）"}
