# AGENTS.md — nexus-netms 项目手册

> 新 AI 会话第一上下文。本文档基于当前代码生成（2026-10-27），改动代码前先读完。
> 历史排障经验见 DECISIONS.md，进度见 STATUS.md，机器搭建见 docs/环境搭建.md。

## 一、项目目标

家庭网络监控与测速系统，运行在绿联 DX4600 Pro（UGOS Pro）的 Docker 上：
只读采集锐捷睿易全屋网络（网关 + 6 AP + 2 交换机）遥测与事件，经 Prometheus/SQLite 入库，
由 NEXUS 看板（`http://192.168.110.54:3002`）三个页面呈现，并内嵌 LibreSpeed 局域网测速与成绩分析。

## 二、操作红线（违反任一条都是事故）

1. **PC 端**：文件操作仅限 `D:\SpeedTest\`。
2. **NAS 端**（192.168.110.54）：容器与文件可自由增删改查。
3. **睿易后台**（网关 `https://192.168.110.1` + MACC 云端 noc.ruijie.com.cn）：**只读**。全屋真实生产网络。
   代码层面也强制：`apps/nexus/reyee-exporter/reyee_exporter.py`、`apps/speedtest-ap/ap_lookup.py` 文档串明确
   「只读，绝不调用配置接口」；全部查询只走 `devSta.get` / `devConfig.get`。
4. **电视**（索尼 Android TV，192.168.110.28）：仅 ADB 操作小黄JS 与输入法，不碰系统分区。
5. **尝试纪律**：任何任务最多连续 2 轮；失败即停并报告卡点；重大变更前先与人确认；不做冗余验证。

## 三、技术栈

- **后端/采集**：Python 3（标准库 http.server + requests + sqlite3 + paramiko），无 Web 框架。
- **前端**：纯原生 HTML/CSS/JS，无构建步骤；自定义无刷新导航（`apps/nexus/network-dashboard/navigation.js`）实现 SPA 化。
- **监控**：Prometheus + blackbox-exporter；指标由自研 exporter 以文本格式暴露。
- **测速**：linuxserver/librespeed 容器，经看板 `/speedtest/engine/` 流式反向代理，不开放独立主机端口。
- **部署**：Docker Compose；NAS 生产目录 `/volume1/docker/nexus/`，开发容器 `/volume1/docker/dev-workspace/`。

## 四、常用命令

```bash
python manage.py test            # 离线全量测试（16 模块：7 Python + 3 JS 语法 + 3 JS + 编译检查），改代码后必跑
python manage.py package all     # 生成干净部署包到 dist/（自动排除密钥/数据库/日志）
python manage.py verify          # 生产只读验证（需内网）
python manage.py tree            # 项目结构

# NAS 执行命令
PYTHONPATH=. .venv/Scripts/python.exe tools/nas/nas_ssh.py "<命令>"

# 网关只读查询（登录逻辑在 apps/speedtest-ap/reyee_session.py）
PYTHONPATH=apps/speedtest-ap .venv/Scripts/python.exe -c "from reyee_session import login,load_env; ..."

# 电视 ADB（Git Bash 必须 MSYS_NO_PATHCONV=1）
MSYS_NO_PATHCONV=1 tools/platform-tools/adb.exe -s 192.168.110.28:5555 shell "..."
```

git 推送：GitHub 直连被墙；VPN 开启时监听 `127.0.0.1:7892`，用
`git -c http.proxy=http://127.0.0.1:7892 -c https.proxy=http://127.0.0.1:7892 push`，**不要**写进 git config。

## 五、目录结构

```text
apps/
├── nexus/                    # 主交付物 NEXUS
│   ├── network-dashboard/    # 看板：dashboard_server.py(HTTP服务) + 3页面(总览/事件/测速) + 前端JS/CSS
│   ├── reyee-exporter/       # 采集：reyee_exporter.py(Prometheus指标) + event_store.py(事件入库)
│   ├── prometheus/ blackbox/ # 监控配置（数据卷保留旧名 monitoring_prometheus_data）
│   ├── docker-compose.yaml   # 5 服务：prometheus/blackbox/reyee-exporter/librespeed/network-dashboard
│   └── grafana/ public-gateway/  # 保留的历史配置，当前主链路不用
├── speedtest-ap/             # 原始原型：LibreSpeed 反向代理 + AP 反查（server.py、ap_lookup.py、test.py）
└── dev-workspace/            # NAS 浏览器开发环境（code-server + deploy-nexus.sh 一键部署）
tools/                        # PC 端工具（nas SSH、reyee 诊断、verification 只读验证、common.py 统一入口）
tests/                        # 离线回归 + fixtures 脱敏数据
config/secrets/               # 真实凭据（Git 完全忽略）；模板在 config/examples/
artifacts/                    # 截图/日志/研究产物（Git 忽略）
dist/                         # 部署包（Git 忽略，可由 manage.py package 重建）
```

