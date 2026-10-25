import base64
import hashlib
import json
import os
import re
import sys
import time

import requests
import urllib3
from Crypto.Cipher import AES

SCRIPT_VERSION = "2026-10-24-r3"
LOGIN_PAGE_PATH = "/cgi-bin/luci/"
LOGIN_PATH = "/cgi-bin/luci/api/auth"
DEVICE_KEY_PATTERN = re.compile(
    r'GibberishAES\.enc\(passwordEl\.value,\s*"([0-9a-fA-F]{32})"'
)


def openssl_key_iv(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16) -> tuple[bytes, bytes]:
    """Derive key and IV using OpenSSL's EVP_BytesToKey with MD5."""
    derived = b""
    target_len = key_len + iv_len
    while len(derived) < target_len:
        derived += hashlib.md5(derived[-16:] + password + salt).digest()
    return derived[:key_len], derived[key_len:target_len]


def aes_encrypt_openssl(plaintext: str, password: bytes, salt: bytes | None = None) -> str:
    salt = os.urandom(8) if salt is None else salt
    key, iv = openssl_key_iv(password, salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    raw = plaintext.encode("utf-8")
    pad_len = 16 - (len(raw) % 16)
    padded = raw + bytes([pad_len] * pad_len)
    enc = cipher.encrypt(padded)
    return base64.b64encode(b"Salted__" + salt + enc).decode()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def redact_auth_values(value):
    sensitive_keys = {"token", "sid", "sysauth"}
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in sensitive_keys else redact_auth_values(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_auth_values(item) for item in value]
    return value


def fetch_device_key(sess: requests.Session, eg_url: str, verify_tls: bool, timeout: float) -> bytes:
    """Fetch the login page and extract the one-time encryption key."""
    page_url = f"{eg_url}{LOGIN_PAGE_PATH}"
    resp = sess.get(page_url, verify=verify_tls, timeout=timeout)
    resp.raise_for_status()
    match = DEVICE_KEY_PATTERN.search(resp.text)
    if not match:
        raise ValueError("未能在登录页中找到 GibberishAES 密钥")
    return match.group(1).encode("ascii")


def test_login() -> int:
    eg_url = os.getenv("EG_URL", "").strip().rstrip("/")
    username = os.getenv("EG_USERNAME", "admin").strip()
    plain_pass = os.getenv("EG_PASSWORD", "")
    verify_tls = env_bool("EG_VERIFY_TLS", False)

    if not eg_url or not plain_pass:
        print("❌ 缺少配置：请在 login.env 中设置 EG_URL 和 EG_PASSWORD。")
        return 2

    try:
        timeout = float(os.getenv("EG_TIMEOUT", "8"))
        if timeout <= 0:
            raise ValueError
    except ValueError:
        print("❌ EG_TIMEOUT 必须是大于 0 的数字。")
        return 2

    print("=== 脚本版本 ===")
    print(SCRIPT_VERSION)

    if not verify_tls:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    sess = requests.Session()
    try:
        device_key = fetch_device_key(sess, eg_url, verify_tls, timeout)
    except (requests.RequestException, ValueError) as exc:
        print(f"❌ 获取设备登录密钥失败：{exc}")
        return 1

    print("=== 动态密钥指纹 ===")
    print(device_key[:8].decode("ascii"))

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

    try:
        resp = sess.post(
            f"{eg_url}{LOGIN_PATH}",
            json=payload,
            verify=verify_tls,
            timeout=timeout,
            headers={
                "Referer": f"{eg_url}{LOGIN_PAGE_PATH}",
                "Origin": eg_url,
            },
        )
    except requests.RequestException as exc:
        print(f"❌ 请求异常：{exc}")
        return 1

    print("=== 响应状态码 ===")
    print(resp.status_code)

    try:
        result = resp.json()
    except ValueError:
        print("=== 响应正文 ===")
        print(resp.text)
        result = {}
    else:
        print("=== 响应摘要（认证值已隐藏）===")
        print(json.dumps(redact_auth_values(result), ensure_ascii=False))

    print("=== Cookie 名称（不显示具体值）===")
    print(", ".join(sess.cookies.keys()) or "无")

    auth_cookie = sess.cookies.get("sysauth")
    response_sid = ""
    data = result.get("data")
    if isinstance(data, dict):
        response_sid = str(data.get("sid") or "")

    if resp.status_code == 200 and (auth_cookie or response_sid):
        auth_type = "sysauth Cookie" if auth_cookie else "响应中的 sid"
        print(f"\n✅ 登录成功，已获取 {auth_type}（未显示具体值）。")
        return 0

    print("\n❌ 登录失败：响应异常或未获取认证标识。")
    return 1


if __name__ == "__main__":
    sys.exit(test_login())
