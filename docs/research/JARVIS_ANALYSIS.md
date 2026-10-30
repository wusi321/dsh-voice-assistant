# GDDXX-Jarvis 源码审计报告

- 审计对象：`D:\桌面\new_idea\GDDXX-Jarvis`
- 版本 / commit：`2.0.1` / `33e6de5`（`git log -1`，分支 `main`，工作区干净）
- 审计时间：2026-10-30
- 审计方法：逐文件阅读 Python 源码、`requirements.txt`、`app/models.json`、CI 与测试脚本；只读，未修改上游任何文件。
- 证据格式：`相对路径:行号`，行号以本报告审计时的文件内容为准。
- 重要前提：本仓库为 **GPL-3.0**（`GDDXX-Jarvis/LICENSE`），下列“可复用”仅指**架构思想与行为契约可重新实现**，不是把代码复制进 `dsh-voice-assistant`。任何逐行复制都会使新项目承担 GPL-3.0 义务。

---

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 能否独立运行语音引擎？ | **不能直接独立**。`VoiceEngine`（纯音频状态机）本身不依赖 UI，但生产入口 `jarvis/service.py` 与 HUD 窗口强绑定：窗口启动服务、窗口关闭服务退出、20 s 无 HUD 连接即 `os._exit(0)`（`app/window.py:40-47`、`jarvis/service.py:594-597`）。 |
| 能否脱离 Jarvis HUD？ | 需要重写入口与传输层。`VoiceEngine` 可单独喂音频（`tests/simulate_en.py` 就是这么做的），但麦克风、TTS 播放、AEC、控制通道都在 `Service` 里，与 HUD/技能/日程/大脑耦合。 |
| 是否存在 UI 强耦合模块？ | 有：`service.py`（HUD 消息、`gesture.UI`、`tools.bind`）、`app/window.py`（进程生命周期）、`hud/js/live.js`（消息分发）。`engine.py` / `wake.py` / `wakeword.py` / `aec.py` 相对纯净。 |
| 是否有可直接抽象的 ASR/TTS 接口？ | **有，但是隐式鸭子类型**：`wake.process(frame)`、`vad.accept_waveform()`/`front`/`pop()`、`asr.text(samples)`、`speaker.synth(text)` 生成 float32 chunk。没有基类、没有统一错误类型、没有版本号。 |
| 哪些模块适合通过 Adapter 替换？ | 唤醒（openWakeWord ↔ sherpa-onnx KWS）、VAD（Silero）、ASR（Parakeet/SenseVoice ↔ 流式 Zipformer）、TTS（Piper/Kokoro ↔ 其他）、AEC（livekit APM ↔ 其他 WebRTC APM）都适合，但需要重新定义接口。 |
| GPL-3.0 的影响 | 复制/修改/链接 Jarvis 代码并以非 GPL 许可证分发，会触发 GPL 传染。**本项目只能学习其设计与参数，代码全部重写**；`piper-tts` 亦是 GPL-3.0，不能作为 MIT/Apache 项目的默认依赖。 |

---

## 1. 项目整体架构

Jarvis 是“单进程 Python 语音服务 + WebView HUD + 可选插件”的桌面应用，不是库，也不是守护进程。

- 进程入口：`python -m jarvis` → `jarvis/__main__.py:1` → `service.main()`（`jarvis/service.py:600-604`）。
- 核心链路（源码注释即架构图）：`mic -> WebRTC echo cancel -> wake word + VAD + local ASR -> command -> brain -> TTS -> speaker`，播放参考信号回灌 AEC（`jarvis/service.py:1-7`）。
- 生产启动：`app/launch.py:12-19` 先确保安装，再启动 `app/window.py`；`app/window.py:17-27` 用 `subprocess.Popen` 启动语音服务；窗口 `finally` 中 `terminate()`（`app/window.py:40-47`）。
- HUD：`hud/index.html` + 原生 JS，通过 `ws://127.0.0.1:8765` 接收状态/字幕/日程/系统信息，发送 `text`、`interrupt`、`camera`、`brain_*`、`llm_*`（`jarvis/service.py:527-566`、`docs/extend.md:45-51`）。
- 插件：`jarvis/plugins/` 下的 Python 模块，自动发现，向 LLM 暴露 OpenAI function schema（`jarvis/tools.py:19-20`、`jarvis/tools.py:55-59`）。
- 依赖：`requirements.txt` 固定了 sherpa-onnx、onnxruntime、sounddevice、livekit、piper-tts、pywebview 等；模型首次运行下载（`app/models.json`）。

