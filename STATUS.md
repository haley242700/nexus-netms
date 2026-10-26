# STATUS.md — 项目状态

> 基于当前代码与仓库状态生成（2026-10-27）。历史背景补充见 DECISIONS.md。

## 一、已完成

| 功能 | 文件路径 | 验证方式 |
|---|---|---|
| 睿易后台自动登录（设备密钥 AES 加密） | `apps/speedtest-ap/test.py`、`reyee_session.py` | NAS login-test 容器实测通过 |
| 只读终端-AP 反查客户端（缓存 + 自动重登） | `apps/speedtest-ap/ap_lookup.py` | `tests/test_ap_lookup.py` |
| NEXUS 总览页（网关/AP/终端遥测、WAN 粒子流场、双健康度圆环、AP 矩阵） | `apps/nexus/network-dashboard/index.html`、`app.js`、`flow-field.js` | `tools/verification/` 生产只读验证 |
| 事件统计页（漫游、离线异常、原因分布、证据链） | `events.html`、`events.js` + `apps/nexus/reyee-exporter/event_store.py` | `tests/test_event_store_v1.py`、`test_dashboard_events_api.py`、`test_event_migration.py` |
| 测速页（LibreSpeed 内嵌 + AP 上下文 + 有线/无线评分 + 同组合历史百分位可视化） | `speedtest.html`、`speedtest-app.js`、`speedtest_analysis.py` | `tests/test_speedtest_analysis.py`、`test_speedtest_integration.py`、`test_speedtest_page.js` |
| 无刷新页面导航（预取 + ETag + 脚本模块作用域） | `navigation.js` | `tests/test_dashboard_pagination.js`、`test_dashboard_throughput.js` |
| Prometheus 指标采集（ap/sta/流量/系统日志） | `apps/nexus/reyee-exporter/reyee_exporter.py` | `:9108/metrics` 生产在线 |
| 统一管理入口（测试/打包/验证/目录树，含分模块计时） | `manage.py` | `python manage.py test` 16 模块全绿 |
| NAS 浏览器开发环境 + 一键部署 | `apps/dev-workspace/`（code-server :8443、`deploy-nexus.sh`） | NAS 容器在线 |
| Kimi Code 桌面端工作区迁移、Git/Node 安装包与脚本 | `tools/install-git.bat`、`install-node.bat` 等 | 工作区 `D:\nexus-netms` 已跑通测试 |

## 二、进行中

| 事项 | 状态 | 相关文件 |
|---|---|---|
| 电视（.28）VPN（小黄JS 智能分流）治理 WAN 会话超限 | VPN 已于 2026-10-26 20:31 连接；观察期中，限流 249 未撤 | `artifacts/tv-vpn-effectiveness-20261026.md` |
| VPN 前后电视连接数对比 | **数据缺口**：云端趋势因限流停止统计，网关无单 IP 实时连接数接口（`ipConnlimitRes` 拿不到）；待用户在睿易 APP 截图补充 | 见 DECISIONS.md「踩坑」 |

## 三、已知问题

1. **电视连接数 VPN 后测不到**（结构性）：见上。两条路：睿易 APP 电视详情页截图，或撤 249 限流等云端重新累积。
2. **Mac/移动端看板布局**已做过响应式适配，但仅在用户手机实测过一次（圆环模块显示问题已修），更多机型未验证。
3. `speedtest_analysis.py` 的评分锚点（`SCORE_ANCHORS`）是按用户家 WiFi 6 / 全 2.5G 环境标的，换环境需重标。
4. 事件库长期增长未验证：events.db 目前只保留项目启动以来的数据，无归档/清理机制（`event_store.py` 无 TTL 逻辑）。
5. GitHub 推送依赖 VPN 代理 7892，VPN 关闭时不可推送（非代码问题，属环境约束）。

## 四、尚未验证

- 撤掉限流 249 后 WAN 会话是否稳定在正常水位（待观察期结束后由用户决策验证）。
- AdGuard Home 若接入网络对全屋 DNS 的影响（组件待命，未接入，见下）。
- 十万级事件量下的看板 API 响应（`tests/nexus_scale_test.py` 用合成数据验证过查询逻辑，生产真实增长曲线未验证）。
- 网关 WAN 口真实协商速率在有线测速时的展示（`speedtest-app.js` 的网口速率逻辑）——曾在此卡住中断，恢复后用户未再追验。

## 五、下一步任务

1. **[等待用户]** 观察 2-3 天（重点夜间待机）后决策是否撤限流 249 → 然后验证任务 四-1。
2. **[等待用户]** AdGuard Home 去留决策（组件已部署在 NAS :3003，未接入网络；若接入需设计网关统一下发备用 DNS 的兜底）。
3. **[等待用户]** 电视 VPN 后连接数补数据（APP 截图）。
4. 事件库增长策略（归档或 TTL），涉及 `event_store.py` + 部署目录 `events/`。
5. 未提交文件：`tools/` 下 Git/Node 安装包（.exe/.msi/.bat，未跟踪）待用户决定是否入库或移入 artifacts。
