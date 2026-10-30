# DSH Voice Assistant — 最终技术选型（P0 输出）

- 状态：P0 审计结论，供 P1 基建使用
- 审计基线：DSH **0.2.1-rc.3**（桌面 GUI 内置运行时）、GDDXX-Jarvis `2.0.1`（GPL-3.0）、dsh-pet `0.3.8`（MIT）
- 原则：先满足 Windows 10/11 + Ubuntu 22.04；许可干净优先；不假设硬件采样率；不为保留原方案而强用不兼容依赖。
- 标记：✅ 已核实可用；🟡 需 P1/P2 实机验证；❌ 不采用。

---

## 1. 选型总表

| 层 | 模块 | 选择 | 版本基线 | 许可 | 平台 | 状态 |
|---|---|---|---|---|---|---|
| Runtime | 语言 | Python | 3.11.x | PSF | Win/Linux | ✅ |
| Runtime | 包管理 | uv | 最新稳定 | Apache-2.0/MIT | Win/Linux | ✅ |
| Runtime | 配置 | Pydantic v2 + pydantic-settings | 2.x | MIT | 全平台 | ✅ |
| Runtime | 音频 I/O | sounddevice（PortAudio） | 0.5.x | MIT | Win/Linux | 🟡 需双平台设备实测 |
| Runtime | 数值/重采样 | NumPy + SciPy `resample_poly` | NumPy 2.x / SciPy 1.14+ | BSD-3 | 全平台 | ✅ |
| Runtime | VAD | sherpa-onnx Silero VAD | sherpa-onnx 1.10.45（审计时 PyPI 最新；任务书写的 1.13 尚未发布，以实际可用版本为准） | Apache-2.0（代码）/ MIT（模型） | 全平台 | ✅ |
| Runtime | 唤醒 | sherpa-onnx KeywordSpotter | 同上 | Apache-2.0（代码）；模型许可待核 | 全平台 | 🟡 模型许可 |
| Runtime | ASR | sherpa-onnx **流式** Zipformer（中英） | 同上 | Apache-2.0（代码）；模型许可待核 | 全平台 | 🟡 精度/许可 |
| Runtime | ASR 兜底 | SenseVoice small int8（非流式，可选） | 同上 | **FunASR model license（非 Apache）** | 全平台 | 🟡 需法务确认，不默认捆绑 |
| Runtime | TTS | sherpa-onnx Kokoro multi-lang v1.1 | 同上 | **Apache-2.0** | 全平台 | ✅ |
| Runtime | AEC | livekit `rtc.AudioProcessingModule`（WebRTC APM） | livekit 1.2.0 | Apache-2.0 | Win x64 / Linux x64 | 🟡 需确认 Windows wheel 暴露 APM |
| Runtime | 播放调度 | 自研 `PlaybackScheduler` + sounddevice OutputStream | — | 本项目 | 全平台 | ✅ 设计 |
| Runtime | WebSocket/HTTP | FastAPI + uvicorn（或 `websockets` + 轻量 HTTP） | FastAPI 0.115+ | MIT | 全平台 | ✅ |
| Runtime | 日志 | structlog/stdlib logging + 脱敏过滤器 | — | 本项目 | 全平台 | ✅ |
| Runtime | 测试 | pytest + pytest-asyncio + numpy fixtures | 8.x | MIT | 全平台 | ✅ |
| Runtime | 质量 | Ruff + mypy（strict 可选） | 最新 | MIT | 全平台 | ✅ |
| 协议 | Schema/类型 | Zod v4（TS 源）+ JSON Schema 导出 + Python Pydantic 镜像 | Zod 4.x | MIT | 全平台 | ✅ |
| 插件 | 语言 | TypeScript strict | 5.7+ | Apache-2.0 | 全平台 | ✅ |
| 插件 | 运行时 | Node.js ≥22（DSH 0.2.1-rc.3 内置 Node 24.21） | Node 24.x | MIT | 全平台 | ✅ |
| 插件 | 包管理 | pnpm workspace | 11.x | MIT | 全平台 | ✅ |
| 插件 | 构建 | `tsc`（Host ESM）+ `esbuild`（Client IIFE） | 最新 | MIT | 全平台 | ✅ 已验证 |
| 插件 | UI | DSH Client Slot（React 由 DSH 提供） | DSH 0.2.1-rc.3 | MIT | Web/桌面 | ✅ |
| 插件 | 配置 | `@deepseek-ai/schemastery` `Config` | DSH 提供 | MIT | — | ✅ |
| 插件 | 测试 | Vitest + DSH API Mock + WS Mock | 3.x | MIT | 全平台 | ✅ |
| 目录 | 跨平台目录 | platformdirs（Python）；DSH `dshHomePath`（TS） | 4.x | MIT | 全平台 | ✅ |
| 打包 | Windows | uv/PyInstaller 或独立 Python runtime + Inno Setup | — | 各许可 | Win | 🟡 P9 |
| 打包 | Ubuntu | deb + systemd --user | — | 各许可 | Linux | 🟡 P9 |