**判断**：这是“应用”，不是“可嵌入的语音运行时”。要作为 Voice Runtime 复用，必须把 `Service` 拆成：`AudioDeviceLayer`、`VoicePipeline`、`Transport`、`HostAdapter` 四层，并去掉 HUD 生命周期绑定。

---

## 2. Python 入口

| 层 | 文件 | 说明 |
|---|---|---|
| 包入口 | `jarvis/__main__.py:1` | 直接 `from .service import main; main()` |
| 服务入口 | `jarvis/service.py:600-604` | 创建 `Service`，启动 `audio_loop` 线程，`asyncio.run(ws_main())` |
| 桌面入口 | `app/launch.py:1-21` | 首次安装检查，启动 `app/window.py` |
| 窗口入口 | `app/window.py:39-47` | 启动/停止语音子进程，创建 pywebview 窗口 |
| 安装入口 | `app/install.py:1-292` | venv、pip 镜像、模型下载与校验 |

没有 CLI 参数、没有 systemd/服务模式、没有 `--headless`。`JARVIS_STAY_ON=1` 可阻止“无 HUD 自动退出”（`jarvis/service.py:594`），但仍是窗口内启动。

---

## 3. 音频采集模块位置

- 采集 + 播放 + AEC 在同一个 PortAudio 双工回调：`jarvis/service.py:456-469`。
  - `sd.Stream(samplerate=48000, blocksize=480, channels=(1,1), dtype="float32", callback=self.duplex_cb)`（`jarvis/service.py:494-496`）。
  - 每次回调：从 `Player` 取 480 帧播放 → 参考信号 48k→16k 后送 AEC `playback()` → 麦克风 48k→16k 后送 AEC `capture()` → 干净音频进 `mic_q`（`jarvis/service.py:460-469`）。
  - 消费线程：`mic_q.get()` → `engine.feed(x)`（`jarvis/service.py:501-504`）。
- 降采样：`Decimator`，63 阶 FIR 抗混叠，48k→16k，10 ms 块状态连续（`jarvis/service.py:44-57`）。
- 设备：只使用系统默认输入/输出（`sd.default.device`，`jarvis/service.py:473-474`），**没有设备枚举、选择、热插拔事件**。
- 断线恢复：`audio_loop()` 捕获异常，5 s 重试，并 `sd._terminate(); sd._initialize()` 重新扫描设备（`jarvis/service.py:478-492`）；这是私有 API，跨 PortAudio 版本不保证。
- 采样率假设：**硬编码 48 kHz 双工**（`DEV_SR = 48000`，`jarvis/service.py:22`）。若设备不支持 48k（部分蓝牙耳机、USB 声卡），`sd.Stream` 直接失败，随后无限重试。
- 双工假设：`sd.Stream` 用单一设备同时开输入输出。默认麦克风与默认扬声器不是同一物理设备时，WASAPI 下通常无法打开，Jarvis 没有回退到“两个单工流 + 软件时钟对齐”。

---

## 4. 唤醒模块位置

- 英文：`jarvis/wakeword.py:13-52`，`HeyJarvis` 直接用 onnxruntime 跑 openWakeWord 的三段模型：melspectrogram、embedding、`hey_jarvis_v0.1.onnx`；80 ms chunk，score 阈值 0.25，连续命中 `patience=1`，命中后约 1.2 s 不应期（`jarvis/wakeword.py:16-21`、`jarvis/wakeword.py:33-52`）。
- 中文：`jarvis/wakeword.py:55-67`，`SherpaKws` 包装 `sherpa_onnx.KeywordSpotter`；关键词和模型在 `jarvis/models.py:19-38`（`嗨贾维斯`、`嘿贾维斯`、`贾维斯`，pinyin + tone）。
- 二次确认：KWS 命中后 0.4 s，用 ASR 转写窗口内音频，`split_wake()` 检查文本是否真的包含唤醒词；`kw_strong` 或声学分数 ≥0.6 可越过文本检查（`jarvis/engine.py:156-199`、`jarvis/wake.py:52-76`）。
- 误唤醒抑制：`NAME_LIKE` 正则、`greet_wake()` 的 “Hi <name>” 启发式、可选的声纹校验（`jarvis/engine.py:172-186`、`jarvis/wake.py:29-49`、`jarvis/engine.py:218-230`）。
- 唤醒词可配置性：**没有运行时配置**。关键词写死在 `models.py:20-24`，英文模型路径写死 `openwakeword/hey_jarvis_v0.1.onnx`（`jarvis/models.py:13`、`app/models.json:82-107`）。

