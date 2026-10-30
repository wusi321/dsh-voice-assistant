# DSH Voice Assistant — P0 源码审计最终报告

- 日期：2026-10-30（Asia/Shanghai）
- 阶段：P0 源码审计（**未进入功能实现**）
- 审计对象：
  - `GDDXX-Jarvis` @ `33e6de5`（2.0.1，GPL-3.0）
  - `dsh-pet` @ `38306ec`（0.3.8，MIT）
  - 运行中的 DSH **0.2.1-rc.3**（桌面 GUI 内置运行时）
- 上游状态：两仓库 `git status --porcelain` 为空，HEAD 未变，未修改任何上游文件。
- 产出目录：`dsh-voice-assistant/`（审计前为空目录；本阶段只新增文档，未写功能代码）。

---

## 1. 两个上游仓库的源码结构

### 1.1 GDDXX-Jarvis（GPL-3.0，macOS/Windows 桌面语音助手）

```text
GDDXX-Jarvis/
├── app/                 # launch.py / window.py / install.py / models.json
├── jarvis/              # Python 语音服务
│   ├── service.py       # 麦克风→AEC→唤醒/VAD/ASR→brain→TTS→扬声器；WS 8765
│   ├── engine.py        # 语音状态机 + 唤醒确认 + 分段 + 打断
│   ├── wakeword.py      # openWakeWord(EN) / sherpa-onnx KWS(ZH)
│   ├── wake.py          # 唤醒词文本校验（split_wake / greet_wake）
│   ├── aec.py           # livekit WebRTC APM（16k/10ms）
│   ├── tts.py           # Piper(EN) / Kokoro(ZH)，句级合成
│   ├── models.py        # sherpa-onnx 模型加载（VAD/ASR/TTS/KWS）
│   ├── brain.py         # LLM 调用（OpenAI 兼容）
│   ├── plugins/         # LLM 工具插件（harness/amap/mihome/demos/creator）
│   └── platforms/       # mac/win/generic 差异
├── hud/                 # Three.js HUD（原生 JS）
├── platform/mac|win     # 打包脚本
├── tests/               # 场景脚本（非 pytest）：simulate_en / smoke_service
└── requirements.txt
```

**核心事实**：

- 入口 `python -m jarvis` → `service.main()`（`jarvis/__main__.py:1`、`jarvis/service.py:600-604`）。
- 音频双工固定 **48 kHz / 480 帧**，只使用系统默认设备（`jarvis/service.py:22`、`:473-496`）。
- AEC 用**播放前软件参考**，不是 WASAPI loopback（`jarvis/service.py:456-469`、`jarvis/aec.py:23-38`）。
- ASR 是**非流式** `OfflineRecognizer`（Parakeet + SenseVoice），**没有 partial**（`jarvis/models.py:58-118`）。
- TTS 句级合成，播放队列可被清空，`gen` 递增丢弃旧回复（`jarvis/tts.py:12-14`、`jarvis/service.py:162-167`）。
- 插件只是“LLM 工具源”：`provide()/bind()/wants()`，无生命周期、无权限、无隔离（`jarvis/tools.py:1-101`）。
- 服务与 HUD 强绑定：窗口启动/杀死服务，20 s 无客户端即退出（`app/window.py:40-47`、`jarvis/service.py:594-597`）。
- WS 是纯 JSON、无认证/版本/序列号/心跳（`jarvis/service.py:527-568`）。

详见 [JARVIS_ANALYSIS.md](research/JARVIS_ANALYSIS.md)。

### 1.2 dsh-pet（MIT，DSH 桌宠插件）

```text
dsh-pet/
├── dsh-pet/                # 真正发布到 npm 的包根
│   ├── package.json        # dsh.bundle.patch + dsh.client
│   ├── cordis.patch.yml    # insert id=dsh-pet
│   ├── src/
│   │   ├── host/           # Cordis Host 插件、HTTP 路由、状态、锁、TTS、桌面 helper
│   │   ├── client/         # 页面 React overlay、设置页、对话面板
│   │   ├── shared/         # 两端共用纯逻辑（状态/动画/物理）
│   │   ├── standalone/     # 无 DSH 独立模式
│   │   └── app/            # Electron 独立应用
│   ├── runtime/electron-helper/  # 桌面透明窗（Electron）
│   └── assets/             # webm 动画、字体、表情包
├── API.md / CORDIS.md / openapi.yaml / CONFIG.md
└── README.md / INSTALL.md
```

