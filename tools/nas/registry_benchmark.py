"""Benchmark identical Docker Hub blob downloads; run on the NAS."""
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "codercom/code-server"
BLOB = "sha256:3193b76d4c10c0cc894faabc27f23fd5569f7dde82387537206353b28506fbee"
MAX_BYTES = 16 * 1024 * 1024
MAX_SECONDS = 30


def request(url, token=None, range_header=False):
    headers = {"User-Agent": "SpeedTest-NAS-registry-benchmark/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if range_header:
        headers["Range"] = f"bytes=0-{MAX_BYTES - 1}"
    return urllib.request.Request(url, headers=headers)


def authenticate(challenge, credentials=None):
    match = re.match(r'Bearer\s+(.*)', challenge, re.I)
    if not match:
        raise RuntimeError("registry did not offer bearer authentication")
    params = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
    realm = params.pop("realm", None)
    if not realm:
        raise RuntimeError("authentication realm missing")
    params["scope"] = f"repository:{REPOSITORY}:pull"
    token_request = urllib.request.Request(realm + ("&" if "?" in realm else "?") + urllib.parse.urlencode(params))
    if credentials:
        basic = base64.b64encode(f"{credentials['username']}:{credentials['password']}".encode()).decode()
        token_request.add_header("Authorization", "Basic " + basic)
    with urllib.request.urlopen(token_request, timeout=10) as response:
        payload = json.load(response)
    return payload.get("token") or payload["access_token"]


def benchmark(base, credentials=None):
    url = f"{base}/v2/{REPOSITORY}/blobs/{BLOB}"
    token = None
    for attempt in range(2):
        try:
            response = urllib.request.urlopen(request(url, token, True), timeout=12)
            break
        except urllib.error.HTTPError as error:
            if error.code == 401 and attempt == 0:
                token = authenticate(error.headers.get("WWW-Authenticate", ""), credentials)
                continue
            raise RuntimeError(f"HTTP {error.code}") from error
    else:
        raise RuntimeError("authentication failed")
    if "json" in response.headers.get("Content-Type", ""):
        raise RuntimeError("registry returned JSON instead of an image blob")

    downloaded = 0
    started = time.monotonic()
    with response:
        while downloaded < MAX_BYTES:
            if time.monotonic() - started >= MAX_SECONDS:
                break
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            downloaded += len(chunk)
    elapsed = time.monotonic() - started
    return downloaded, elapsed


def main():
    sources = sys.argv[1:]
    credentials = None
    if sources and sources[0] == "--authenticated-stdin":
        credentials = json.load(sys.stdin)
        sources = sources[1:]
    for base in sources:
        base = base.rstrip("/")
        try:
            size, elapsed = benchmark(base, credentials)
            speed = size / elapsed / (1024 * 1024)
            print(json.dumps({"source": base, "bytes": size, "seconds": round(elapsed, 2), "MiB_s": round(speed, 2)}, ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({"source": base, "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