**可借鉴**：KWS 快速命中 + ASR 二次确认 + 声纹/文本兜底的两级架构，以及“唤醒词必须在句首”的约束。**不可直接复用**：openWakeWord 预训练 “hey jarvis” 模型是 CC BY-NC-SA 4.0（`GDDXX-Jarvis/NOTICE.md`），不能用于可商用/通用开源发行。

---

## 5. ASR 模块位置

- 模型加载：`jarvis/models.py:58-69`。
  - 英文：sherpa-onnx `OfflineRecognizer.from_transducer`，NeMo Parakeet TDT 0.6B v2 int8。
  - 中文：`OfflineRecognizer.from_sense_voice`，SenseVoice small int8，`language="auto"`，`use_itn=True`。
- 封装：`jarvis/models.py:86-118`，`Transcriber.text(samples, mixed=False)`。
  - `mixed=True` 时先跑 SenseVoice，若汉字占比 ≥30% 直接返回（避免 Parakeet 把中文转成英文乱码）；否则跑 Parakeet，词数 ≥2 直接返回；否则用 SenseVoice 兜底（`jarvis/models.py:101-118`）。
- 调用点：`jarvis/engine.py:215-216`，每次对**完整 VAD 段**做离线识别；唤醒确认窗口 1.6-2.4 s（`jarvis/engine.py:174-175`），命令段最多 15 s（`jarvis/engine.py:288`）。
- **没有流式 ASR，没有 partial 结果**。`get_partial_result()` 在 Jarvis 中不存在；HUD 的 `speech.partial` 类事件也不存在。这是它与任务书“实时语音识别 / speech.partial”最大的差距。
- 延迟：一段话结束后 VAD `min_silence=0.45 s` 才出段，再跑离线模型；实时性由 `max_segment=15 s` 和模型大小决定。Parakeet 0.6B 在 CPU 上不是低延迟选择。

---

## 6. VAD 模块位置

- 配置：`jarvis/models.py:41-50`。
  - Silero VAD ONNX：`models-bundle/silero_vad.onnx` / `models/silero_vad.onnx`。
  - `threshold=0.5`，`min_silence_duration=0.45`，`min_speech_duration=0.15`，`window_size=512`，`max_speech_duration=8.0`，`buffer_size_in_seconds=60`。
- 驱动：`jarvis/engine.py:108-110` 每 512 样本 `accept_waveform` + `is_speech_detected`；`jarvis/engine.py:122-133` 在 VAD 非空时取段。
- 关键工程细节（值得复用其结论）：sherpa-onnx 的 `seg.start` **跨版本不可靠**，Jarvis 改用“当前时间 - min_silence”反推段尾，再按段长反推段首，并从 `ring` 缓冲补 0.25 s 前置音频（`jarvis/engine.py:126-133`、`jarvis/engine.py:209-213`）。
- 语义结束判定：任务书目标 500-1000 ms；Jarvis 用 450 ms 静音 + 段后处理，落在目标内，但代价是每段至少 450 ms 延迟。
- 打断判定另有一套“连续说话 350 ms + 音量高于回声阈值”的快速路径（`jarvis/engine.py:116-120`），不依赖 VAD 段结束。

---

## 7. TTS 模块位置

- 统一出口：`jarvis/tts.py:89-102`。
  - 英文：`PiperSpeaker`，`piper-tts` + 社区 `jarvis-high` 音色，可加“金属感”FFmpeg/numpy 效果（`jarvis/tts.py:61-86`）。
  - 中文：`Speaker`，sherpa-onnx Kokoro multi-lang v1.1，`sid=68`，24 kHz（`jarvis/tts.py:8-9`、`jarvis/tts.py:93-102`）。