**核心事实**：

- 纯展示 Avatar：不碰 `ctx.agents`、不建 Session、不 steer/cancel；它自己的“对话”走 `ctx.llm.stream` 直连模型（`dsh-pet/dsh-pet/src/host/whisper.ts:142`、`host/chat.ts:57-58`）。
- 对外唯一 HTTP 面：`/dsh-pet-7340`，挂在 DSH Web 服务，**插件层零鉴权**（`openapi.yaml:19`）；仅独立模式有进程 token。
- 数据单一出口 `GET /state`；业务失败恒 HTTP 200 + `{ok:false, reason}`（`routes/result.ts:15-46`）。
- 占用锁：per-pet 单槽，TTL 默认 120 s（1 s–30 min），懒判过期；`/anim`、`/broadcast`、`/position`、`/throw`、`/bubble/clear` 需 `?lock=`（`host/lock.ts:21-23`、`:162-175`）。
- TTS Provider：`ctx.get('petApi7340').voice.register`，单槽、后注册覆盖、返回 mp3 `Uint8Array`、15 s 超时、文本 ≤500 UTF-16、队列上限 3（`host/voice/registry.ts:39-49`、`host/voice/speak.ts:16-27`）。
- 播放不在宿主：两端各自 `HTMLAudioElement`，播完无回调（`src/shared/voice.ts:151-175`）→ 与“Runtime 单一播放权威”冲突。
- 工作状态仅 6 档（thinking/working/result/waiting/success/error），外部单槽 `'api'`，last-writer-wins（`host/work-status.ts:15`、`host/routes/state.ts:110-152`）。
- 桌面/Web 两套渲染端；桌面走私有 `dsh-pet-bridge://` + 宿主管道，第三方不可复用（`host/plugin/desktop/spawn.ts:126-137`）。
- 文档漂移 3 处：默认音色（openapi 写 XiaoxiaoNeural，实际 XiaoyiNeural）、`/sleep` 的 `?lock=` 未实现、`name='pet'` vs entry `id='dsh-pet'`。

详见 [DSH_PET_ANALYSIS.md](research/DSH_PET_ANALYSIS.md)。

### 1.3 DSH 当前安装（关键发现）

机器上有**两套 DSH**：

| 对象 | 版本 | 路径 | 用途 |
|---|---|---|---|
| 桌面 GUI 内置运行时 | **0.2.1-rc.3** | `D:\DeepSeekHarness\resources\app.asar\dsh` | **当前真正运行的 Host** |
| GUI 自带 CLI | 0.2.1-rc.3 | `D:\DeepSeekHarness\resources\runtime\cli\bin\dsh.cmd` | 应使用它安装插件 |
| PATH 上的 npm CLI | 0.1.5-rc.1 | `C:\Users\lenovo\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh` | **旧版，不要用于安装/验证** |
| profile 依赖闭包 | 0.1.5-rc.2 | `~\.dsh\profiles\node_modules\@deepseek-ai` | 只有 0.1.5 的 `.d.ts`，不是运行版本 |

**结论**：所有插件开发/验收以 **0.2.1-rc.3** 为准；按 0.1.5 写会踩 API 漂移。

---

## 2. Jarvis 可复用模块（只复用设计与行为，不复制 GPL 代码）

按价值排序：

