# P1 实施计划 — 项目基础设施

- 前置：P0 三份审计文档 + 技术选型 + 风险清单完成（本次提交）
- 目标：建立可构建、可测试、可安装的最小骨架；**不实现真实语音引擎**，但把协议、配置、进程、认证、CI 全部打通。
- 周期估算：6–8 个工作日（单人）；可与 P2 音频 spike 并行 2 天。
- 验收原则：每一步都有可执行命令与可观察结果；不以“代码写完”代替“跑通”。

---

## 1. 目录结构（P1 落地）

```text
dsh-voice-assistant/
├── README.md
├── LICENSE                       # Apache-2.0（建议）
├── NOTICE.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── package.json                  # pnpm workspace root
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
├── .gitignore
├── .editorconfig
├── .github/workflows/ci.yml
│
├── packages/
│   ├── protocol/
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   ├── src/
│   │   │   ├── index.ts
│   │   │   ├── events.ts          # VoiceEvent<T>、事件枚举、payload schema
│   │   │   ├── binary.ts          # 16-byte PCM frame header codec
│   │   │   ├── errors.ts          # 错误码
│   │   │   └── version.ts         # PROTOCOL_VERSION = 1
│   │   └── test/
│   │       ├── events.test.ts
│   │       └── binary.test.ts
│   │
│   └── plugin/
│       ├── package.json
│       ├── plugin.json            # 可选：仅本工程元数据；DSH 不消费（DSH 只读 package.json.dsh）
│       ├── tsconfig.json
│       ├── tsdown.config.mjs
│       ├── cordis.patch.yml
│       ├── locale/{en,zh}.json
│       ├── icon.svg
│       ├── src/
│       │   ├── host/
│       │   │   ├── index.ts       # export name/inject/Config/apply
│       │   │   ├── config.ts      # schemastery Config
│       │   │   ├── runtime-manager.ts
│       │   │   ├── runtime-client.ts
│       │   │   ├── event-router.ts
│       │   │   ├── health.ts
│       │   │   └── http.ts        # active-session 上报路由（P5 用，P1 先留接口）
│       │   └── client/
│       │       ├── index.ts       # window.__ModuleLoader__.load
│       │       ├── settings.tsx   # settings.section（P1 只读状态）
│       │       └── styles.ts
│       └── test/
│           ├── runtime-manager.test.ts
│           └── config.test.ts
│
├── runtime/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/voice_runtime/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── daemon.py             # CLI: doctor / daemon / probe
│   │   ├── runtime/
│   │   │   ├── lifecycle.py
│   │   │   ├── supervisor.py
│   │   │   └── health.py
│   │   ├── audio/
│   │   │   ├── __init__.py
│   │   │   ├── device_manager.py  # 枚举/能力查询（P1 只读）
│   │   │   ├── audio_buffer.py    # ring buffer + 单测
│   │   │   └── resampler.py       # 16k <-> device rate + 单测
│   │   ├── engines/
│   │   │   ├── base.py            # 抽象基类（P1 只定义，不实现）
│   │   │   └── manager.py         # 注册/健康检查/降级骨架
│   │   ├── session/
│   │   │   ├── state_machine.py   # P1 只实现 IDLE/ERROR + 转移表骨架
│   │   │   └── manager.py
│   │   ├── transport/
│   │   │   ├── protocol.py        # Pydantic 镜像 + 校验
│   │   │   ├── websocket_server.py
│   │   │   ├── authentication.py
│   │   │   └── discovery.py       # 发现文件 0600/ACL
│   │   ├── config/
│   │   │   ├── schema.py          # Pydantic Settings
│   │   │   ├── loader.py
│   │   │   └── defaults.py
│   │   └── utils/
│   │       ├── logging.py         # 脱敏 filter
│   │       └── platform.py        # platformdirs 封装
│   └── tests/
│       ├── test_audio_buffer.py
│       ├── test_resampler.py
│       ├── test_protocol.py
│       ├── test_auth.py
│       ├── test_discovery.py
│       ├── test_state_machine.py
│       └── test_config.py
│
├── models/
│   ├── manifest.json
│   └── manifest.schema.json
│
├── config/
│   ├── default.json
│   └── schema.json
│
├── scripts/
│   ├── install_windows.ps1
│   ├── install_linux.sh
│   ├── build_windows.ps1
│   ├── build_linux.sh
│   └── download_models.py
│
├── tests/
│   ├── integration/
│   │   ├── test_runtime_startup.py
│   │   └── test_plugin_connect.mjs
│   └── e2e/                       # P10 前只放 README
│
└── docs/
    ├── ARCHITECTURE.md
    ├── PROTOCOL.md
    ├── ENGINE_ADAPTERS.md
    ├── SECURITY.md
    ├── WINDOWS.md
    ├── LINUX.md
    ├── DEVELOPMENT.md
    ├── ROADMAP.md
    ├── TECH_SELECTION.md          # 本次 P0 产出
    ├── RISK_REGISTER.md           # 本次 P0 产出
    └── research/
        ├── JARVIS_ANALYSIS.md
        ├── DSH_PET_ANALYSIS.md
        └── DSH_API_ANALYSIS.md
```