- 分句：正则按 `。！？!?；;\n`、英文句号+空格、以及 12 字以上逗号切分（`jarvis/tts.py:12-14`）。每句独立合成，句内不是流式。
- 播放：`Player` 是唯一调度者，`push()` 把 24k 重采样到 48k 入队（`jarvis/service.py:60-85`、`jarvis/service.py:437-454`）。
- 取消：`player.stop()` 清空队列；`self.gen` 递增使旧合成线程在下一个 chunk 前退出（`jarvis/service.py:162-167`、`jarvis/service.py:445-449`）。`TTSEngine.cancel()` 这种接口不存在。
- 音量/语速：`Speaker` 构造参数有 `speed`、`fx`，但 `make_speaker()` 不接受配置，运行时不可调（`jarvis/tts.py:89-96`）。
- 音色：英文写死 `VOICE=68` 仅对 Kokoro 分支有效；Piper 用固定模型路径（`jarvis/models.py:15-17`、`jarvis/tts.py:8`）。

---

## 8. AEC 模块位置

- `jarvis/aec.py:1-39`，使用 `livekit.rtc.AudioProcessingModule`（WebRTC APM 封装）。
- 参数：16 kHz、10 ms（160 样本）帧，`echo_cancellation=True`、`noise_suppression=True`、`high_pass_filter=True`、`auto_gain_control=False`，`stream_delay_ms=40`（`jarvis/aec.py:10-16`）。
- 参考信号：**软件参考**，不是 WASAPI Loopback。`duplex_cb` 把即将写给扬声器的 `out` 降采样后送 `aec.playback()`（`jarvis/service.py:460-462`），因此参考与播放严格同源；这比“录回环”更可靠，也避开了 Windows WASAPI loopback / Linux monitor source 的平台差异。
- 处理：`process_reverse_stream(ref_frame)` 与 `process_stream(mic_frame)` 都是 160 样本（`jarvis/aec.py:23-38`）。
- 局限：
  - 固定 40 ms 延迟，不做延迟估计/漂移补偿；不同设备/蓝牙延迟可能远超 40 ms。
  - 双工流固定 48k，AEC 固定 16k，重采样链固定；设备不支持 48k 时整套失效。
  - 不做非线性残余回声抑制后的“双讲检测”，打断判定仍靠 VAD + 音量阈值（`jarvis/engine.py:116-120`）。
- 结论：**AEC 方案可行，但必须重写为“播放调度器提供参考帧 + 可配置延迟 + 设备实际采样率”的 Runtime 模块**；不能假设 48k/40 ms。

---

## 9. 插件接口

- 发现：`jarvis/tools.py:19-20` 扫描 `jarvis/plugins/` 下所有模块；`CORE` 是内置源（`jarvis/tools.py:19`）。
- 契约（`jarvis/tools.py:1-10`、`docs/extend.md:27-37`）：
  - `provide() -> ([(openai_tool_schema, function)], hint_text)`（必需）。
  - `wants(text) -> tool_name | None`（可选，强制某句话必须调用该工具）。
  - `bind(ctx)`（可选，拿到 `ctx.ui`、`ctx.say_alone`、`ctx.narrate`、`ctx.gen`）。
- 生命周期：`_load()` 首次导入并 `bind()`，之后缓存；没有 `start/stop/dispose`，没有热重载，没有版本协商（`jarvis/tools.py:37-52`）。
- 开关：`config.json` 的 `plugins: {name: false}`（`jarvis/config.py:83-84`）。
- 隔离：无。插件与服务同进程，可直接访问文件、网络、全局状态；没有权限模型。
- 通信：插件不直接与 HUD 通信，只能通过 `ctx.ui` 发 JSON；`ctx.say_alone` / `ctx.narrate` 控制 TTS。
- 示例：`jarvis/plugins/harness/__init__.py:98-144`（把 DSH 包成 `ask_harness` 工具）、`jarvis/plugins/demos/*.py`。

**评价**：这是“LLM 工具插件”，不是“语音引擎插件系统”。对本项目而言，`provide/bind/wants` 的轻量思路可借鉴，但 Engine Adapter 必须是强类型、可配置、可健康检查、可替换的独立接口。

---

## 10. 服务通信方式