1. **AEC 软件参考架构**：播放前样本送 `process_reverse_stream`，麦克风送 `process_stream`（`jarvis/service.py:456-469`、`jarvis/aec.py:23-38`）。这是跨平台最可控的方案。
2. **两级唤醒确认**：KWS 快速命中 → 0.4 s ASR 文本确认 → 声纹/强分数兜底（`jarvis/engine.py:156-199`）。
3. **VAD 段时间戳修正**：不信 `seg.start`，用“当前时间 − min_silence”反推，并用 ring buffer 补前置音频（`jarvis/engine.py:126-133`、`:209-213`）。
4. **打断双路径**：播放中“连续 350 ms 语音 + 高于回声阈值”快速触发；VAD 段结束后再兜底（`jarvis/engine.py:116-120`、`:343-348`）。
5. **停播/停任务/引导三分**：`stop` 与 `barge_in` 分开，`gen` 只丢旧回复（`jarvis/service.py:162-167`、`jarvis/engine.py:309-314`）。我们要在此基础上真正调用 `agent.cancel()` / `agent.steer()`。
6. **模型清单与下载校验**：多镜像、size/sha256、`.part` 断点续传、原子替换（`app/models.json`、`app/install.py:84-120`）。
7. **测试方法**：合成麦克风 + 模拟房间回声 + 假双工声卡（`tests/simulate_en.py:1-80`、`tests/smoke_service.py:1-41`）。
8. **声纹可选门控**：无声纹返回 `None`，不阻塞主流程（`jarvis/engine.py:218-226`）。

**不可复用**：`service.py`/`engine.py`/`tts.py`/`aec.py` 等 GPL 代码；固定 48k 双工、默认设备、无认证 WS、HUD 生命周期绑定、默认打印转写文本、`sd._terminate()` 私有 API。

---

## 3. dsh-pet 可调用接口（Voice Assistant 的 PetBridge 面）

| PetBridge 方法 | 真实接口 | 备注 |
|---|---|---|
| `getState()` | `GET /dsh-pet-7340/state`（支持 `since+timeout` 长轮询，≤10 s） | 单一数据出口；`counter` 变化才更新 |
| `setWorkStatus(state, task)` | `POST /dsh-pet-7340/work-status` `{state, task?}`；`DELETE` 清空 | 只接受 6 档；外部单槽 `'api'`；`task` ≤40 码点；与内部会话状态按优先级竞争 |
| `broadcast(text, opts)` | `POST /dsh-pet-7340/broadcast?pet=&lock=` | 需锁；只写气泡，不生成 |
| `playAnimation(name\|url, facing)` | `POST /dsh-pet-7340/anim?pet=&lock=` | 名字必须在配置动画池；url 必须 http(s) 且 CORS 可达；返回 `playbackId` |
| `acquireLock(ttl)` | `POST /dsh-pet-7340/lock?pet=` `{ttl?}` | 默认 120 s，1 s–30 min；取锁会唤醒宠物并打断当前点播 |
| `releaseLock(lockId)` | `POST /dsh-pet-7340/lock/release?pet=` `{lockId}` | 只有用户可 force 抢占 |
| `wake()` / `sleep()` | `POST /dsh-pet-7340/wake` / `/sleep` | sleep 需配置睡觉动画；`?lock=` 语义与文档不一致 |
| `getPlayback(id)` | `GET /dsh-pet-7340/playback/{id}?wait=&timeout=` | 唯一可靠的“动画播完”回执 |
| TTS Provider | `ctx.get('petApi7340').voice.register({id,name,synthesize})` | 仅 Host 同进程可用；单槽、覆盖、mp3 字节、15 s、≤500 字、不回落 |
| 状态订阅 | `GET /state` 轮询 / `ctx.get('petApi7340').getState()`（Client） | 无事件推送；`/state` 是唯一真相 |

**关键限制**：

- **不能从 dsh-pet 复用 Agent 能力**：没有 `ctx.agents`/Session/steer/cancel。
- **不能从 dsh-pet 获得 TTS 播放完成事件**：它不播音频；播放权威必须在 Voice Runtime。
- **不能把 LISTENING/SPEAKING 塞进 `workStatus`**：只有 6 档，且与 Agent 工作状态共用；用 `lock + /anim + /broadcast` 表达语音状态。
- **HTTP 无鉴权**：只能依赖 DSH Web 服务仅监听 localhost；不要在日志/URL 暴露 pet 端口。

---

## 4. DSH 插件真实 API（0.2.1-rc.3）

### 4.1 插件 manifest 与入口

