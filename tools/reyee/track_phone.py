"""高频追踪指定终端的 AP 归属变化。只读，轮询网关 sta_list。"""
import json, sys, time, datetime
from tools.common import apply_env
from ap_lookup import ReyeeClient

TARGET = "7a:75:b3:ec:3c:73"  # 我的iPhone

apply_env("login.env")

c = ReyeeClient()
c._ensure_session()
print("start", datetime.datetime.now().strftime("%H:%M:%S"), flush=True)

last = None
deadline = time.time() + 280
while time.time() < deadline:
    try:
        stas = c.get_sta_list()
        me = next((s for s in stas if (s.get("mac") or "").lower() == TARGET), None)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        if me:
            cur = (me.get("sn"), me.get("rssi"), me.get("rate"), me.get("channel"))
            if cur != last:
                print(f"{now}  AP={me.get('deviceAliasName') or me.get('sn')}  rssi={me.get('rssi')}  rate={me.get('rate')}  ch={me.get('channel')}", flush=True)
                last = cur
        else:
            if last != "GONE":
                print(f"{now}  !! iPhone 不在线列表", flush=True)
                last = "GONE"
    except Exception as e:
        print(datetime.datetime.now().strftime("%H:%M:%S"), "ERR", repr(e)[:80], flush=True)
    time.sleep(3)
print("end", datetime.datetime.now().strftime("%H:%M:%S"), flush=True)