- 传输：`websockets.serve(handler, "127.0.0.1", port)`，端口默认 8765，可用 `JARVIS_VOICE_PORT` 覆盖（`jarvis/service.py:527`、`jarvis/service.py:568`）。
- 消息：纯 JSON 文本，`{"type": ...}` 扁平结构（`jarvis/service.py:144-169`、`jarvis/service.py:527-566`）。
  - 服务 → HUD：`state`、`you`、`jarvis`、`level`、`mic`、`schedule`、`history`、`trip`、`weather`、`sys`、`brain`、`agents`、`enroll`。
  - HUD → 服务：`text`、`interrupt`、`camera`、`llm_*`、`brain_*`。
- 无认证、无 token、无版本号、无 `sessionId`、无 `sequence`、无心跳、无重连协议、无错误码；只有 localhost 绑定（`jarvis/service.py:527`）。
- 音频：**不传输**。麦克风音频在服务进程内处理，HUD 只收文本/状态。没有二进制帧，也没有“Plugin 作为客户端拉音频”的概念。
- 结论：与任务书要求的“WebSocket + JSON control + Binary PCM、版本化、认证、序列号、重连”差距很大，协议层需要从零设计。

---

## 11. 运行依赖

`GDDXX-Jarvis/requirements.txt`：

- 语音：`sherpa-onnx>=1.13`、`onnxruntime>=1.18`、`numpy`、`scipy`、`sounddevice`、`soundfile`、`livekit`（AEC）、`piper-tts`（GPL）、`imageio-ffmpeg`。
- 窗口/服务：`pywebview`、`websockets`、`psutil`、`segno`。
- 摄像头/OCR：`opencv-python-headless`、`mediapipe`（仅 Windows）、`rapidocr_onnxruntime`（仅 Windows）、`pyobjc`（仅 macOS）。
- 其他：`pycryptodome`、`requests`、`pillow`、`colorama`。
- Python 版本：README 要求 3.10+；CI 用 3.12（`.github/workflows/ci.yml:18-19`）。任务书要求 3.11，需单独验证依赖轮子。

模型（`app/models.json`）：Silero VAD、SenseVoice、Parakeet、openWakeWord、CAM++ 声纹、Piper alan/jarvis、Kokoro、中文 KWS；按 `core/en/zh` 分组，带 `size`、`sha256`、多镜像 URL、可选 `archive`/`zip`。

---

## 12. Windows 特定依赖

- `mediapipe`、`rapidocr_onnxruntime` 仅 `sys_platform == "win32"`（`requirements.txt:14-15`）。
- 摄像头使用 `cv2.CAP_DSHOW`（`jarvis/platforms/generic.py:25-27`）。
- 开机启动：Startup 文件夹 `.lnk`，PowerShell + WScript.Shell（`jarvis/platforms/win.py:11-27`）。
- 打包：Inno Setup 6（`platform/win/build.ps1`、`platform/win/jarvis.iss`）。
- 配置 ACL：`icacls /inheritance:r /grant:r user:(F)`（`jarvis/config.py:58-66`）。
- 音频：PortAudio/WASAPI 共享模式，无 WASAPI exclusive/loopback 代码。
- 窗口：WebView2（pywebview）。
- 未使用 Windows 专有的 AEC/loopback API；AEC 是跨平台软件参考。

---

## 13. Linux 兼容性

- 官方 README 只声明 macOS 12+ 与 Windows 10/11（`README.md` 顶部），**Linux 不是产品目标**。
- 但代码有 Linux 分支：
  - 数据目录 `~/.local/share/jarvis`（`jarvis/paths.py:25-27`）。
  - XDG autostart（`jarvis/platforms/generic.py:87-96`）。
  - CI 的 `test` job 在 `ubuntu-latest` 上只做 `compileall` 和 `test_brain.py`；`voice` job 在 Ubuntu 跑模型场景（`.github/workflows/ci.yml:10-46`）。
- 风险：
  - `livekit` wheel 的 Linux 预编译包可用性需实测；`piper-tts` 需要 espeak-ng 数据/共享库。
  - `pywebview` 在 Linux 需要 GTK/Qt WebKit，安装包未覆盖。
  - `sounddevice` 需要 PortAudio；`sd._terminate()/_initialize()` 是私有 API。
  - 无 systemd user unit、无 `.deb`、无 PipeWire/PulseAudio 设备枚举。
- 结论：**语音算法层可在 Linux 跑通（CI 有证据），但桌面产品层没有 Linux 支持**。本项目要支持 Ubuntu 22.04，必须自己实现设备管理、服务化与打包。