**项目许可证建议：Apache-2.0**（含专利授权，适合基础设施；与 DSH MIT、dsh-pet MIT 兼容）。若希望最大兼容性，可用 MIT；二者都不能与 GPL-3.0 的 Jarvis 代码混合。

---

## 2. 关键取舍与理由

### 2.1 为什么 ASR 必须用流式模型

Jarvis 的 `OfflineRecognizer` 只能对完整 VAD 段转写（`jarvis/models.py:58-118`），没有 partial。任务书要求 `speech.partial`、ASR P95 ≤1.5 s、实时识别。sherpa-onnx 的 `OnlineRecognizer` 提供 `accept_waveform`、`is_ready`、`decode_stream`、`get_result`、`is_endpoint`，可以同时产出 partial 与 endpoint。选型上：

- 默认：`sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20`（中英混说；体积/精度平衡）。
- 低配：`sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23`（14M，中文，CPU 友好）。
- 英文：`sherpa-onnx-streaming-zipformer-en-20M-2023-02-17`。
- 可选二遍：SenseVoice 对最终段重打分/纠错，但**不作为默认依赖**（许可不明确）。

⚠️ 这些模型的权重许可并非都与 sherpa-onnx 代码的 Apache-2.0 相同。`app/models.json` 只记录来源，不记录模型许可；P1 的 `models/manifest.json` 必须增加 `license`、`license_url`、`commercial_use`、`redistributable` 字段，并在下载前显示。默认安装只自动下载 MIT/Apache-2.0 明确许可的模型。

### 2.2 为什么 TTS 选 Kokoro，而不是 Piper

- `piper-tts` 1.8.0 是 **GPL-3.0-or-later**（PyPI 元数据核实）。把它作为默认依赖分发，会让整个作品承担 GPL 义务，与 Apache-2.0/MIT 目标冲突。
- Kokoro multi-lang v1.1 权重是 **Apache-2.0**（Hugging Face 模型卡核实），sherpa-onnx 原生支持，24 kHz，中英混合。
- Piper 只作为“用户自行安装的可选后端”，在 `ENGINE_ADAPTERS.md` 标注 GPL，默认不安装、不分发。
- Jarvis 的 `jarvis-high` 音色是社区模型、非商业授权（`NOTICE.md`），不得复用/分发。

### 2.3 为什么 AEC 用“软件参考 + WebRTC APM”，而不是 WASAPI Loopback

- Jarvis 已在 Windows/macOS 验证：播放前把即将写出的样本送 `process_reverse_stream`，麦克风样本送 `process_stream`，参考与播放同源，无需 loopback 设备（`jarvis/service.py:456-469`、`jarvis/aec.py:23-38`）。
- WASAPI Loopback / PulseAudio monitor 受设备、驱动、采样率、时钟漂移影响，且 Linux 上 PipeWire/PulseAudio 行为不一致；作为**可选增强**，不作为首选。
- 仍需解决：设备实际延迟（蓝牙 100-300 ms）、时钟漂移、双讲检测。P2 必须做真机测试；不通过则降级为“半双工 + 按键/唤醒打断”，并在 UI 明示。

### 2.4 为什么不用 dsh-pet 的 TTS Provider 作为主播放通道