- 没有 `plugin.json`；DSH 只读 `package.json`：
  - `dsh.bundle.patch` → `cordis.patch.yml`（Host 行）。
  - `dsh.client` → Client 半侧（`platform: "web"`、`inject` 包名、`immediately`、`external`）。
- `cordis.patch.yml` 顶层 YAML 数组；`insert` 新增行，`id` 覆盖既有行；`config` 是**整行替换**，不是深合并。
- Host 入口：`export const name/inject/Config` + `export function apply(ctx, config)`；或默认导出 Service 类。
- Client 入口：`window.__ModuleLoader__.load({ id: '<包名>', factory(require) { ... } })`；factory 返回 `{ inject, apply(ctx) }`。
- 真实样例：`dsh-video-skin`、`dsh-channel-wechat`、`dsh-experimental-voice-input-bundle`。

### 4.2 Host Context 真实服务（节选）

| 服务 | 用途 | 证据 |
|---|---|---|
| `ctx.agents` | Agent 注册表：`get/list/roots/create/resume` | `dsh-agent/lib/index.js:596-623` |
| `ctx.sessions` | Session store：`get/list/create/fork/enter/announce` | 运行时 Service 目录 |
| `ctx.sessionController` | 会话列表/恢复/发送/取消/历史/跟随 | 运行时 Service 目录；`list/resolveAgent/prompt/cancel/follow` |
| `ctx.settings` | 配置 schema 与持久化 | 运行时 Service 目录 |
| `ctx.webServer` | 注册 HTTP 路由/WS upgrade/index 注入 | `dsh-pet` 实际使用 |
| `ctx.commands` | 斜杠命令 | 运行时 Service 目录 |
| `ctx.approval` | 审批策略与请求 | 运行时 Service 目录 |
| `ctx.speechToText` | **实验性整段转录**（无流式、无 TTS） | 0.2.1 新增；`dsh-experimental-speech-to-text` |
| `ctx.slots` / `ctx.locale` | **仅 Client** | 两条独立 Cordis 树 |

### 4.3 Agent API（真实存在）

```ts
const agent = ctx.agents.get(sessionId)            // 裸 Agent | undefined
agent.followup(message)                            // 下一轮
agent.steer(message)                               // 最近 step 边界
agent.inject(message)                              // 不唤醒的模型上下文
agent.cancel({ kind: 'user' }, { keepInbox: true })// 只 abort，立即返回
await agent.whenIdle()                             // 等真正收敛
agent.status                                       // 'idle' | 'running'
agent.session                                      // Session
```

- `cancel` **无返回值、无 `agent/cancelled` 事件**；结果只能通过 `session/event` 的 `turn/end.reason.kind === 'aborted'`、`assistant/message.interrupted`、或 `agent/assistant-stream` 的 `end.outcome.kind === 'abandoned'` 观察。
- `keepInbox: true` 对齐 DSH GUI 的“停止”按钮；默认 `cancel` 会清空队列。

### 4.4 Assistant Stream（真实事件名）

- 事件：**`agent/assistant-stream`**，载荷 `{ agent, frame }`，由 `dsh-agent-loop` 发出（`R/dsh-agent-loop/lib/index.js:1079-1081`）。
- `frame`：
  - `{ type:'start', attemptId, revision, turn, step }`
  - `{ type:'chunk', attemptId, revision, index, time, chunk }`
  - `{ type:'end', attemptId, revision, index, outcome:{kind:'committed'|...}|{kind:'abandoned'} }`
- `chunk` 是 LLM `StreamChunk`：`text-delta`、`reasoning-delta`、`tool-call-delta`、`block-start/end`、`usage`、`finish`。
- **只念 `text-delta` 与 `block-end(text)`**；`reasoning-delta`（隐藏推理）与 `tool-call-delta`（内部工具参数）绝不能进 TTS。
- **没有句子边界**；DSH 不提供分句工具。必须自建 `SentenceSegmenter`（CJK 句末 + 英文句末 + 最小/最大长度 + 首句低延迟阈值）。

### 4.5 Session 事件