---

## 14. 可复用的代码/设计（需重写，不复制）

按价值排序：

1. **AEC 参考信号架构**：播放调度器在写出前提供参考帧，AEC 与播放同源；不依赖 WASAPI loopback（`jarvis/service.py:456-469`、`jarvis/aec.py:23-38`）。这是本项目 AEC 的正确方向。
2. **两级唤醒确认**：KWS 快速命中 → 0.4 s ASR 文本确认 → 声纹/强分数兜底（`jarvis/engine.py:156-199`）。
3. **VAD 段时间戳修正**：不信任 `seg.start`，用“当前时间 - min_silence”反推，并用 ring buffer 补前置音频（`jarvis/engine.py:126-133`、`jarvis/engine.py:209-213`）。可直接指导我们绕开 sherpa-onnx 版本差异。
4. **打断的双路径**：播放中“连续 350 ms 语音 + 高于回声阈值”快速触发；VAD 段结束后再兜底（`jarvis/engine.py:116-120`、`jarvis/engine.py:343-348`）。
5. **“停止播报 / 停止任务 / 引导任务”三分**：`stop` 与 `barge_in` 分开处理，`gen` 递增只丢弃旧回复（`jarvis/service.py:162-167`、`jarvis/engine.py:309-314`）。我们还需要在此基础上真正调用 `agent.cancel()` / `agent.steer()`。
6. **模型清单与下载校验**：JSON 注册表 + 多镜像 + size/sha256 + `.part` 断点续传 + 原子替换（`app/models.json`、`app/install.py:84-120`）。数据模型可借鉴，代码重写。
7. **测试方法**：合成麦克风 + 模拟房间回声 + 假双工声卡（`tests/simulate_en.py:1-80`、`tests/smoke_service.py:1-41`）。这是本项目集成测试的直接参考。
8. **声纹可选门控**：没有声纹时返回 `None`，不阻塞主流程（`jarvis/engine.py:218-226`）。

---

## 15. 不建议复用的代码/设计

1. **GPL 代码本身**：`engine.py`、`service.py`、`wakeword.py`、`tts.py`、`aec.py` 全部是 GPL-3.0；逐行移植会传染。
2. **`Service` 的全局单例式结构**：`tools.bind(ui=..., say_alone=..., narrate=..., gen=...)`、`gesture.UI = self.broadcast`（`jarvis/service.py:96-107`）把 UI、工具、语音、日程耦合在一个类里，无法测试、无法多实例。
3. **固定 48 kHz 双工 + 默认设备**：不满足“设备枚举/选择/热插拔/不假设 16k 硬件”的要求（`jarvis/service.py:22`、`jarvis/service.py:473-496`）。
4. **无认证的 WebSocket + 扁平 JSON**：不满足版本化、序列号、重连、错误码、安全要求（`jarvis/service.py:527-568`）。
5. **非流式 ASR + 句级 TTS**：无法满足 `speech.partial`、首字延迟 ≤1 s 的目标（`jarvis/models.py:58-118`、`jarvis/tts.py:12-14`）。
6. **`JARVIS_DEBUG_HEARD` 默认开启**：默认 `"1"` 会把识别文本打印到日志（`jarvis/engine.py:131`、`jarvis/engine.py:241`、`jarvis/engine.py:253`），违反“日志不含敏感语音内容”。我们默认必须关闭并脱敏。
7. **`sd._terminate()/_initialize()` 私有 API**：跨版本不稳定（`jarvis/service.py:489-492`）。
8. **HUD 生命周期绑定**：`window.py` 启停服务、`service.py` 无客户端 20 s 退出（`app/window.py:40-47`、`jarvis/service.py:594-597`），与“Runtime 独立运行”相反。
9. **`piper-tts` 作为默认 TTS**：GPL-3.0，且默认 `jarvis-high` 音色是非商业授权（`NOTICE.md`、`requirements.txt:8`）。
10. **openWakeWord 预训练 hey jarvis 模型**：CC BY-NC-SA 4.0，不能随通用开源项目分发（`NOTICE.md`）。

---

## 16. 需要重新实现的模块