**与任务书结构的差异与理由**：

1. 增加 `packages/plugin/src/client`：DSH 插件必须 Host+Client 两半；设置页/麦克风指示在 Client。
2. 增加 `transport/discovery.py`：Runtime 独立启动时插件需要发现端口/token；任务书未列，但安全要求必须有。
3. 增加 `models/manifest.schema.json`：模型清单自身需要校验，防止手写错误。
4. `docs/TECH_SELECTION.md`、`RISK_REGISTER.md` 为 P0 产物，保留在 docs 根便于评审。
5. `plugin.json` 仅当需要插件市场元数据时使用；DSH 本地 bundle 以 `package.json` 的 `dsh.bundle.patch` 为准，不假设 `plugin.json` 是必需文件。

---

## 2. 工作包（WP）

### WP1.1 仓库与工具链（0.5 天）

- 初始化 pnpm workspace、`packages/protocol`、`packages/plugin`、`runtime/` uv 项目。
- 根 `package.json` scripts：`lint`、`typecheck`、`test`、`build`、`format`。
- Python：`ruff`、`mypy`、`pytest`、`pytest-asyncio`、`pytest-cov`。
- TS：`typescript` strict、`eslint` flat config、`vitest`、`tsdown`。
- `.gitignore`：`node_modules/`、`.venv/`、`dist/`、`models/*`（保留 manifest）、`*.wav`、日志、发现文件。
- LICENSE/NOTICE/CONTRIBUTING/CHANGELOG 初版。

**验收**：`pnpm install && pnpm -r build && pnpm -r test && pnpm -r typecheck && pnpm -r lint` 通过；`uv sync && uv run ruff check && uv run mypy src && uv run pytest` 通过。

### WP1.2 协议包（1.5 天）

- `VoiceEvent<T>`：`version: 1`、`id`、`sessionId`、`sequence`、`timestamp`、`type`、`payload`。
- 事件枚举：任务书 §八 的 Runtime→Plugin / Plugin→Runtime 全量。
- Zod schema + `z.infer` 类型；JSON Schema 导出脚本。
- 二进制 PCM 帧：
  - magic `VAP1`（4B）、version（1B）、flags（1B）、header length（2B）、sequence（4B）、timestamp_ms（4B）、sample_rate（4B）、channels（2B）、samples（2B）……总头 24B 或 16B；P1 固定 24B，保留扩展。
  - PCM16 little-endian；校验长度；拒绝非法 magic/版本/采样率/通道。
- 错误码：`auth_failed`、`protocol_version_mismatch`、`session_missing`、`engine_unavailable`、`device_lost`、`tts_cancelled`、`agent_cancel_failed` 等。
- 单元测试：JSON round-trip、未知 type 拒绝、序列号回绕、二进制头解析/拒绝、分片音频重组。

**验收**：`pnpm --filter @dsh-voice/protocol test`；导出 `protocol.schema.json` 可被 Python `jsonschema` 校验。

### WP1.3 Python Runtime 骨架（2 天）

- `voice_runtime.daemon` CLI：
  - `doctor`：Python/依赖/设备/配置/端口/权限检查，输出人类可读 + `--json`。
  - `daemon --config <path>`：启动，写发现文件，启动 WS，等待信号；`--fake-audio` 不打开设备。
  - `probe --device`：P1 只枚举，不实际录音。
