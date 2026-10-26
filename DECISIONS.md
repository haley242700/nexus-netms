# DECISIONS.md — 技术决策、否决方案与踩坑记录

> 生成于 2026-10-27。标注【代码可证】的可在所指文件中直接验证；标注【会话记录】的来自排障过程，未在代码中复验，引用前请留意。

## 一、重要技术决策及原因

1. **睿易一律只读**【代码可证：`reyee_exporter.py`、`ap_lookup.py` 文档串】
   全屋真实生产网络，任何写操作都不可接受。所有查询收敛到 `devSta.get` / `devConfig.get` 两个只读方法。

2. **只读客户端只保留一份实现**【代码可证：`tools/common.py` 注释】
   `apps/speedtest-ap/ap_lookup.py` 的 `ReyeeClient` 是唯一客户端；诊断工具经 `tools/common.py` 注入 sys.path 复用。
   避免多份登录/加密逻辑漂移（登录加密在 `test.py`：`fetch_device_key` + `aes_encrypt_openssl`）。

3. **事件库用 SQLite + WAL，单写多读**【代码可证：`event_store.py`、`dashboard_server.py`】
   采集线程独占一个连接写入；看板每次请求开独立只读连接（`mode=ro`）。表结构在线 ALTER 升级，不删历史事件。

4. **LibreSpeed 内嵌容器，经看板流式反向代理**【代码可证：`apps/nexus/docker-compose.yaml`、`dashboard_server.py` `proxy_speedtest`】
   不开放额外主机端口；注入 `X-Forwarded-For`/`X-Real-IP` 使引擎看到真实客户端 IP，AP 反查才能按访问者 IP 工作。

5. **测速成绩按「终端 × 有线/无线 × 连接设备 × 网关」组合历史百分位**【代码可证：`speedtest_analysis.py` `context_identity`】
   有线以交换机 SN 隔离历史（防换机串数据），无线以 AP 名。低优指标（延迟/抖动）统一转成「百分位越高越优秀」方向展示，避免图表逻辑分叉。

6. **评分锚点分有线/无线**【代码可证：`speedtest_analysis.py` `SCORE_ANCHORS`】
   无线 2401 Mbps 满分、有线 2500 Mbps 满分，延迟/抖动锚点无线放宽——按用户家 WiFi 6 + 全 2.5G 环境标定。

7. **页面 SPA 化用自研无刷新导航而非引入框架**【代码可证：`navigation.js`】
   fetch + DOMParser 换壳、`<script type="module">` 隔离作用域、`pointerenter` 预取、ETag 缓存，解决三页跳转慢的问题，零依赖零构建。

8. **Prometheus 数据卷保留旧名 `monitoring_prometheus_data`**【代码可证：compose `volumes`】
   项目从 SpeedTest 改名 nexus-netms 时不丢历史监控数据。

9. **部署包可重复生成且零密钥**【代码可证：`manage.py` `make_package`】
   打包时硬校验禁止 `.env`/`login.env`/`nas.env`/`cloud.env`/`htpasswd`/`.pkl`/`.b64` 进入 dist；真实配置永远留在 NAS 生产目录 `secrets/`。

10. **开发主阵地在 NAS code-server**【代码可证：`apps/dev-workspace/`】
    浏览器里开发、容器内跑测试、`deploy-nexus.sh` 一键部署；PC 只做诊断与打包。git 推送例外走 PC（NAS 访问 GitHub 受限）。

## 二、已否决的方案

1. **iperf3 作为测速引擎**【会话记录】浏览器无法原生跑 iperf3 协议，终端必须装客户端，违背「手机电脑零安装」目标。保留 LibreSpeed。
2. **AdGuard Home 仅为电视限流贸然接入全屋 DNS**【会话记录】风险收益不成比例，且兜底难做。AGH 目前待命未接入，是否做 NEXUS 第四页待用户决策。
3. **网关 VPN 分流被墙域名**【会话记录】EG 系列网关无可靠策略路由能力支撑该方案；改为在电视本机装 VPN 客户端（小黄JS，ClashMeta 内核，智能分流）。
4. **PC 端作为开发主力**【会话记录】环境漂移、路径混乱；已收敛到 NAS 容器开发，PC 仅保留诊断工具链。
5. **在睿易后台拉黑电视海外域名**【会话记录】域名列表无法从网关侧自动获取，手动维护不可持续；被 VPN 方案取代。

## 三、容易踩坑的地方（按血泪程度排序）

1. **EGW 新查询接口先查前端 JS 再调**【代码可证：`artifacts/research/reyee_admin_js/chunk-advanced.js`】
   连接数限制页面的真实模块名是 `ip_connlimit`（列表）/ `ipConnlimitRes`（每策略当前连接数），不是字面上的 ipconn/session_limit。
   判断方法用 `devConfig.get`；`devSta.get` 对 config 类模块返回 `illeagal parameter`。
   但注意：`ipConnlimitRes` 走 `devConfig.get`/`devSta.get` 都拿不到（前端 `$apiArr` 的数据通道不同）——
   **网关没有可用的单 IP 实时连接数接口**。想要电视当前会话数，只有睿易 APP 详情页或云端超限诊断两条路。
2. **「单 IP 限流 249 开着，云端就不会统计该 IP 会话」**【会话记录】
   云端单 IP 趋势本质是超限诊断；被限流的设备永远"不超限"，趋势图停止出新数据。对比 VPN 效果前必须意识到这个掩蔽效应。
3. **绿联 NAS 文件管理器上传 `.env` 会「成功但文件消失」**【会话记录】→ 用 SSH 写入。
4. **GitHub 直连被墙**【代码可证：无代理配置入库】
   推送必须临时 `-c http.proxy=http://127.0.0.1:7892`（VPN 开启时）；写死进 git config 会导致 VPN 一关必失败。仓库名强制全写小写。
5. **Git Bash 下 adb 的 `/data` 等路径会被 MSYS 改写**【代码可证：AGENTS.md 命令示例】→ 命令前加 `MSYS_NO_PATHCONV=1`。
6. **索尼电视 ADB 注入文本会被 kcm 输入法按 T9 改写**【会话记录】→ 已装 ADBKeyBoard，`am broadcast -a ADB_INPUT_TEXT --es msg '...'`；`input keyevent` 的 DEL 在输入框无效；屏幕键盘不接受 ADB 触摸。
7. **下载极慢时立即停手报告**【用户硬性规则】家有 2000M 宽带，不在慢速下载上空耗；镜像加速用 NAS Docker 已配置的 docker.1ms.run。
8. **睿易 MAC 格式多样**【代码可证：`reyee_exporter.py` `normalize_mac`】锐捷返回的 MAC 有冒号/横线/点分多种格式，比较前必须统一归一化，否则事件关联不上。
9. **锐捷占位值**【代码可证：`ap_lookup.py` `_clean`】接口会返回 `NULL`/`undefined` 字符串而不是空值，直接判空会踩雷。
10. **只读挂载的 Python 文件改完必须 restart 容器进程**【代码可证：`deploy-nexus.sh` 末尾注释】`up -d` 不会重载只读挂载的代码。

## 四、待决事项（不要替用户拍板）

- 限流 249 是否撤（观察 2-3 天后用户决策）。
- AdGuard Home 去留及是否做 NEXUS 第四页。
- `tools/` 下 Git/Node 安装包（约 400MB）是否入 Git 还是移 artifacts。