| 模块 | 重写理由 | 新设计要点 |
|---|---|---|
| 设备管理 | Jarvis 只用默认设备、固定 48k、无双工回退 | `sounddevice` 枚举 + 设备能力查询 + 单工/双工自适应 + 热插拔 + 重连 |
| 音频图 | 采集/播放/AEC 在一个回调里，难测试 | `AudioBuffer` + `Resampler` + `CaptureStream` + `PlaybackScheduler` 分离；回调只做拷贝 |
| 唤醒 | 关键词/模型写死，模型非商用 | `WakeEngine` 接口 + 可配置关键词/模型 + sherpa-onnx KWS + 自定义模型训练流程 |
| VAD | 直接依赖 sherpa 对象模型 | `VADEngine` 接口，返回带时间戳的 `SpeechSegment`，允许 Silero/WebRTC VAD 替换 |
| ASR | 离线、无 partial | `ASREngine` 流式接口（`start_stream/accept_audio/get_partial/get_final`），优先 sherpa-onnx 流式 Zipformer |
| TTS | 句级、GPL、无 cancel | `TTSEngine` 流式接口 + 真 cancel + 统一 PCM 格式 + 许可干净的模型 |
| AEC | 固定 40 ms/48k/16k | 参考帧队列 + 可配置延迟 + 设备采样率自适应 + 双讲检测 |
| 状态机 | 4 个状态、与 UI 事件耦合 | 独立 `VoiceStateMachine`（10 状态）+ 显式转移表 + 超时/恢复 |
| 协议 | 无版本/无认证/无序列 | `VoiceEvent<T>` + JSON control + 二进制 PCM 帧 + token + 重连 |
| 测试 | 脚本式、依赖真模型 | pytest + 假音频设备 + 假引擎 + 确定性 WAV 场景 |

---

## 17. 重点问题逐条回答

### 17.1 是否可以独立运行语音引擎？

`VoiceEngine` 可以独立喂音频并产出事件，测试脚本就是这样用的（`tests/simulate_en.py:55-77`）。但“语音引擎”如果指完整链路（麦克风→唤醒→ASR→TTS→扬声器），**不能**：它由 `Service` 组装，`Service` 又由 HUD 窗口启动和杀死。

### 17.2 是否可以脱离 Jarvis HUD？

算法层可以，工程层不行。需要：
- 去掉 `window.py` 的父子进程生命周期；
- 去掉 `service.py:594-597` 的无客户端退出；
- 把 `broadcast()` 替换为可插拔 Transport；
- 把 `tools`/`schedule`/`brain` 从语音服务中拆出。

### 17.3 是否存在与 UI 强耦合的模块？

- `jarvis/service.py`：HUD 消息类型、`gesture.UI`、`tools.bind(ui=...)`、`say_alone`、字幕文本（`jarvis/service.py:96-107`、`jarvis/service.py:144-169`、`jarvis/service.py:437-454`）。
- `app/window.py`：进程生命周期。
- `hud/js/live.js`：按 `m.type` 分发，新增能力要改 HUD。
- `jarvis/engine.py` 只通过 `on_event(name, data)` 输出，**不依赖 UI**，这是可复用的边界。

### 17.4 是否存在可以直接抽象的 ASR/TTS 接口？

有“事实接口”，没有“声明接口”：
- ASR：`Transcriber.text(samples, mixed=False) -> str`（`jarvis/models.py:101`）。
- TTS：`Speaker.synth(text) -> Iterator[np.float32]`（`jarvis/tts.py:98-102`）。
- 二者都没有基类、没有异常契约、没有采样率元数据、没有取消/超时。

它们足以证明“Adapter 化是可行的”，但新项目必须定义 `ASREngine` / `TTSEngine` 抽象基类与统一 `AudioChunk`。

### 17.5 哪些模块适合通过 Adapter 替换？

- 唤醒：openWakeWord ↔ sherpa-onnx KWS ↔ 自定义 KWS。
- VAD：Silero ↔ WebRTC VAD ↔ 能量 VAD（测试用）。
- ASR：Parakeet / SenseVoice ↔ 流式 Zipformer / Whisper。
- TTS：Kokoro / Piper ↔ Edge TTS / 其他本地 TTS。
- AEC：livekit APM ↔ speexdsp ↔ 无 AEC（降级）。
- 播放：sounddevice ↔ 其他后端（测试用 FakeSink）。

### 17.6 GPL-3.0 对代码复用和发布有什么影响？