- 配置：
  - Pydantic Settings，层级：默认 < 用户配置（platformdirs）< 环境变量 < CLI。
  - `config/schema.json` 由 Pydantic `model_json_schema()` 生成，CI 检查与 `default.json` 一致。
- 发现与认证：
  - 绑定 `127.0.0.1:0`，写 `runtime.json`（pid、port、token、version、started_at、protocol_version）。
  - Windows：创建文件后 `icacls` 仅当前用户；Linux：`chmod 600`。
  - token 32 bytes `secrets.token_urlsafe(32)`；日志/异常不得包含 token。
- WS：
  - 首帧 `auth`（type + token + protocolVersion），失败关闭。
  - `ping/pong`、`runtime.ready`、`runtime.error`。
  - 连接上限、未认证超时 5 s。
- 生命周期：SIGINT/SIGTERM 优雅退出；关闭 WS、删除发现文件、释放资源；异常退出写 `runtime.error`。
- 日志：stdlib logging + JSON 可选；脱敏 filter（token、`authorization`、`text` 字段）。
- 音频骨架：`AudioBuffer`（ring，固定容量，单测）、`Resampler`（polyphase，单测）、`DeviceManager`（枚举/默认设备/能力查询，P1 只读）。
- 引擎基类：`WakeEngine`、`VADEngine`、`ASREngine`、`TTSEngine`、`AECProcessor`，全部 `async` + `initialize/health/shutdown`；P1 只定义 `NotImplemented` 的 Fake 实现，供协议测试。
- 状态机：P1 只实现 `IDLE ↔ ERROR` 与转移合法性校验；完整 10 状态在 P4。

**验收**：
- `uv run voice-runtime doctor` 在两平台输出可读报告。
- `uv run voice-runtime daemon --fake-audio` 启动后：
  - 发现文件存在且权限正确；
  - 未认证 WS 被拒；错误 token 被拒；正确 token 收到 `runtime.ready`；
  - `ping` 收到 `pong`；
  - Ctrl+C 后进程退出、发现文件删除。
- `uv run pytest` 全绿；`ruff`/`mypy` 通过。

### WP1.4 模型清单与下载器（1 天）

- `models/manifest.json` 条目字段：
  - `model_id`、`engine`、`task`、`language`、`version`、`download_url`（数组/镜像）、`sha256`、`size`、`license`、`license_url`、`commercial_use`、`redistributable`、`supported_platforms`、`sample_rate`、`capabilities`、`files`。
- P1 只放 2 个真实条目（Silero VAD、Kokoro），其余标 `status: candidate` 且不自动下载；**不下载大模型**。
- `scripts/download_models.py`：
  - `--list`、`--verify`、`--download <id>`、`--all`、`--dry-run`。
  - 临时目录 → sha256 → 原子移动；断点续传；失败清理；镜像回退。
  - 许可需 `--accept-license <id>`；`commercial_use: false` 需二次确认。
- 测试：本地 HTTP fixture 提供小文件；覆盖成功、hash 错误、断点续传、原子性、许可拒绝。

**验收**：`uv run python scripts/download_models.py --verify` 对 P1 条目通过；负向测试拒绝坏 hash；不产生大文件下载。

### WP1.5 DSH 插件骨架（2 天）

- `package.json`：
  - `name: "dsh-voice-assistant"`、`type: module`、`main: lib/index.js`、`exports` 含 `./client`、`dsh.bundle.patch`、`dsh.client`（`platform: web`、`inject: ["@deepseek-ai/dsh-client-ui-conversation"]`）、`peerDependencies` 指向 `0.2.1-rc.3` 系列。
  - `files` 包含 `lib`、`cordis.patch.yml`、`locale`、`icon.svg`。
