# P1 验收报告

- 日期：2026-10-30
- 范围：项目结构、依赖管理、代码规范、类型检查、测试框架、CI；协议包、Runtime 骨架、DSH 插件骨架。
- 目标平台：Windows 10/11、Ubuntu 22.04。
- 结论：**P1 工程初始化完成**。真实麦克风/播放/唤醒/VAD/ASR/TTS/AEC 未实现（P2/P3）。

## 1. 交付清单

| 项 | 路径 | 状态 |
|---|---|---|
| Monorepo 根配置 | `package.json`、`pnpm-workspace.yaml`、`tsconfig.base.json`、`eslint.config.js`、`.prettierrc.json` | done |
| 许可证/NOTICE | `LICENSE`（Apache-2.0）、`NOTICE.md` | done |
| 协议包 | `packages/protocol` | done |
| DSH 插件 | `packages/plugin` | done |
| Python Runtime | `runtime/` | done |
| 模型清单/下载器 | `models/manifest.json`、`scripts/download_models.py` | done |
| 默认配置/Schema | `config/default.json`、`config/schema.json` | done |
| CI | `.github/workflows/ci.yml` | done |
| 文档 | `docs/ARCHITECTURE.md`、`PROTOCOL.md`、`SECURITY.md`、`ENGINE_ADAPTERS.md`、`WINDOWS.md`、`LINUX.md`、`DEVELOPMENT.md`、`ROADMAP.md` | done |
| 安装/构建脚本 | `scripts/install_*.{ps1,sh}`、`build_*.{ps1,sh}`、`gen_config.py` | done |

## 2. 实际验证结果

### 2.1 TypeScript

```text
pnpm -r build      PASS
pnpm -r lint       PASS
pnpm -r typecheck  PASS
pnpm -r test       PASS
```

- Protocol：3 个测试文件，17 个测试通过。
- Plugin：4 个测试文件，12 个测试通过。
- 覆盖：事件 schema、认证消息、二进制 PCM 帧、发现文件、RuntimeClient 握手/坏 token、RuntimeManager 连接/错误、Host apply 生命周期。

### 2.2 Python

```text
uv run ruff format --check src tests   PASS (41 files formatted)
uv run ruff check src tests            PASS
uv run mypy src                        PASS (29 source files)
uv run pytest -q                       PASS (55 passed, 1 skipped)
```

跳过项：Windows 上不检查 POSIX `0600` 权限位（`test_discovery.py`）；Linux CI 会执行该项。

覆盖：AudioRingBuffer、StreamingResampler、PCM 帧已知字节（与 TypeScript 一致）、事件解析、token 认证、发现文件、配置/JSON Schema、状态机/Avatar 投影、fake engines、WebSocket 认证/心跳、Supervisor 启动/停止、模型 manifest schema、日志脱敏。

### 2.3 Runtime 独立启动（G3）

实际执行：

```text
uv run voice-runtime daemon --fake-audio --port 0
{"ok": true, "port": 17277, "pid": 24316, "discovery": "...\\runtime.json", "protocolVersion": 1}
```

用 WebSocket 客户端验证：

```text
auth.ok
runtime.ready  0.1.0  ['fake-audio']
discovery exists after shutdown: False
```

结论：Runtime 可在无 DSH 的情况下启动、认证、发送 ready、接受 `runtime.shutdown` 并清理发现文件。

### 2.4 Doctor

```text
uv run voice-runtime doctor --json
"ok": true
```

必检项（Python 3.11、协议、数据目录）通过；`sounddevice`/`sherpa_onnx`/`livekit`/音频设备为可选警告，符合 P1 范围。

### 2.5 模型清单

- `models/manifest.json` 通过 `models/manifest.schema.json` 校验。
- 仅 Silero VAD 标记 `verified: true`（含 SHA256/大小）。
- Kokoro 为 candidate（无 SHA256，下载器拒绝自动下载）。
- `scripts/download_models.py --list/--dry-run` 通过；未下载任何模型。

## 3. 验收门状态