- `ctx.on('session/event', (session, event) => ...)`：post-commit、fire-and-forget、每个 append 都触发。
- 关键事件：`turn/start`、`turn/end`（含 `reason`）、`step/start/end`、`user/message`、`assistant/message`（含 `stream`、`interrupted?`）、`assistant/attempt`、`tool/call`、`tool/result`。
- 播报双通道：`agent/assistant-stream` 做低延迟增量，`session/event` 的 `assistant/message` 做最终一致性（防漏句/断线重连）。

### 4.6 UI

- `settings.section`：Settings 侧栏的一个页面（推荐用于 17 项设置）。
- `conversation.composer.dock` / `conversation.input.right`：会话级控件（麦克风按钮、状态条）。
- Session-scoped Slot 的 standardProps **含 `sessionId`**（实测 `Slots.listSubTree`）——这是实现“当前活动会话”的关键。
- `webserver/index-inject`：无需 Client 插件的轻量视觉注入（悬浮球/波形条），但拿不到 Cordis 服务。

### 4.7 明确不存在/待验证

**不存在**：

- `ctx.agents.getActiveSession()` / `currentSessionId`（两版都没有）。
- `assistant-stream` / `session/assistant-stream` 事件名（正确是 `agent/assistant-stream`）。
- `agent/turn-start` / `agent/turn-end` / `agent/message`（这些是 session 事件）。
- `agent/cancelled` / `cancel()` 返回值。
- 插件级 `permissions` 清单字段（权限是 session 级 sandbox + approval）。
- DSH 内置 TTS 服务（只有整段 STT，无语音合成）。
- 句子边界 / 分句工具。

**待验证**：

- `ctx.speechToText` 的精确 provider 参数类型（0.2.1 无 d.ts）。
- approval answerer 的公开注册 API（语音代答审批；不建议 P1 做）。
- `plugins.bundle.config` Slot 的声明方与稳定键。
- `agent/assistant-stream` 在真实 turn 中的帧顺序/丢帧行为（P5 用真实会话采一遍）。

详见 [DSH_API_ANALYSIS.md](research/DSH_API_ANALYSIS.md)。

---

## 5. sherpa-onnx 模型推荐

| 用途 | 模型 | 语言/任务 | 许可 | 状态 |
|---|---|---|---|---|
| VAD | `silero_vad.onnx`（sherpa-onnx 发行） | 语音活动检测 | **MIT** | ✅ 默认 |
| 唤醒（中） | `sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01` | 中文 KWS，pinyin 关键词可配 | 代码 Apache-2.0；**权重许可待核** | 🟡 默认候选 |
| 唤醒（英） | `sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01` | 英文 KWS | 代码 Apache-2.0；**权重许可待核** | 🟡 候选 |
| 流式 ASR（中英） | `sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20` | 中英混说，partial + endpoint | 代码 Apache-2.0；**权重许可待核** | 🟡 默认候选 |
| 流式 ASR（低配中） | `sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23` | 中文，14M，CPU 友好 | 同上 | 🟡 低配 |
| 流式 ASR（英） | `sherpa-onnx-streaming-zipformer-en-20M-2023-02-17` | 英文，20M | 同上 | 🟡 候选 |
| TTS | `kokoro-multi-lang-v1_1`（sherpa-onnx） | 中英，24 kHz，多音色 | **Apache-2.0** | ✅ 默认 |
| 可选二遍 ASR | SenseVoice small int8 | 中英日韩粤，非流式 | **FunASR model license（非 Apache）** | 🟡 需法务，不默认捆绑 |
| 可选声纹 | 3D-Speaker CAM++ | 说话人验证 | Apache-2.0 | 🟡 P6 可选 |

**明确不推荐**：

- openWakeWord 预训练 `hey jarvis`：模型 CC BY-NC-SA 4.0（Jarvis NOTICE），非商业。
- Piper `jarvis-high` 音色：个人非商业，不可分发。
- `piper-tts` 作为默认依赖：GPL-3.0-or-later（PyPI 1.8.0 元数据核实）。
- Parakeet TDT 0.6B：0.6B 参数、非流式，CPU 延迟不适合常驻。
- SenseVoice 作为唯一/默认 ASR：许可不明确，且非流式。

**模型管理要求**：