- `cordis.patch.yml`：`- insert: - id: dsh-voice-assistant / name: 'dsh-voice-assistant'`。
- Host：
  - `export const name = 'voice-assistant'`、`inject = ['agents','sessions','webServer']`（P1 最小）。
  - `Config`（schemastery）：`runtimePath`、`autoStart`、`wsPort`（0=自动）、`sessionStrategy`、`logLevel`、`voiceEnabled`。
  - `RuntimeManager`：spawn Runtime（`child_process.spawn`，stdio pipe）、读取发现文件、连接 WS、指数退避重连（1s→30s，jitter）、健康状态、dispose 时优雅停止。
  - `RuntimeClient`：auth、ping/pong、事件分发、请求-响应（`tts.speak` 等 P4 再接）。
  - `EventRouter`：把 runtime 事件转成内部事件；P1 只处理 `runtime.ready`、`runtime.error`、`pong`。
  - `http.ts`：注册 `/dsh-voice-assistant/active-session`（P1 只返回 501/占位；P5 实现）。
- Client：
  - `client.js` 由 tsdown 产出 IIFE；`window.__ModuleLoader__.load({id, factory})`。
  - 注册 `settings.section`（id `voice-assistant`，label 本地化），页面显示：Runtime 状态、版本、端口、发现文件路径、按钮“启动/停止/诊断”（P1 调 Host HTTP 占位）。
  - 所有注册 try/catch，失败不影响 DSH。
- 测试：Vitest mock `child_process`、`ws`、`fs`；覆盖重连、发现文件解析、token 不日志、dispose。

**验收**：在测试 profile 中安装本地 bundle，DSH 设置页出现 “Voice Assistant”，显示 Runtime 状态；Host 能启动/停止 fake runtime；DSH 重启后自动恢复。

### WP1.6 CI 与文档（1 天）

- GitHub Actions：
  - `python` job：Windows + Ubuntu，Python 3.11，`uv sync --frozen`，ruff/mypy/pytest。
  - `node` job：Windows + Ubuntu，Node 24，pnpm install，lint/typecheck/test/build。
  - `license` job：pip-licenses + license-checker，拒绝 GPL/AGPL（允许列表例外需注释）。
  - `docs` job：markdown link check（可选）。
- 文档初版：
  - `ARCHITECTURE.md`：分层、进程、线程、数据流、单一播放权威、状态机三分离。
  - `PROTOCOL.md`：消息、二进制帧、认证、重连、错误码、版本协商。
  - `SECURITY.md`：localhost、token、发现文件、权限、确认、日志脱敏、威胁模型。
  - `ENGINE_ADAPTERS.md`：接口、生命周期、错误、模型许可、替换指南。
  - `WINDOWS.md` / `LINUX.md`：安装、设备、权限、systemd/Startup、已知问题。
  - `DEVELOPMENT.md`：环境、命令、测试、调试、提交规范。
  - `ROADMAP.md`：P0-P10 阶段与验收门。
- `CHANGELOG.md`：P1 条目。

**验收**：CI 在 Windows/Ubuntu 全绿；文档无“已完成”但未实现的功能描述。

---

## 3. P1 验收门（必须全部满足）

| 门 | 标准 | 证据 |
|---|---|---|
| G1 构建 | 两平台 `pnpm build` + `uv sync` 成功 | CI 日志 |
| G2 质量 | lint/typecheck/test 全绿；覆盖率 ≥70%（核心模块） | CI + coverage 报告 |
| G3 Runtime 独立 | 不启动 DSH，`daemon --fake-audio` 可启动、认证、心跳、优雅退出 | 集成测试 |
| G4 插件加载 | DSH 0.2.1-rc.3 测试 profile 中安装并显示设置页 | 截图/日志 + `cordis_inspect_query` |
| G5 协议 | JSON + 二进制帧 round-trip；版本不匹配拒绝 | 单测 |
| G6 模型清单 | schema 校验 + 下载器负向测试；无大文件入库 | pytest |
| G7 安全 | 未认证连接拒绝；日志无 token/转写 | 安全测试 |
| G8 文档 | 七份文档齐全；无 stub 当完成 | 评审 |

**P1 明确不做**：真实麦克风采集、真实 VAD/ASR/TTS、AEC、DSH Agent 消息发送、dsh-pet 联动、设置页完整 17 项、打包安装器。

---

## 4. 测试计划（P1）

### Python