- Jarvis 整体 GPL-3.0。把其代码复制、修改、与我们的代码链接成一个作品分发，整个作品需以 GPL-3.0 发布并提供源码。
- 即使“只复制一个函数”，只要构成可版权保护的表达，仍可能侵权；不能以“改写变量名”规避。
- `piper-tts` 也是 GPL-3.0；把它作为依赖分发（即使动态链接）通常要求整个作品 GPL 兼容。
- openWakeWord 的 `hey_jarvis` 预训练模型是 CC BY-NC-SA 4.0：非商业、相同方式共享，不能用于商业发行。
- 默认 `jarvis-high` 音色是“个人非商业使用”，不能随项目分发。
- **本项目策略**：Jarvis 仅作为“行为参考与参数来源”，所有代码独立实现；默认引擎选择许可干净的组件（sherpa-onnx Apache-2.0、Silero MIT、Kokoro Apache-2.0、SenseVoice 需核对模型许可）；不引入 `piper-tts` 作为默认依赖；不下载/分发非商用模型。

---

## 18. 对本项目的直接输入（P1 之前必须落地的结论）

1. **AEC 采用“软件参考 + WebRTC APM”**，不采用 WASAPI loopback / PulseAudio monitor 作为首选；参考帧由唯一播放调度器提供。Jarvis 已验证该路径在 Windows/macOS 可用（GPL 代码不能复制，但结论可用）。
2. **设备层不能假设 48 kHz 双工**。必须先查询设备默认采样率与通道数，优先 48k 双工；失败则回退到“输入/输出两个单工流 + 环形缓冲 + 漂移补偿”，再失败才报错。
3. **ASR 必须选流式模型**，否则 `speech.partial` 无法实现；离线 SenseVoice 可作为最终结果校正/降级，但不能作为唯一 ASR。
4. **TTS 默认选 Kokoro（sherpa-onnx，Apache-2.0）或其它许可干净模型**；`piper-tts` 仅作为用户自行安装的可选后端，并在文档中标注 GPL。
5. **唤醒默认选 sherpa-onnx KWS**（中文 pinyin 关键词可配置），英文可提供自定义 KWS 模型；不默认分发 openWakeWord 的 NC 模型。
6. **日志默认不打印识别文本**；调试模式必须显式开启并做脱敏。
7. **测试直接借鉴“合成麦克风 + 模拟回声 + 假双工声卡”**，但用 pytest 组织，且不依赖真实模型即可跑核心状态机。

---

## 19. 关键证据索引

| 主题 | 证据 |
|---|---|
| 服务入口/生命周期 | `jarvis/__main__.py:1`、`jarvis/service.py:600-604`、`app/window.py:40-47`、`jarvis/service.py:594-597` |
| 双工音频 | `jarvis/service.py:22`、`jarvis/service.py:456-469`、`jarvis/service.py:494-496` |
| 降采样 | `jarvis/service.py:44-57` |
| 设备默认值 | `jarvis/service.py:473-474` |
| 设备恢复 | `jarvis/service.py:478-492` |
| AEC | `jarvis/aec.py:10-38`、`jarvis/service.py:460-462` |
| VAD | `jarvis/models.py:41-50`、`jarvis/engine.py:108-133` |
| KWS | `jarvis/models.py:19-38`、`jarvis/wakeword.py:13-67` |
| 唤醒确认 | `jarvis/engine.py:156-199`、`jarvis/wake.py:52-76` |
| ASR | `jarvis/models.py:58-118` |
| TTS | `jarvis/tts.py:12-14`、`jarvis/tts.py:61-102` |
| 播放/取消 | `jarvis/service.py:60-85`、`jarvis/service.py:162-167`、`jarvis/service.py:437-454` |
| 打断 | `jarvis/engine.py:116-120`、`jarvis/engine.py:200-207`、`jarvis/engine.py:309-314` |
| 插件 | `jarvis/tools.py:1-101`、`docs/extend.md:6-37` |
| WebSocket | `jarvis/service.py:527-568` |
| 模型清单 | `app/models.json`、`app/install.py:84-120` |
| 测试 | `tests/simulate_en.py`、`tests/smoke_service.py`、`.github/workflows/ci.yml` |
| 许可 | `GDDXX-Jarvis/LICENSE`、`GDDXX-Jarvis/NOTICE.md`、`requirements.txt:8` |
