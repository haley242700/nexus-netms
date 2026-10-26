"""睿易终端上下文：无线 AP、有线交换机与未知上游的离线测试。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "speedtest-ap"))
from ap_lookup import ReyeeClient


class FakeReyeeClient(ReyeeClient):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _cmd(self, module, data=None):
        self.calls.append((module, data))
        if module == "sta_list":
            return {"list": [{
                "userIp": "192.168.110.57", "mac": "86:FF:81:81:B5:BE",
                "hostName": "iPhone", "deviceAliasName": "一楼主卧AP",
                "sn": "AP-SN", "ssid": "Ubiquiti", "band": "5 GHz",
            }]}
        if module == "user_list":
            assert data == {"devType": "all", "dataType": "timely"}
            return {"list": [
                {"userIp": "192.168.110.27", "mac": "34:5A:60:72:33:EE", "hostName": "PC", "connectType": "wire", "sn": "G1V61MP005183"},
                {"userIp": "192.168.110.54", "mac": "98:6E:E8:23:DF:5A", "hostName": "NAS", "connectType": "wire", "sn": "G1UC12T002343"},
                {"userIp": "192.168.110.12", "mac": "78:45:58:70:0E:50", "hostName": "其他AP", "connectType": "wire", "sn": "GATEWAY-SN"},
            ]}
        if module == "local_topology":
            assert data == {"fromcache": "true", "caller": "web"}
            return {"topo": {"deviceType": "EGW", "children": [
                {"deviceType": "SW", "deviceSn": "G1V61MP005183", "productClass": "RG-ES209MG-P", "manageIp": "192.168.110.16", "children": []},
                {"deviceType": "SW", "deviceSn": "G1UC12T002343", "productClass": "RG-ES209MG", "manageIp": "192.168.110.6", "children": []},
            ]}}
        raise AssertionError(module)


client = FakeReyeeClient()
wireless = client.lookup_by_ip("192.168.110.57")
assert wireless["apName"] == "一楼主卧AP" and wireless["band"] == "5 GHz"

pc = client.lookup_by_ip("192.168.110.27")
assert pc["connected"] and pc["clientMac"] == "34:5A:60:72:33:EE"
assert pc["switchName"] == "ES209MG-P · 192.168.110.16"
assert pc["switchSn"] == "G1V61MP005183"

nas = client.lookup_by_ip("192.168.110.54")
assert nas["switchName"] == "ES209MG · 192.168.110.6"
assert nas["switchSn"] == "G1UC12T002343"
assert pc["switchSn"] != nas["switchSn"], "同名交换机不得合并"

unknown = client.lookup_by_ip("192.168.110.12")
assert unknown["connected"] and "switchSn" not in unknown
assert client.lookup_by_ip("192.168.110.200")["connected"] is False
assert len([call for call in client.calls if call[0] == "local_topology"]) == 1, "拓扑应使用缓存"

print("睿易上下文验证通过：无线 AP、两台同名有线交换机及未知上游均按真实 SN 区分。")