## 六、核心模块与关键数据流

```text
reyee-exporter（每 3s ap_list+sta_list，30s 静态/备注，30s 系统日志）
  → Prometheus 指标 /metrics :9108        → 看板 /api/query(_range) 转发给前端图表
  → EventStore → SQLite events.db (WAL)    → 看板 /api/events 只读查询（漫游/离线/证据链）
浏览器测速 → /speedtest/engine/* 流式转发 → librespeed 容器
测速结果 POST /api/speedtest-results
  → ReyeeClient.lookup_by_ip(访问者IP) 取 AP/交换机上下文
  → speedtest_analysis.record_and_analyze 评分(有线/无线锚点) + 同 combo_key 历史百分位
  → SQLite speedtest.db → 前端渲染成绩与分位图
/api/ap-info → 按访问者真实 IP 只读反查当前连接 AP（失败不影响测速）
```

关键文件：
- 只读客户端唯一实现：`apps/speedtest-ap/ap_lookup.py`（`ReyeeClient`，会话缓存 + 自动重登 + 列表 TTL 缓存）。诊断工具经 `tools/common.py` 复用，**禁止复制第二份客户端实现**。
- 登录加密：`apps/speedtest-ap/test.py`（`fetch_device_key` + `aes_encrypt_openssl`，EGW 登录需先取设备密钥）。
- 评分/分位：`apps/nexus/network-dashboard/speedtest_analysis.py`。
- 事件解析：`apps/nexus/reyee-exporter/event_store.py`（漫游正则、离线状态机、syslog 去重、证据链）。
- 页面跳转性能：`navigation.js`（预取 + 模块作用域脚本 + ETag）。

## 七、外部依赖与凭据

| 对象 | 位置 | 凭据 |
|---|---|---|
| 睿易网关 EG310MG-P | `https://192.168.110.1` | `config/secrets/login.env`（EG_URL/EG_USERNAME/EG_PASSWORD） |
| MACC 云端 | noc.ruijie.com.cn | `config/secrets/cloud.env` |
| NAS SSH | 192.168.110.54 | `config/secrets/nas.env`（经 tools/nas/nas_ssh.py） |
| code-server | :8443 | NAS 端 `dev-workspace/secrets/code-server.env` |
| GitHub | haley242700/nexus-netms（仓库名强制全小写） | 推送走 VPN 代理 7892 |

## 八、编码规范

1. 真实密码只进 `config/secrets/` 或环境变量；任何日志/输出不打印凭据（代码中已全面贯彻）。
2. 睿易接口只调 `devSta.get` / `devConfig.get`；新增查询先在 `artifacts/research/` 的前端 JS 里确认模块名（方法见 DECISIONS.md）。
3. 看板显示名覆盖写在 `reyee_exporter.py` 的 `LOCAL_NAME_OVERRIDES`，**不回写**睿易后台。
4. SQLite 一律 WAL 模式；采集线程独占写入连接，页面用独立只读连接。
5. 页面/指标数据要保持「百分位越高越优秀」的统一方向（低优指标在前端反转），见 `speedtest_analysis.py` 与 `tests/test_speedtest_page.js`。
6. 部署相关改动后必跑 `python manage.py test`；提交前 `git status --ignored` 确认没有混入受保护文件。

## 九、NAS 部署

1. PC：`python manage.py package all`。
2. 上传 `dist/nexus/` 内容到 `/volume1/docker/nexus/`（部署包不含 login.env；生产密钥在该目录 `secrets/`）。
3. `docker compose up -d --build` 并 restart network-dashboard + reyee-exporter（Python 文件是只读挂载，必须重启进程才生效）。
   NAS 容器内可一键完成：`apps/dev-workspace/deploy-nexus.sh`（测试→打包→拷贝→重建→健康检查）。
