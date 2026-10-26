# AGENTS.md — AI 会话操作手册

> 本文件是新 AI 会话的第一上下文。任何操作前先读完本文件。
> 最后更新：2026-10-26（电视 VPN 方案落地后）

## 一、操作红线（违反任何一条都是事故）

1. **PC 端**：文件操作仅限项目文件夹（`D:\SpeedTest\`）。确需操作其他路径必须先请求人类批准。
2. **NAS 端**（绿联 DX4600 Pro，192.168.110.54）：可自由增删改查容器与文件。
3. **睿易后台**（网关 + MACC 云端）：**只读**。这是用户最重要的生产环境，全屋真实网络设备，网络崩溃不可接受。
4. **电视**（索尼 Android TV）：只允许 ADB 操作小黄JS 应用与输入法相关设置，不碰系统分区、不恢复出厂。
5. **尝试纪律**：任何任务最多连续尝试 2 轮；失败立即停下报告卡点，不自动换方案反复试错；重大变更前先与人类确认；不做冗余验证。

## 二、环境速查表

| 对象 | 地址/标识 | 说明 |
| --- | --- | --- |
| NAS | `192.168.110.54`（SSH 配置在 `config/secrets/nas.env`） | UGOS Pro，Docker 主战场 |
| code-server 开发容器 | `http://192.168.110.54:8443` | NAS 上浏览器开发环境，密码在 NAS 端 `code-server.env` |
| 睿易网关 | `https://192.168.110.1`（EG310MG-P，SN G1V403U011506） | 凭据 `config/secrets/login.env`，登录见 `apps/speedtest-ap/reyee_session.py` |
| MACC 云端 | `https://noc.ruijie.com.cn`（凭据 `config/secrets/cloud.env`） | 只读查询用，登录态在内置浏览器 |
| NEXUS 看板 | `http://192.168.110.54:3002`（/、/events、/speedtest） | 主交付物 |
| AdGuard Home | `192.168.110.54:3003`（面板）/ `:53`（DNS） | **待命未接入网络**，去留待人类决策 |
| 索尼电视 | `192.168.110.28`（MAC cc:6b:1e:0d:8c:ed） | ADB 调试已开，`adb -s 192.168.110.28:5555` |
| GitHub 仓库 | `github.com/haley242700/nexus-netms` | 仓库名必须全小写 |

## 三、设备清单（全屋 6 AP + 2 交换机 + 网关）

- 网关：RG-EG310MG-P（2.5G 口，WAN 会话上限 1400，MTU 1492）
- AP：一楼客厅、一楼主卧、负一楼书房、负一卧室等共 6 台（WiFi 6）
- 交换机 2 台（.6 曾离线报警，后自愈；均 2.5G）
- 已知终端大户：电视 `.28`（见第六节事故档案）

## 四、常用命令

```bash
# 离线全量测试（不碰生产，改代码后必跑）
python manage.py test

# 生成部署包 → 上传 NAS 对应目录重建容器
python manage.py package all

# NAS 执行命令（密码在 nas.env）
PYTHONPATH=. .venv/Scripts/python.exe tools/nas/nas_ssh.py "<命令>"
# NAS 上 docker 命令需要提权：echo <密码> | sudo -S docker ps

# 网关只读查询
PYTHONPATH=apps/speedtest-ap .venv/Scripts/python.exe -c "..."
# 客户端类：from ap_lookup import ReyeeClient; c._cmd('user_list', {...})
# 登录：reyee_session.login(load_env('config/secrets/login.env'))

# 电视 ADB（Git Bash 必须加 MSYS_NO_PATHCONV=1，否则 /data 路径被改写）
MSYS_NO_PATHCONV=1 tools/platform-tools/adb.exe -s 192.168.110.28:5555 shell "..."
```

git 推送注意：本机 git 配置了失效代理 `127.0.0.1:7892`，推送必须 `git -c http.proxy= -c https.proxy= push`。

## 五、项目架构一句话版

`reyee-exporter`（Python，只读轮询网关 + 系统日志入库）→ SQLite 事件库 → `network-dashboard`（纯前端 + `dashboard_server.py`，端口 3001→3002）三个页面（总览/事件/测速）；`nexus-librespeed` 内嵌测速引擎经 `/speedtest/engine/` 流式转发；Prometheus + Blackbox 监控。NAS 生产目录 `/volume1/docker/nexus/`，开发容器项目在 `/volume1/docker/dev-workspace/`（仓库克隆于容器内 `/workspace/SpeedTest`）。

## 六、事故档案与进行中的事（2026-10-26）

**WAN 会话超限事故（已定位，治理中）**
- 现象：WAN 会话峰值 4229（上限 1400），半连接 4003，多次全屋云连接闪断
- 根因：电视 `.28` 访问被墙海外域名失败 → 无限重试 → 半连接风暴（云端 AI 诊断异常 IP 仅 .28）
- 治标：睿易 AI 防护已开单 IP 限流 249
- 治本：电视已装机场官方客户端小黄JS（包名 `com.xhjs`，ClashMeta 内核），**智能分流模式**，2026-10-26 20:31 已连接
- 待办：观察 WAN 会话趋势（MACC 诊断页历史趋势图），稳定数日后由人类决策是否撤限流

**电视 ADB 操作手册（血泪经验）**
- 索尼 kcm 会把 ADB 注入的数字按 T9 改写（2→a、@ 丢失）→ 已装 ADBKeyBoard（`com.android.adbkeyboard/.AdbIME`），用 `am broadcast -a ADB_INPUT_TEXT --es msg '...'` 注入
- `input keyevent` 的 DEL/MOVE_HOME 在输入框上无效；清空应用数据用 `pm clear com.xhjs`
- 屏幕键盘不接受 ADB 触摸，只能遥控器
- 小黄JS 登录页「记住我」与「自动登录」**互斥**（App bug），当前只勾了「记住我」
- VPN 远程开关：`am broadcast -a com.xhjs.action.START / STOP / TOGGLE`（TempActivity，已验证）

**待命组件**
- AdGuard Home（NAS 容器，未接入网络）：密码空、面板 3003；`AdGuardHome.yaml` 的 `bootstrap_dns` 必须单行字符串。是否做 NEXUS 第四页由人类决策。

## 七、已知坑速览

- 绿联 NAS 文件管理器上传 `.env` 会「成功但消失」→ 用 SSH 写入
- GitHub 仓库名强制小写，引用统一 `nexus-netms`
- 轩辕镜像加速：NAS Docker 配置了 1ms.run；PC 走 jsdelivr 镜像可绕开 GitHub 下载被墙
- 下载极慢时立即停止并报告，不在慢速下载上空耗（用户家 2000M 宽带）