- dsh-pet 的 `voice.register` 只负责**合成 mp3 字节**，播放由宠物页面/桌面渲染端的 `HTMLAudioElement` 完成（`dsh-pet/dsh-pet/src/shared/voice.ts:151-175`），播完没有回调。
- 任务书要求“音频播放必须单一调度权威”，且 `tts.finished` / `tts.interrupted` 必须可观测。让 pet 播放会失去精确的播放状态，且与 Runtime 的 AEC 参考信号冲突。
- 结论：**Voice Runtime 独占播放**。dsh-pet 只做动画/气泡/状态。TTS Provider 注册只在“宠物独立模式、Runtime 不播放”时作为可选模式，且必须互斥。

### 2.5 为什么 Active Session 需要客户端上报

- DSH 0.2.1-rc.3 **没有 host 侧 active session API**：`ctx.agents` 只有 `get/list/roots`（`dsh-agent/lib/index.js:596-623`），`ctx.sessions` 只有 `get/list/create/fork`，没有“当前选中会话”。
- `conversation.composer.dock` / `conversation.input.right` 等 session-scoped Slot 的 standardProps 含 `sessionId`（实测 `Slots.listSubTree`），客户端插件可以拿到当前会话 ID。
- 方案：Client 半侧在 Slot 挂载时把 `sessionId` 上报给 Host 半侧（同源 HTTP 路由或 DSH Remote）；Host 维护 `activeSessionId`，并提供三种策略：
  1. `active-session`（默认）：客户端上报的当前会话；无客户端时回退到最近 `session/event` 的会话。
  2. `fixed-session`：用户配置固定 Session ID。
  3. `new-session-per-wake`：每次唤醒 `ctx.agents.create()` 新建（不推荐默认，上下文会断）。
- 这是 P5 必须实现的桥接点，不能假设 `ctx.agents.getActiveSession()` 存在。

### 2.6 为什么协议用 Zod + JSON Schema + Pydantic 镜像

- 任务书建议 TypeBox/Zod 并生成 TS 类型；Zod 已是 DSH 生态依赖（dsh-pet 使用 zod 4），团队熟悉。
- Python 侧用 Pydantic 定义同一组消息，P1 用 golden fixtures 做双向 conformance test；P4 可引入 `datamodel-code-generator` 从 JSON Schema 生成 Python 模型，消除手写漂移。
- 二进制 PCM 帧用固定 16 字节头 + little-endian PCM16，不经 JSON Base64。

---

## 3. 被否决/降级的方案

| 方案 | 结论 | 原因 |
|---|---|---|
| 直接复制 Jarvis `engine.py`/`service.py` | ❌ | GPL-3.0 传染；且与 HUD 生命周期强耦合 |
| `piper-tts` 作为默认 TTS | ❌ | GPL-3.0；与 Apache/MIT 发行不兼容 |
| openWakeWord “hey jarvis” 预训练模型 | ❌ | 模型 CC BY-NC-SA 4.0（Jarvis NOTICE），非商业 |
| Jarvis 默认 `jarvis-high` 音色 | ❌ | 个人非商业授权，不可分发 |
| WASAPI Loopback 作为唯一 AEC 参考 | ❌ | 平台差异大；软件参考更可控 |
| 用 dsh-pet 播放 TTS | ❌（默认） | 无播放完成回调；与 Runtime 单一播放权威冲突 |
| 第二套 Agent Brain / 直接调 LLM | ❌ | 违反“DSH 是唯一 Agent 执行核心” |
| PyQt/Electron 自建 UI | ❌ | 任务书要求遵循 DSH 插件 UI 技术栈 |
| JSON Base64 传持续音频 | ❌ | 带宽/延迟/GC 压力；用二进制帧 |
| 固定 48 kHz 双工 | ❌ | 设备可能只支持 44.1/16 kHz；必须探测与重采样 |
| 以 CLI `dsh` 0.1.5-rc.1 为集成目标 | ❌ | 当前 GUI 运行时是 0.2.1-rc.3；CLI 版本落后，API 可能缺失 |
| SenseVoice 作为默认 ASR | 🟡 | 模型许可是 FunASR 自定义 license，需法务确认；先作为可选 |
| 声纹门控作为默认 | 🟡 | CAM++ 模型 Apache-2.0，但增加误拒/注册复杂度；P6 可选 |