| 门 | 状态 | 说明 |
|---|---|---|
| G1 两平台构建 | ✅ 本地 Windows；CI 配置 Ubuntu/Windows | 未在 Ubuntu 实机跑过，见 §4 |
| G2 lint/typecheck/test | ✅ | 无失败测试；1 个 Windows 跳过 |
| G3 Runtime 独立启动 | ✅ | 见 §2.3 |
| G4 DSH 插件加载/设置页 | ⚠️ **未验证** | 未向用户现有 desktop profile 安装插件（需要显式授权，且可能改变用户 DSH 状态）。已构建 Host/Client、通过 Host apply 单测；未在真实 DSH 页面确认设置页渲染。 |
| G5 协议 round-trip | ✅ | TS + Python 双侧；已知帧字节一致 |
| G6 模型清单/下载器 | ✅ | schema + 负向拒绝 |
| G7 安全 | ✅（P1 范围） | 未认证/坏 token/协议版本拒绝、日志脱敏单测 |
| G8 文档 | ✅ | 8 份文档；未把 P2/P3 能力写成已完成 |

## 4. 未验证/限制（必须继承到 P2）

1. **G4 未在真实 DSH 中安装验证**：当前 shell 的 `plugin_manager` 审批被禁用；且安装会修改用户的 `desktop` profile。需要在测试 profile 或用户明确授权后进行。
2. **未在 Ubuntu 实机运行**：只写了 CI 配置；本机是 Windows。P2 必须在 Ubuntu 22.04 跑 Python/Node 两项 job。
3. **没有真实音频**：`sounddevice` 未加入 P1 依赖；`--fake-audio` 不打开设备。设备枚举、48k/44.1k/16k、双工、热插拔都是 P2。
4. **没有真实引擎**：Sherpa/livekit 未安装；`EngineManager` 只有 fake。`doctor` 会如实报告缺失。
5. **模型许可**：Kokoro 已有 Apache-2.0 结论但缺 SHA256；KWS/流式 ASR 权重许可仍未核实；P2/P3 前不得设为默认自动下载。
6. **Windows 非 ASCII 路径**：uv 的 editable `.pth` 在中文路径下可能无法被 Python 读取；`pytest` 用 `pythonpath = ["src"]` 规避，CLI 开发时需 `PYTHONPATH=src`（见 `WINDOWS.md`）。CI 路径为 ASCII，不受影响。
7. **插件安装打包**：`packages/plugin/lib` 是构建产物并已被 `.gitignore` 忽略；发布前需 `pnpm --filter dsh-voice-assistant build` 并确认 `files` 清单。P1 未做 npm pack/安装。

## 5. 与 P1 计划的偏差

| 计划 | 实际 | 原因 |
|---|---|---|
| `tsdown` 构建 | `tsc` + `esbuild` | 更少依赖、可控 Host ESM + Client IIFE；dsh 客户端只需一个 IIFE bundle |
| FastAPI/uvicorn | `websockets` + 原生 HTTP 状态路由在插件侧 | P1 仅需 WS 控制 + 插件状态；P4 再评估 HTTP 健康端点 |
| `plugin.json` | 未创建 | DSH 不消费；`package.json.dsh` 是唯一清单 |
| G4 真实安装 | 只做构建 + Host apply 单测 | 避免未经授权修改用户 DSH profile |
| 模型下载全部条目 | 只放 1 个 verified + 1 个 candidate | 没有可信 SHA256 的模型不进入自动下载 |

## 6. 下一步（P2）

1. 在 Ubuntu 22.04 实机跑 P1 CI 等价命令。
2. 加入 `sounddevice` + `livekit` spike：设备枚举、48k/16k 采集、播放回调、AEC 软件参考。
3. 打开 `runtime/src/voice_runtime/audio` 的真实实现；保持 fake 作为测试替身。
4. 在测试 DSH profile 安装插件，完成 G4，并验证 `settings.section` 渲染。
5. 补齐 Kokoro SHA256/大小；确认 KWS/ASR 权重许可后再进入 P3。