| 测试 | 内容 |
|---|---|
| `test_audio_buffer.py` | ring 容量、覆盖最旧、并发读写、零长度、超大块 |
| `test_resampler.py` | 48k→16k、44.1k→16k、16k→24k、长度/幅度、状态连续 |
| `test_protocol.py` | Pydantic 模型校验、未知字段、版本、错误码 |
| `test_auth.py` | 正确/错误/缺失 token、超时、重放、日志脱敏 |
| `test_discovery.py` | 文件权限（POSIX 0600 / Windows ACL）、原子写、过期清理 |
| `test_state_machine.py` | 合法/非法转移、全局取消、超时 |
| `test_config.py` | 默认值、环境变量覆盖、非法值、schema 生成 |

### TypeScript

| 测试 | 内容 |
|---|---|
| `events.test.ts` | schema 校验、未知 type、序列号 |
| `binary.test.ts` | 头解析、坏 magic/版本/长度、PCM 对齐 |
| `runtime-manager.test.ts` | spawn、发现文件、重连退避、dispose、崩溃重启 |
| `config.test.ts` | 默认值、非法配置、迁移 |

### 集成

| 测试 | 内容 |
|---|---|
| `test_runtime_startup.py` | 启动 daemon → 发现文件 → WS auth → ready → shutdown |
| `test_plugin_connect.mjs` | Node 启动 fake runtime → 插件 RuntimeClient 连接 → 收到 ready → 断开重连 |

---

## 5. 分支与提交

- `main`：受保护，只接受 PR。
- `develop`：集成分支。
- `feature/p1-infrastructure`：本阶段。
- 提交粒度：脚手架、协议、runtime、模型、plugin、CI/文档各一次；每个提交可独立构建。
- 不合并上游 Git 历史；Jarvis/dsh-pet 仅作为只读参考。

---

## 6. P1 之后的衔接

| 阶段 | 入口条件 | 主要产出 |
|---|---|---|
| P2 音频系统 | P1 G1-G8 通过 | 真实设备枚举/采集/播放/重采样/设备热插拔；AEC spike |
| P3 语音引擎 | P2 音频闭环 + 模型许可清单 | Wake/VAD/ASR/TTS 适配器与基准 |
| P4 协议完整 | P1 协议 + P2 音频帧 | 全事件、重连、取消、错误恢复 |
| P5 DSH 插件 | P1 插件骨架 + P4 | Agent Bridge、设置页、麦克风指示 |
| P6 dsh-pet | P5 + V-07 | PetBridge、动画/锁/状态 |
| P7 全双工 | P2 AEC + P5 | barge-in、steer/cancel 三分 |
| P8 安全 | P4 + P5 | 权限确认、审计、红队 |
| P9 打包 | P2-P8 | Windows/Ubuntu 安装包 |
| P10 发布 | 全部 | 性能/稳定性/文档/发布 |

---

## 7. 时间估算（单人，含自测）

| WP | 天数 |
|---|---|
| WP1.1 仓库与工具链 | 0.5 |
| WP1.2 协议包 | 1.5 |
| WP1.3 Runtime 骨架 | 2.0 |
| WP1.4 模型清单/下载器 | 1.0 |
| WP1.5 DSH 插件骨架 | 2.0 |
| WP1.6 CI/文档 | 1.0 |
| 缓冲（修 CI/跨平台） | 1.0 |
| **合计** | **9.0** |

若只做“最小可评审骨架”（不含插件设置页与 CI 矩阵），可压缩到 5–6 天；但不建议跳过 G3/G4/G5 的验收。

---

## 8. P1 第一天的具体动作

1. `git switch -c feature/p1-infrastructure`（在 `dsh-voice-assistant` 内；不碰上游）。
2. 创建根 `package.json`、`pnpm-workspace.yaml`、`runtime/pyproject.toml`。
3. 先写 `packages/protocol/src/events.ts` + `binary.ts` + 测试（协议是后续所有模块的契约）。
4. 再写 `runtime/transport/protocol.py` 镜像 + conformance fixture。
5. 最后搭 Runtime daemon 与插件 RuntimeManager，打通 `runtime.ready`。
6. 当天结束前必须能跑：`pnpm --filter @dsh-voice/protocol test` 与 `uv run pytest runtime/tests/test_protocol.py`。