---

## 4. 平台矩阵

| 能力 | Windows 10/11 x64 | Ubuntu 22.04 x64 | 备注 |
|---|---|---|---|
| sherpa-onnx wheel | ✅ win_amd64 | ✅ manylinux x86_64 | cp311 有轮子 |
| livekit wheel | ✅ win_amd64 | ✅ manylinux_2_28 x86_64 | APM 符号需 P2 验证 |
| sounddevice/PortAudio | ✅ 内置 PortAudio DLL | 🟡 需 `libportaudio2` | 打包需带库 |
| WASAPI 共享/独占 | 🟡 | — | 默认共享；独占作为可选 |
| PulseAudio/PipeWire | — | 🟡 | 设备枚举/热插拔需实测 |
| platformdirs | ✅ | ✅ | 配置/模型目录 |
| 开机启动 | ✅ Startup .lnk | ✅ systemd --user | P9 |
| 安装包 | ✅ Inno Setup | ✅ deb | P9 |
| DSH 桌面/网页 | ✅ | ✅（dsh web） | 插件运行在 DSH 进程 |

---

## 5. 版本与依赖策略

1. **精确锁定**：`runtime/pyproject.toml` + `uv.lock` 锁定 Python 依赖；`pnpm-lock.yaml` 锁定 TS 依赖。
2. **DSH 版本探测**：插件启动时读 `ctx` 可用服务与 `@deepseek-ai/dsh/package.json` 版本；`engines.dsh`/`peerDependencies` 声明 `0.2.1-rc.3` 为已验证基线，不把 `dsh.compatibility` 当安装闸门。
3. **模型与代码分离**：模型不进 Git；`models/manifest.json` 记录 `sha256`、`size`、`license`、`license_url`、`commercial_use`、`redistributable`、`platforms`、`sample_rate`。
4. **可选引擎**：ASR/TTS/Wake/AEC 均通过 Adapter 注册；缺模型时 Runtime 仍可启动，返回 `engine_unavailable`，不崩溃。
5. **离线优先**：所有默认路径不联网；模型下载是显式用户操作。

---

## 6. 待验证清单（进入 P1/P2 前）

| ID | 事项 | 验证方法 | 阻塞阶段 |
|---|---|---|---|
| V-01 | livekit 1.2.0 Windows wheel 是否暴露 `AudioProcessingModule` 且可处理 16k/10ms | 安装 wheel，跑 `python -c` + 10 s 回声样本 | P2 |
| V-02 | sherpa-onnx 1.10.45 的 `OnlineRecognizer` API 与模型组合 | 跑官方示例 + 中文/英文 WAV | P3 |
| V-03 | KWS/ASR/TTS 模型权重许可与再分发条款 | 读模型卡/MODEL_LICENSE；记录 URL 与结论 | P1（模型清单） |
| V-04 | Windows 默认麦克风/扬声器不同设备时 PortAudio 行为 | 双设备矩阵实测 | P2 |
| V-05 | Ubuntu 22.04 PipeWire/PulseAudio 设备枚举与热插拔 | 实机 + `pactl`/`wpctl` | P2 |
| V-06 | DSH 0.2.1-rc.3 的 client slot 在桌面与 web 两种模式下的 sessionId props | 装一个最小 client 插件打印 props | P5 |
| V-07 | dsh-pet 0.3.8 在 DSH 0.2.1-rc.3 上可安装/共存（peer 版本） | 测试 profile 安装 + `/state` | P6 |
| V-08 | `agent/assistant-stream` 的 `text-delta` 与 `end` 在真实 DSH turn 中的顺序 | 订阅并记录 frame | P5 |
| V-09 | `agent.cancel` 后 `whenIdle` 与 `turn/end.reason` 的可观测性 | 构造长工具调用，取消并读 session | P7 |
| V-10 | dsh-pet `/work-status` 外部槽与内部会话状态的优先级冲突 | 同时写入两组状态，观察 `/state` | P6 |
