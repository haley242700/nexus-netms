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
USER_LIST_TTL = 15
TOPOLOGY_TTL = 60


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
        self._user_list: list[dict] = []
        self._user_list_at = 0.0
        self._switches: dict[str, dict] = {}
        self._switches_at = 0.0
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

    def _cmd(self, module: str, data=None) -> dict:
        """调用只读 devSta.get，认证失效时自动重登一次。"""
        self._ensure_session()
        params = {"module": module}
        if data is not None:
            params["data"] = data
        body = {"method": "devSta.get", "params": params}
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

    def get_user_list(self) -> list[dict]:
        """读取全量终端；有线终端的 sn 是其真实上游设备 SN。"""
        with self._lock:
            if time.time() - self._user_list_at < USER_LIST_TTL:
                return self._user_list
            data = self._cmd("user_list", {"devType": "all", "dataType": "timely"})
            self._user_list = list(data.get("list") or [])
            self._user_list_at = time.time()
            return self._user_list

    def get_switches(self) -> dict[str, dict]:
        """从本地拓扑建立交换机 SN 索引，不把同名设备合并。"""
        with self._lock:
            if time.time() - self._switches_at < TOPOLOGY_TTL:
                return self._switches
            data = self._cmd("local_topology", {"fromcache": "true", "caller": "web"})
            switches = {}

            def walk(node):
                if _clean(node.get("deviceType")).upper() == "SW" and _clean(node.get("deviceSn")):
                    model = _clean(node.get("productClass"))
                    ip = _clean(node.get("manageIp"))
                    switches[_clean(node.get("deviceSn"))] = {
                        "switchName": " · ".join(part for part in (model.removeprefix("RG-"), ip) if part),
                        "switchModel": model,
                        "switchIp": ip,
                        "switchSn": _clean(node.get("deviceSn")),
                    }
                for child in node.get("children") or []:
                    walk(child)

            walk(data.get("topo") or {})
            self._switches = switches
            self._switches_at = time.time()
            return self._switches

    @staticmethod
    def _base_context(row, ip):
        return {
            "connected": True,
            "clientIp": ip,
            "clientMac": _clean(row.get("mac")),
            "hostName": _clean(row.get("hostName")),
        }

    def lookup_by_ip(self, ip: str) -> dict:
        """按 IP 反查无线 AP，或有线终端真实上游交换机。"""
        ip = (ip or "").strip()
        if not ip:
            return {"connected": False, "note": "缺少 IP 参数"}
        for sta in self.get_sta_list():
            if (sta.get("userIp") or "") == ip:
                return {
                    **self._base_context(sta, ip),
                    "apName": _clean(sta.get("deviceAliasName")) or _clean(sta.get("sn")),
                    "apSn": _clean(sta.get("sn")),
                    "ssid": _clean(sta.get("ssid")),
                    "band": _clean(sta.get("band")),
                    "channel": _clean(sta.get("channel")),
                    "rssi": _clean(sta.get("rssi")),
                    "rxRate": _clean(sta.get("rxrate")),
                    "onlineTime": _clean(sta.get("onlineTime")),
                }
        for user in self.get_user_list():
            if (user.get("userIp") or "") != ip or user.get("connectType") == "wireless":
                continue
            context = self._base_context(user, ip)
            switch = self.get_switches().get(_clean(user.get("sn")))
            if switch:
                context.update(switch)
            else:
                context["note"] = "有线终端的上游设备不是已识别交换机"
            return context
        return {"connected": False, "clientIp": ip, "note": "不在睿易在线终端列表中"}