- `models/manifest.json` 必须记录 `license`、`license_url`、`commercial_use`、`redistributable`、`sha256`、`size`、`platforms`、`sample_rate`。
- 默认只自动下载 MIT/Apache-2.0 明确许可的模型；非商用模型需用户显式确认，且不随包分发。
- 不把模型提交 Git；下载到临时目录 → 校验 → 原子移动。

---

## 6. Windows/Linux 兼容性

| 能力 | Windows 10/11 x64 | Ubuntu 22.04 x64 | 结论 |
|---|---|---|---|
| sherpa-onnx | ✅ win_amd64 wheel（cp311） | ✅ manylinux x86_64 | P1 锁定版本 |
| livekit（AEC） | ✅ win_amd64 wheel；**APM 符号待验证** | ✅ manylinux_2_28 wheel | P2 真机验证 |
| sounddevice/PortAudio | ✅ 自带 PortAudio DLL | 🟡 需 `libportaudio2` | 安装器声明依赖 |
| 默认设备双工 | 🟡 WASAPI 共享模式；不同设备可能打不开 | 🟡 PulseAudio/PipeWire 行为差异 | 必须实现单工回退 |
| 设备热插拔 | 🟡 需实测 | 🟡 需实测 | P2 |
| 开机启动 | ✅ Startup `.lnk` | ✅ systemd --user | P9 |
| 安装包 | ✅ Inno Setup | ✅ deb | P9 |
| DSH 插件 | ✅ 桌面 GUI | ✅ `dsh web` | 两模式都要冒烟 |
| 采样率 | ❌ 不能假设 48k/16k | ❌ 不能假设 | 必须探测 + 重采样 |

**Jarvis 的 Linux 参考价值有限**：README 只声明 macOS/Windows；Linux 只有 `paths.py` 回退、XDG autostart 和 CI 的语音脚本，没有桌面产品支持、没有设备枚举、没有 systemd/deb。

---

## 7. GPL / MIT 许可证注意事项

| 组件 | 许可 | 对本项目的影响 |
|---|---|---|
| GDDXX-Jarvis 代码 | **GPL-3.0** | 不能复制/修改/链接进 Apache/MIT 项目；只能学习设计与参数，代码全部重写。 |
| `piper-tts` | **GPL-3.0-or-later** | 不能作为默认依赖分发；只能作为用户自行安装的可选后端，并明确标注 GPL。 |
| openWakeWord 预训练模型 | **CC BY-NC-SA 4.0** | 非商业、相同方式共享；不能随通用开源项目分发。 |
| Jarvis `jarvis-high` 音色 | 个人非商业 | 不能分发/商用。 |
| SenseVoice 权重 | **FunASR model license**（`license: other`） | 需法务确认；不作为默认依赖。 |
| KWS/流式 ASR 权重 | 待核实（WenetSpeech/GigaSpeech 派生） | 默认下载前必须核实；不能假设 Apache-2.0。 |
| Kokoro 权重 | **Apache-2.0** | 可默认。 |
| Silero VAD | **MIT** | 可默认。 |
| dsh-pet | **MIT** | 可作为联动目标；仍以其实际 API 为准。 |
| DSH | **MIT** | 插件按其 API 开发；不改上游。 |

**发行策略**：

- 项目代码建议 **Apache-2.0**（专利授权，适合基础设施），与 DSH/dsh-pet MIT 兼容。
- `NOTICE.md` 逐个记录第三方组件/模型来源与许可。
- CI 增加 license 扫描，默认拒绝 GPL/AGPL；例外必须有书面理由。
- 模型许可与代码许可分离；不把“代码 Apache-2.0”误写成“模型也可商用”。

---

## 8. 技术选型调整建议（相对任务书初稿）

