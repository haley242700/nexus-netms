"""测速评分、组合隔离、历史分位和样本门槛的离线测试。"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "nexus" / "network-dashboard"))
from speedtest_analysis import percentile, record_and_analyze, score_metric

for access_type in ("wired", "wireless"):
    assert score_metric("download", 100, access_type) == 60
    assert score_metric("download", 300, access_type) == 80
    assert score_metric("download", 500, access_type) == 90
    assert score_metric("download", 1000, access_type) == 95
    assert score_metric("ping", 150, access_type) == 0
    assert score_metric("jitter", 5, access_type) == 80
assert score_metric("download", 2500, "wired") == 100
assert score_metric("download", 2401, "wireless") == 100
assert score_metric("download", 2401, "wired") < 100
assert score_metric("ping", 3, "wired") == 100
assert score_metric("ping", 5, "wireless") == 100
assert score_metric("ping", 10, "wireless") == 95
assert score_metric("ping", 20, "wireless") == 85
assert score_metric("ping", 30, "wireless") == 70
assert score_metric("ping", 10, "wired") == 85
assert percentile([0, 10], 50) == 5
assert percentile([1, 2, 3, 4, 5], 20) == 1.8

wireless = {
    "connected": True, "clientIp": "192.168.110.57", "clientMac": "86:FF:81:81:B5:BE",
    "hostName": "iPhone", "apName": "负一卧室AP", "band": "5 GHz", "ssid": "Ubiquiti",
}
wired = {
    "connected": True, "clientIp": "192.168.110.50", "clientMac": "AA:BB:CC:DD:EE:FF",
    "hostName": "PC", "apName": "负一电脑房AP", "band": "", "ssid": "",
}
mapped_wired = {
    **wired,
    "switchName": "ES209MG-P · 192.168.110.16",
    "switchModel": "RG-ES209MG-P",
    "switchIp": "192.168.110.16",
    "switchSn": "G1V61MP005183",
}
with tempfile.TemporaryDirectory(dir=ROOT / "artifacts" / "tmp") as tmp:
    path = str(Path(tmp) / "speedtest.db")
    first = record_and_analyze(path, {"download": 100, "upload": 10, "ping": 1, "jitter": 1}, wireless, "我的手机", "192.168.110.1")
    assert first["saved"] and first["identity"]["connectionDevice"] == "负一卧室AP"
    assert first["identity"]["clientKey"] == "86:ff:81:81:b5:be"
    assert first["scores"]["accessType"] == "wireless"
    assert first["analysis"]["needed"] == 4 and "percentiles" not in first["analysis"]["metrics"]["download"]

    for index in range(2, 6):
        result = record_and_analyze(path, {"download": index * 100, "upload": index * 10, "ping": index, "jitter": index / 2}, wireless, "我的手机", "192.168.110.1")
    assert result["analysis"]["sampleSize"] == 5
    assert not result["analysis"]["reliable"]
    download = result["analysis"]["metrics"]["download"]
    assert download["percentiles"]["50"] == 300
    assert download["percentiles"]["1"] == 104
    assert download["percentiles"]["99"] == 496
    assert download["superiority"] == 90
    assert result["analysis"]["metrics"]["ping"]["superiority"] == 10
    assert result["scores"]["overall"] > 0 and result["scores"]["grade"]

    other = record_and_analyze(path, {"download": 999, "upload": 99, "ping": 9, "jitter": 9}, wired, "书房电脑", "192.168.110.1")
    assert other["identity"]["accessType"] == "wired"
    assert other["identity"]["connectionDevice"] == "未识别交换机"
    assert other["analysis"]["sampleSize"] == 1, "不同终端和接入组合不得混合历史"

    mapped = record_and_analyze(path, {"download": 888, "upload": 88, "ping": 2, "jitter": 1}, mapped_wired, "书房电脑", "192.168.110.1")
    assert mapped["identity"]["connectionDevice"] == "ES209MG-P · 192.168.110.16"
    assert "switch:G1V61MP005183" in mapped["identity"]["comboKey"]
    assert mapped["context"]["switchSn"] == "G1V61MP005183"
    assert mapped["analysis"]["sampleSize"] == 1, "未识别与已识别交换机的历史不得混合"
    moved_ip = record_and_analyze(path, {"download": 777, "upload": 77, "ping": 2, "jitter": 1}, {**mapped_wired, "switchIp": "192.168.110.99"}, "书房电脑", "192.168.110.1")
    assert moved_ip["analysis"]["sampleSize"] == 2, "交换机 IP 变化不得拆散同一 SN 的历史"

print("测速分析验证通过：评分、分位、组合隔离及交换机 SN 稳定标识均正确。")
