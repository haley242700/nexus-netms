# nexus-netms

家庭网络测速、AP 信息关联与网络监控项目，运行环境为绿联 DX4600 Pro / UGOS Pro Docker。当前仓库同时维护两个独立应用，以及 PC 端的测试、诊断和部署工具。

## 操作边界

- 本地项目根目录固定为 `D:\SpeedTest\`。
- 睿易诊断与采集工具仅使用只读接口，不修改 AP 或网络配置。
- `manage.py test` 和 `manage.py package` 完全离线，不连接 NAS 或生产后台。
- `manage.py verify` 会访问内网生产服务，但只执行读取和验证。

## 项目结构

```text
SpeedTest/
├── apps/
│   ├── speedtest-ap/       # LibreSpeed AP 信息集成、登录与只读客户端
│   ├── nexus/              # NEXUS 看板、Exporter、Prometheus 及 Compose
│   └── dev-workspace/      # NAS 浏览器开发环境与一键部署脚本
├── tools/
│   ├── common.py           # 统一路径和配置读取
│   ├── nas/                # NAS SSH 文件与命令工具
│   ├── reyee/              # 睿易只读诊断、日志和脚本分析
│   ├── dashboard/          # 历史 Grafana JSON 生成工具
│   └── verification/       # 生产只读验证与性能检查
├── tests/                  # 离线回归、前端测试和扩展性测试
│   └── fixtures/           # 可提交的脱敏测试数据
├── assets/heimdall/        # Heimdall 玻璃样式与壁纸资源
├── config/
│   ├── examples/           # 可提交的配置模板
│   └── secrets/            # 本地真实配置，Git 完全忽略
├── artifacts/              # 截图、日志、研究产物和备份，Git 完全忽略
├── dist/                   # 可重复生成的干净部署包，Git 忽略
└── manage.py               # 统一管理入口
```

## 页面

- `/`：运行总览，展示网关、AP、终端与信道遥测。
- `/events`：漫游与异常事件统计。
- `/speedtest`：统一风格的 LibreSpeed 局域网测速，展示下载、上传、延迟、抖动和当前终端的 AP 上下文。

测速引擎作为 `nexus-librespeed` 内部容器运行，不开放额外主机端口；看板通过 `/speedtest/engine/` 流式转发测速流量。`/api/ap-info` 按访问者真实 IP 只读查询睿易，AP 查询失败不影响测速。

随时查看实际目录：

```bash
python manage.py tree
```

## 开发环境初始化

### NAS code-server（主方式）

浏览器打开 `http://192.168.110.54:8443`，登录密码仅保存在 NAS 的 `/volume1/docker/dev-workspace/secrets/code-server.env`。开发容器项目位于 `/volume1/docker/dev-workspace/`，仓库克隆到容器内的 `/workspace/SpeedTest`，与生产目录 `/volume1/docker/nexus/` 分离。

首次克隆后，在 code-server 终端执行：

```bash
cd /workspace/SpeedTest
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

之后使用 `.venv/bin/python manage.py test` 运行测试。验证并部署 NEXUS 时执行 `apps/dev-workspace/deploy-nexus.sh`；脚本先运行测试，再生成干净部署包并重建生产容器，不会覆盖生产密钥或事件数据库。

### PC（可选）

在 PC 项目根目录执行：

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

PowerShell 可将上面的路径写为 `.venv\Scripts\python.exe`。

真实配置仅保存在 `config/secrets/`，模板位于 `config/examples/`：

- `login.env`：睿易后台及 LibreSpeed 配置，参考 `login.env.example`。
- `nas.env`：NAS SSH 配置，参考 `nas.env.example`。
- `.env`、`cloud.env` 等本地文件同样不会上传 Git。

不要将真实密码写入 `apps/`、`tests/`、Compose 文件或 README。

## 统一管理命令

### 离线全量测试

```bash
python manage.py test
```

包含 Python 语法编译、事件单元测试、事件 API、旧库迁移、十万级合成数据扩展测试，以及前端语法、分页和吞吐测试。测试临时文件只写入项目内的 `artifacts/tmp`，不会访问生产网络。

### 生成部署包

```bash
python manage.py package all
```

也可只生成一个应用：

```bash
python manage.py package speedtest-ap
python manage.py package nexus
```

输出位于 `dist/speedtest-ap/` 和 `dist/nexus/`。每次生成都会重建目标目录，并检查部署包不包含密钥、会话、数据库、日志或缓存。

### 生产只读验证

```bash
python manage.py verify
```

该命令检查页面、API、事件计数、采集周期和性能；只有明确需要访问内网生产服务时才运行。

## NAS 重复部署

先在 PC 上运行 `python manage.py package all`，然后上传对应部署包中的**内容**：

| 本地部署包 | NAS 目标目录 | Compose 文件 |
| --- | --- | --- |
| `dist/speedtest-ap/` | `/volume1/docker/speedtest-ap/` | `speedtest-ap.compose.yaml` |
| `dist/nexus/` | `/volume1/docker/nexus/` | `docker-compose.yaml` |

`login-test.compose.yaml` 用于独立的单次登录测试项目，其 NAS 目录为 `/volume1/docker/tmp-login-test/`。

部署包不携带真实 `login.env`。NEXUS 的配置位于 `/volume1/docker/nexus/secrets/login.env`，事件数据位于 `events/`。NEXUS 部署包自动带上只读客户端运行文件，可独立构建 `nexus-runtime:local`，不依赖 speedtest-ap 的目录或镜像。Prometheus 继续使用名为 `monitoring_prometheus_data` 的数据卷，以保留项目重命名前的历史数据。

## 诊断工具

所有诊断工具从项目根目录以模块方式运行，例如：

```bash
python -m tools.reyee.probe_offline_logs
python -m tools.reyee.analyze_offline_logs
python -m tools.reyee.inspect_remarks
```

新产生的诊断文件统一写入 `artifacts/diagnostics/`，下载的后台脚本写入 `artifacts/research/`。应用只保留一份只读客户端实现，工具通过 `tools/common.py` 复用。

## Git 约定

`.gitignore` 已覆盖真实 env、`htpasswd`、Cookie/会话、数据库、日志、截图、研究产物、虚拟环境和部署包。不要对这些文件使用 `git add -f`。

提交前建议执行：

```bash
python manage.py test
git status --ignored
```

`apps/nexus/grafana/` 与 `apps/nexus/public-gateway/` 是保留的历史配置；当前 NEXUS 主链路为 `network-dashboard`、`reyee-exporter`、Prometheus 和 Blackbox。