| 任务书初稿 | 审计后建议 | 原因 |
|---|---|---|
| AEC 优先 WASAPI Loopback / PulseAudio Monitor | **软件参考 + WebRTC APM**；loopback 仅可选 | Jarvis 已验证；跨平台可控；避免设备/驱动差异 |
| Piper TTS | **Kokoro（Apache-2.0）默认**；Piper 仅可选 | Piper GPL-3.0；Kokoro 许可干净且 sherpa-onnx 原生支持 |
| 离线 ASR（SenseVoice/Parakeet） | **流式 Zipformer 默认**；SenseVoice 可选二遍 | 必须有 partial/endpoint；Parakeet 0.6B 太重 |
| `active-session` 直接取 DSH 当前会话 | **Client Slot 上报 + 固定绑定 + 最近活动回退** | Host 无 active session API |
| dsh-pet 作为 TTS Provider/播放通道 | **Runtime 独占播放**；pet 只做动画/气泡 | pet 播放无完成回调；双播放器冲突 |
| `plugin.json` 作为插件清单 | **package.json 的 `dsh` 字段 + cordis.patch.yml** | DSH 不读 plugin.json |
| 固定 48 kHz 双工 | **设备能力探测 + 单工回退 + 重采样** | 硬件不保证 48k/双工 |
| JSON Base64 传音频 | **JSON control + 二进制 PCM 帧** | 延迟/带宽/GC |
| Python 3.11 + FastAPI | **保留**；`uv` + Pydantic v2 + FastAPI/uvicorn | 与任务书一致；依赖轮子可用 |
| TypeScript + Vitest | **保留**；Zod v4 + JSON Schema + Pydantic 镜像 | 协议单一来源，跨语言契约测试 |
| 直接以 0.1.5 插件 API 开发 | **以 DSH 0.2.1-rc.3 为准** | 当前 GUI 运行版本；0.1.5 缺 `speechToText`/`configForms` 等 |

---

## 9. 主要风险（Top 8，完整 18 条见 RISK_REGISTER.md）

| ID | 风险 | 影响 | 缓解 | 关闭门 |
|---|---|---|---|---|
| R-01 | DSH 版本漂移（GUI 0.2.1-rc.3 / CLI 0.1.5-rc.1） | 插件装不上/API 缺失 | 以 GUI 为准；peer 精确；CI 版本矩阵；用 GUI 自带 CLI | P1 |
| R-02 | 无 host 侧 active session API | 语音绑错会话 | Client Slot `sessionId` 上报 + 固定绑定 + 最近活动回退 | P5 |
| R-03 | 许可污染（Jarvis GPL / piper GPL / NC 模型） | 无法按 Apache/MIT 发行 | Clean-room；依赖白名单；模型许可门控；CI license 扫描 | P1 |
| R-04 | AEC 跨平台/延迟不确定 | 全双工失败 | 软件参考 + 延迟估计 + 双讲检测 + 半双工降级 | P2 |
| R-05 | TTS 播放权威冲突 | 双路声音/打断失效 | Runtime 独占播放；pet 只动画；显式互斥模式 | P6 |
| R-06 | 设备采样率/双工假设失败 | 无声/打不开设备 | 能力探测、单工回退、重采样、热插拔 | P2 |
| R-07 | 流式 ASR 精度/延迟不达标 | partial 抖动/尾字超时 | 双模型、端点可调、基准集、低配模型 | P3 |
| R-10 | 停播/停任务/引导语义混淆 | 假取消/工具继续跑 | 三动作分离；`whenIdle` + `turn/end` 确认；不可取消明示 | P7 |

其他：R-08 唤醒模型 NC；R-09 DSH UI/API 变更；R-11 确认绕过；R-12 WS 认证；R-13 打包；R-14 长稳；R-15 模型供应链；R-16 语音隐私；R-17 隐藏推理泄露；R-18 dsh-pet 状态冲突。

---

## 10. P1 具体开发计划（摘要）

**目标**：建立可构建、可测试、可安装的最小骨架；不实现真实语音引擎。

**范围**：

1. Monorepo（pnpm workspace + uv）+ 严格 TS/Python + CI（Windows/Ubuntu）。
2. `packages/protocol`：`VoiceEvent<T>`、全事件枚举、二进制 PCM 帧、错误码、Zod schema、JSON Schema 导出。
3. `runtime/`：daemon CLI（doctor/daemon --fake-audio）、Pydantic 配置、platformdirs、发现文件（0600/ACL）、WS 首帧 token 认证、心跳、优雅退出、AudioBuffer/Resampler/DeviceManager 骨架、引擎基类、状态机骨架。
4. `models/manifest.json` + `download_models.py`：sha256/断点续传/原子移动/许可确认；P1 只放 Silero + Kokoro，不下载大模型。
5. `packages/plugin`：Host（RuntimeManager 启停/发现/重连、EventRouter、Config）+ Client（settings.section 显示 Runtime 状态）；安装到 DSH 0.2.1-rc.3 测试 profile。
6. 文档：ARCHITECTURE / PROTOCOL / SECURITY / ENGINE_ADAPTERS / WINDOWS / LINUX / DEVELOPMENT / ROADMAP。

**验收门**：

- G1 两平台构建通过。
- G2 lint/typecheck/test 全绿；核心覆盖率 ≥70%。
- G3 Runtime 独立启动、认证、心跳、优雅退出。
- G4 DSH 0.2.1-rc.3 中插件加载、设置页可见、能启停 fake runtime。
- G5 协议 JSON + 二进制 round-trip；版本不匹配拒绝。
- G6 模型清单 schema + 下载器负向测试。
- G7 未认证连接拒绝；日志无 token/转写。
- G8 文档齐全且无“stub 当完成”。

**明确不做**：真实麦克风/播放、VAD/ASR/TTS、AEC、Agent 消息发送、dsh-pet 联动、17 项完整设置页、安装包。

详见 [P1_PLAN.md](P1_PLAN.md)。

---

## 11. 本次审计的边界与未验证项

**已核实**：

- 两上游仓库 HEAD/工作区干净；未修改。
- Jarvis 的音频/AEC/唤醒/VAD/ASR/TTS/插件/平台/测试结构（逐文件）。
- dsh-pet 的 HTTP/OpenAPI/Cordis 服务/锁/动画/工作状态/TTS Provider/桌面模式。
- DSH 0.2.1-rc.3 的插件 manifest、`ctx.agents`、`agent/assistant-stream`、`session/event`、`cancel/steer`、Slot 目录、speechToText 边界。
- 运行中 Host 的 Service 目录、Event 目录、三个关键 Slot 的注册签名与 `sessionId` standardProp。

**未验证（P1/P2 必须做）**：

1. livekit 1.2.0 Windows wheel 是否暴露 `AudioProcessingModule` 且可处理 16k/10ms。
2. Windows 默认麦克风/扬声器不同设备时 PortAudio 行为；Ubuntu PipeWire/PulseAudio 设备枚举与热插拔。
3. KWS/流式 ASR 权重许可与再分发条款（WenetSpeech/GigaSpeech 派生）。
4. SenseVoice 的 FunASR model license 是否允许商用/再分发。
5. dsh-pet 0.3.8 在 DSH 0.2.1-rc.3 上的实际安装/共存（peer 版本）。
6. `agent/assistant-stream` 在真实 turn 中的帧顺序/丢帧；`cancel` 后 `whenIdle` 的实际收敛时间。
7. DSH Desktop 的 `DSH_PROFILE=desktop` 下插件安装/加载的完整流程（P1 G4）。
8. 任何“性能目标”（唤醒 ≤800 ms、ASR ≤1.5 s、打断 ≤500 ms）——P0 没有跑真实音频，不能声称达标。

---

## 12. 结论

1. **P0 的三个分析文档已完成**，所有关键结论有源码/类型/运行时证据，未伪造 API。
2. **项目可以进入 P1**，但必须先解决 DSH 版本基线（0.2.1-rc.3）、许可门控、AEC/设备 spike 三件事。
3. **架构主线成立**：Python Voice Runtime 独立运行 + DSH 作为唯一 Agent 核心 + dsh-pet 作为 Avatar；三者通过版本化协议/HTTP 解耦。
4. **最大的工程风险不是算法，而是版本与许可**：DSH rc 漂移、Jarvis GPL、Piper GPL、NC 唤醒模型。P1 必须用 CI 和模型清单把这些“锁死”。
5. **第一版最小闭环**应是：唤醒 → 流式 ASR → DSH Session followup → assistant-stream 分句 → Kokoro TTS → Runtime 播放 → dsh-pet 动画；AEC/barge-in 作为 P7 增强，不阻塞闭环。
