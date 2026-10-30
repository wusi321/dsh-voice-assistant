# DSH Voice Assistant — 技术风险清单（P0）

- 版本：2026-10-30，基于 DSH 0.2.1-rc.3 / dsh-pet 0.3.8 / Jarvis 2.0.1
- 评级：概率（L/M/H）× 影响（L/M/H）；“阻塞门”指必须在进入下一阶段前关闭或给出降级方案。
- 每个风险必须对应一个可验证的缓解动作；不接受“以后再说”。

---

## 0. 最高优先级风险（Top 5）

| 排名 | ID | 风险 | 为什么现在必须处理 |
|---|---|---|---|
| 1 | R-01 | DSH 版本漂移（GUI 0.2.1-rc.3 / CLI 0.1.5-rc.1 / profile 0.1.5-rc.2） | 插件 API、安装器、peer 依赖全部受影响；按错版本开发会“本机可跑、用户装不上” |
| 2 | R-02 | 没有 host 侧 active session API | 任务书默认 `active-session`；不解决就无法把语音绑定到用户当前会话 |
| 3 | R-03 | 许可污染（Jarvis GPL、piper GPL、NC 模型） | 一旦复制/捆绑，整个项目无法按 Apache/MIT 发行，后期难以回滚 |
| 4 | R-04 | AEC 跨平台/延迟不确定 | 全双工与 barge-in 的核心；失败则第一版只能半双工 |
| 5 | R-05 | TTS 播放权威与 dsh-pet 冲突 | 两个播放器会导致回声、重复播报、打断失效 |

---

## R-01 DSH 版本漂移与 API 不稳定

- **证据**：桌面 GUI 内置 `0.2.1-rc.3`（`app.asar/dsh/package.json:4`）；PATH 上的 `dsh` 是 `0.1.5-rc.1`；profile `node_modules` 是 `0.1.5-rc.2`。dsh-pet 0.3.8 的 peerDependencies 要求 `^0.2.0-rc.1`。
- **概率**：H；**影响**：H；**阻塞门**：P1。
- **表现**：插件在 GUI 可加载、在 CLI 安装失败；`ctx.agents`/事件名在 0.1.5 与 0.2.1 之间缺失或语义不同；`dsh plugin add` 用错 CLI。
- **缓解**：
  1. 所有集成以 **GUI 内置运行时 0.2.1-rc.3** 为准；文档明确“不要用 PATH 上的旧 CLI 安装”。
  2. 插件 `engines.dsh`/`peerDependencies` 精确到 `0.2.1-rc.3`；启动时读版本并拒绝不兼容运行时，给出可操作错误。
  3. CI 增加 DSH 版本矩阵（至少 0.2.1-rc.3；若 0.2.1 正式版发布则加）。
  4. 只用 `cordis_inspect_list/query` 能查到的 Service/Event；不猜 API。
- **关闭标准**：在干净 profile 中用 GUI 插件管理器安装并跑通最小 host+client 插件。

---

## R-02 没有 host 侧“当前活动会话”API

- **证据**：`ctx.agents` 只有 `get/list/roots`（`dsh-agent/lib/index.js:596-623`）；`ctx.sessions` 只有 `get/list/create/fork`；全仓 grep 无 `activeSession/currentSessionId`。Client 的 session-scoped Slot 有 `sessionId` prop（`Slots.listSubTree('conversation.composer.dock')`）。
- **概率**：H；**影响**：H；**阻塞门**：P5。
- **表现**：语音消息发到错误会话；用户切换会话后语音仍发给旧会话；多窗口/多标签页时不确定。
- **缓解**：
  1. Client 半侧在 `conversation.composer.dock` 或 `conversation.input.right` 注册一个无渲染/极轻组件，读取 `sessionId` 并上报 Host。
  2. Host 维护 `activeSessionId`，并实现 `active-session / fixed-session / new-session-per-wake` 三种策略。
  3. 回退：取最近一次 `session/event` 的 session；再回退：`ctx.agents.roots()` 最后一个。
  4. 每次发送前校验 `ctx.agents.get(id)` 仍存在；不存在则报 `session_missing` 并让用户选择。
- **关闭标准**：在桌面与 web 两种模式下切换会话，语音都进入当前会话；单测覆盖回退链。

---

## R-03 许可证污染

- **证据**：Jarvis `LICENSE` 为 GPL-3.0；`piper-tts` 1.8.0 PyPI 元数据为 GPL-3.0-or-later；Jarvis NOTICE 标注 openWakeWord 预训练模型 CC BY-NC-SA 4.0、`jarvis-high` 音色非商业；SenseVoice 模型卡为 `license: other`（FunASR MODEL_LICENSE）。
- **概率**：H（如果直接复用）；**影响**：H；**阻塞门**：P1。
- **缓解**：
  1. **Clean-room**：Jarvis 只读，代码全部重写；提交记录中不出现 Jarvis 代码片段。
  2. 依赖白名单：Apache-2.0/MIT/BSD；GPL/AGPL 依赖默认拒绝，piper 仅作为“用户自装”可选后端。
  3. 模型清单增加 `license`/`commercial_use`/`redistributable`；默认只自动下载 MIT/Apache-2.0 明确许可的模型；非商用模型需用户显式确认，且不随包分发。
  4. `NOTICE.md` 记录所有第三方组件与模型来源；CI 增加 license 扫描（pip-licenses / license-checker）。
- **关闭标准**：`docs/ENGINE_ADAPTERS.md` 与 `models/manifest.json` 中每个默认依赖都有许可结论；CI license job 通过。

---

## R-04 AEC 跨平台与真实延迟不确定

- **证据**：Jarvis 固定 40 ms 延迟、48k 双工、16k AEC（`jarvis/aec.py:10-16`、`jarvis/service.py:22`），没有延迟估计/漂移补偿；`livekit` 1.2.0 有 win_amd64 轮子，但 APM 符号需实测。
- **概率**：M/H；**影响**：H；**阻塞门**：P2。
- **表现**：蓝牙耳机/不同设备下 AEC 失效；TTS 自己被当成用户说话，导致自打断；barge-in 误触发或漏触发。
- **缓解**：
  1. 软件参考（播放前样本）而非 loopback；参考队列带时间戳。
  2. 延迟估计：用已知 TTS 信号做互相关，估计 device→mic 延迟，动态设置 `stream_delay_ms`。
  3. 双讲检测：VAD + 回声残留能量比 + 近端/远端能量比，三条件确认才打断。
  4. 降级：AEC 不可用/效果差时，切半双工（TTS 期间暂停唤醒、按住说话），UI 明示。
  5. P2 在 Windows 10/11 + Ubuntu 22.04 真机跑“TTS 播放中插入用户命令”的量化测试，记录 ERLE、误打断率、漏打断率。
- **关闭标准**：两平台各 3 种设备（内置/USB/蓝牙）通过 barge-in 场景；否则第一版明确半双工。

---

## R-05 TTS 播放权威冲突（Runtime vs dsh-pet）

- **证据**：dsh-pet 的 `/voice/speak` 只合成 mp3，播放由两端 `HTMLAudioElement` 完成，无完成回调（`dsh-pet/dsh-pet/src/shared/voice.ts:151-175`）；其 `voice.register` 是单槽、后注册覆盖、不回落。
- **概率**：H（若同时启用）；**影响**：H；**阻塞门**：P6。
- **表现**：两路声音重叠；AEC 参考只覆盖 Runtime，宠物播放的声音被当成回声/用户；`tts.finished` 不准。
- **缓解**：
  1. **默认互斥**：Runtime 播放，dsh-pet 只做动画/气泡；不注册 dsh-pet TTS Provider。
  2. 提供显式“由宠物播放”模式（宠物独立运行、Runtime 不播放）；该模式下关闭 AEC/打断，UI 标注能力降级。
  3. 若未来 dsh-pet 提供播放完成回调，再评估合并；当前不假设。
- **关闭标准**：任一时刻只有一个音频输出权威；集成测试检测不到双路播放。

---

## R-06 设备采样率/双工假设失败

- **证据**：Jarvis 固定 `DEV_SR=48000`、`sd.Stream` 单设备双工（`jarvis/service.py:22`、`:496`）；只使用默认设备（`:473`）。
- **概率**：H；**影响**：M/H；**阻塞门**：P2。
- **表现**：蓝牙耳机、USB 声卡、虚拟声卡打不开 48k 双工；默认麦克风与扬声器不同设备时 `sd.Stream` 失败。
- **缓解**：
  1. 启动时枚举设备，查询 `default_samplerate`、`max_input_channels`、`max_output_channels`、hostapi。
  2. 优先同设备双工；失败则输入/输出两个单工流 + 环形缓冲 + 漂移补偿（按时间戳丢弃/插入帧）。
  3. 重采样到内部 16k，不假设硬件 16k；输出侧按设备采样率重采样。
  4. 设备热插拔：监听 `sounddevice` 异常 + 周期重扫；恢复后重建流并重置 VAD/AEC 状态。
- **关闭标准**：两平台设备矩阵（内置/USB/蓝牙/虚拟）至少各 3 种通过冷启动与拔插恢复。

---

## R-07 流式 ASR 精度/延迟不达标

- **证据**：Jarvis 用非流式 SenseVoice/Parakeet（`jarvis/models.py:58-118`），无 partial；流式 Zipformer 在中文长句/中英混说上的精度需实测。
- **概率**：M；**影响**：M/H；**阻塞门**：P3。
- **表现**：partial 抖动、最终结果错字、端点到 1.5 s 超标。
- **缓解**：
  1. 双模型策略：流式出 partial，端点后用可选二遍模型重转写最终结果（可配置）。
  2. 端点参数可调（`rule1/rule2/rule3` 静音时长）；默认 0.6-0.8 s，按场景调。
  3. 建立 100 条中文/中英混合 WAV 基准集，记录 WER/CER、首字延迟、尾字延迟。
  4. 低配模式用 14M 中文模型；高配用 bilingual。
- **关闭标准**：基准集 CER ≤ 目标值（P3 定），P95 尾字延迟 ≤1.5 s。

---

## R-08 唤醒模型许可与非商用限制

- **证据**：Jarvis 的英文 openWakeWord 模型 CC BY-NC-SA 4.0；中文 KWS 模型基于 WenetSpeech，权重许可需核实。
- **概率**：H（若默认捆绑）；**影响**：H；**阻塞门**：P1/P3。
- **表现**：项目无法商业使用/再分发；用户安装即侵权。
- **缓解**：
  1. 默认不捆绑任何 NC 模型；模型清单中显式标注 `commercial_use: false`，需用户确认后下载。
  2. 提供“自带模型”路径：用户训练/购买自己的 KWS 模型；文档给出 sherpa-onnx 微调流程。
  3. 与法务确认 WenetSpeech 派生模型条款；若不允许再分发，则只提供下载脚本，不镜像。
- **关闭标准**：默认安装路径不含 NC 模型；`models/manifest.json` 许可字段完整。

---

## R-09 DSH 插件 UI/API 变更

- **证据**：DSH 0.2.1-rc.3 仍是 rc；Slot 目录、事件签名可能变；`conversation.composer.dock`、`settings.section` 已实测存在，但不能假设永久。
- **概率**：M；**影响**：M；**阻塞门**：P5。
- **表现**：升级 DSH 后设置页空白、麦克风按钮消失、插件加载失败。
- **缓解**：
  1. Client 侧所有 Slot 注册 `try/catch` + 能力探测；失败只降级，不影响 DSH 启动。
  2. Host 侧 `inject` 最小化；缺失服务用 `ctx.get(name, false)` 软取。
  3. 版本矩阵 CI；发版前在桌面 + web 两种模式冒烟。
  4. 保留“无 UI 的纯 host 模式”，即使 Slot 全失效也能通过命令/HTTP 使用。
- **关闭标准**：DSH 升级到下一个 rc 时，冒烟测试通过或明确记录不兼容。

---

## R-10 打断语义混淆：停播 / 停任务 / 引导

- **证据**：Jarvis 只做 `player.stop()` + `gen++` 丢弃旧回复（`jarvis/service.py:162-167`），没有取消 LLM/工具；DSH `agent.cancel` 只 abort，不等待（`dsh-agent-loop/lib/index.js:815-821`），`whenIdle` 才收敛（`:870-875`）。
- **概率**：H；**影响**：H；**阻塞门**：P7。
- **表现**：用户说“停”，TTS 停了但 Agent 继续跑工具；或工具不可取消却告诉用户“已取消”。
- **缓解**：
  1. 三个独立动作：`tts.cancel`、`agent.cancel({kind:'user'})`、`agent.steer(msg)`；由意图分类器选择，默认只停播。
  2. `cancel` 后 `await agent.whenIdle()`，读 session 最后 `turn/end.reason`；若是 `aborted` 且工具仍在跑，明确告知“已停止播报，但当前工具无法中断”。
  3. 不可取消的外部操作（下载、系统安装）在 UI/语音中标注。
- **关闭标准**：集成测试覆盖三种意图与“不可取消工具”场景，播报内容与实际状态一致。

---

## R-11 确认流程被绕过 / 模糊“好”授权

- **证据**：DSH 有 `tools/pre-execute`（`PreToolDecision` 支持 allow/deny/cancel/ask）与 `approval/request`；语音是新的输入入口，不是新权限体系。
- **概率**：M；**影响**：H；**阻塞门**：P8。
- **表现**：用户说“好”就执行了任意后续危险命令；语音确认没有绑定具体操作/会话/有效期。
- **缓解**：
  1. L3 一律走 DSH 原生审批 UI（`ask`），语音只播报“需要屏幕确认”，不自动回答。
  2. 若实现语音确认，token 必须绑定 `sessionId + turn + toolCallId/args hash + operation + expiresAt`；模糊词不通过；确认语必须包含短码。
  3. 语音来源的 turn 打标（message source/metadata），guard 只对语音 turn 生效，避免影响键盘用户。
  4. 所有确认/拒绝写入脱敏审计日志。
- **关闭标准**：红队用例（“好”“可以”“都行”“你看着办”）全部不能授权 L3。

---

## R-12 WebSocket 认证/发现文件泄露

- **证据**：dsh-pet HTTP 无鉴权（`openapi.yaml:19`）；Jarvis WS 无 token（`jarvis/service.py:527`）。本项目要求更高。
- **概率**：M；**影响**：H；**阻塞门**：P4。
- **表现**：本机其他进程连接 Runtime，注入 TTS/读取转写；token 出现在日志/进程命令行。
- **缓解**：
  1. 仅绑定 `127.0.0.1`；随机端口；每次启动生成 32 字节 token。
  2. token 只写入权限 0600 的发现文件（Windows ACL 仅当前用户）；不出现在 URL/命令行/日志。
  3. WS 首帧 `auth`，失败即关闭；限制未认证连接数/超时。
  4. 日志脱敏：token、音频、转写文本默认不落盘。
- **关闭标准**：未认证连接 100% 拒绝；日志扫描无 token/转写。

---

## R-13 Python/Node 打包与安装复杂度

- **证据**：Jarvis 首次安装下载 ~1 GB 模型、创建 venv（`app/install.py`）；DSH 插件是 npm 包。用户不应为了语音装完整 Python 工具链。
- **概率**：H；**影响**：M/H；**阻塞门**：P9。
- **表现**：安装失败、PATH 冲突、模型下载慢、杀软误报。
- **缓解**：
  1. Runtime 独立安装包（Windows 用嵌入式 Python/PyInstaller；Ubuntu 用 deb + venv），插件只负责发现与启动。
  2. 模型懒下载 + 断点续传 + sha256 + 镜像；失败可重试，不阻塞 Runtime 启动。
  3. 安装器检测 VC++ Runtime/PortAudio；Ubuntu 声明 `libportaudio2` 依赖。
  4. 提供 `dsh-voice-runtime doctor` 诊断命令。
- **关闭标准**：干净 Win10/11 与 Ubuntu 22.04 各一次从零安装，≤15 分钟（不含模型下载）。

---

## R-14 长时运行稳定性/内存泄漏

- **证据**：Jarvis 环形缓冲 30 s、VAD buffer 60 s（`jarvis/engine.py:61`、`jarvis/models.py:50`）；长时间运行需验证。
- **概率**：M；**影响**：M；**阻塞门**：P10。
- **表现**：8 小时后内存增长、音频漂移、WS 断连不恢复。
- **缓解**：
  1. 所有队列有界；音频缓冲固定容量；丢弃策略显式。
  2. 8 小时 soak test + 内存/句柄/线程监控；WS 重连与心跳。
  3. 引擎可 reset/reload；模型句柄泄漏检测。
- **关闭标准**：8 小时 RSS 增长 <10%，无断流。

---

## R-15 模型下载供应链

- **证据**：Jarvis `app/models.json` 有 sha256/size/多镜像（`app/install.py:84-120`）；但并非所有条目都有 sha256（如 CAM++、jarvis-high）。
- **概率**：M；**影响**：H；**阻塞门**：P1。
- **表现**：下载被篡改/损坏；模型与清单不符；临时文件残留。
- **缓解**：
  1. 所有默认模型必须有 sha256；无 sha256 的模型不进入默认清单。
  2. 下载到临时目录 → 校验 → 原子移动；失败清理。
  3. HTTPS + 域名白名单；不支持任意 URL。
- **关闭标准**：`download_models.py --verify` 对全部默认模型通过；负向测试（坏 hash）拒绝。

---

## R-16 语音隐私（转写/录音落盘）

- **证据**：Jarvis 默认 `JARVIS_DEBUG_HEARD=1` 打印识别文本（`jarvis/engine.py:131`、`:241`、`:253`）；`debug_clips` 可录音（`jarvis/service.py:25-29`）。
- **概率**：H（若照搬）；**影响**：H；**阻塞门**：P4。
- **表现**：日志含用户原话；磁盘残留 WAV。
- **缓解**：
  1. 默认不打印转写文本；调试需显式开关并脱敏。
  2. 默认不落盘原始音频；debug clip 仅显式开启，保留上限与自动清理。
  3. 日志字段白名单；错误信息不含文本。
- **关闭标准**：默认配置下 24 h 日志扫描无用户文本/音频路径。

---

## R-17 DSH 隐藏推理/工具参数泄露到 TTS

- **证据**：`agent/assistant-stream` 同时发 `text-delta`、`reasoning-delta`、`tool-call-delta`（`dsh-agent-loop/lib/index.js:1080`、`AssistantStreamFrame`）；Jarvis 没有这种区分。
- **概率**：M；**影响**：H；**阻塞门**：P5/P7。
- **表现**：TTS 念出思维链、工具参数、内部 ID。
- **缓解**：
  1. 只消费 `text-delta`；显式忽略 `reasoning-delta` 与 `tool-call-delta`。
  2. 白名单清洗：去除 `[[...]]`、代码块、URL、路径、长数字；句子级过滤。
  3. 测试：构造含 reasoning/tool 参数的 stream，断言 TTS 队列为空。
- **关闭标准**：单元测试覆盖；真实 turn 抽检无泄露。

---

## R-18 dsh-pet 状态冲突与文档漂移

- **证据**：dsh-pet 工作状态只有 6 档（thinking/working/result/waiting/success/error），`/work-status` 是单外部槽，内部也写同一快照；文档有 3 处漂移（默认音色、`/sleep` 锁、`name` vs entry id）。
- **概率**：H；**影响**：M；**阻塞门**：P6。
- **表现**：语音状态与 Agent 状态互相覆盖；桌宠动画跳变；按文档写死参数失败。
- **缓解**：
  1. 以源码为准，不以 README/openapi 为准；集成测试直接打 `/state` 断言。
  2. 语音状态不塞进 `workStatus`；用 `lock + /anim + /broadcast` 表达 LISTENING/SPEAKING；`workStatus` 只表达 Agent 工作状态。
  3. 外部槽写入前检查当前优先级；必要时不写，避免覆盖更高优先级状态。
  4. 对 `petApi7340` 做能力探测，缺失则禁用联动。
- **关闭标准**：双状态并发场景下 Avatar 显示符合映射表；文档漂移项在代码中有注释/测试。

---

## 19. 风险与阶段映射

| 阶段 | 必须关闭/降级 |
|---|---|
| P1 | R-01、R-03、R-15、R-16（配置默认值） |
| P2 | R-04、R-06、R-13（音频/设备/诊断） |
| P3 | R-07、R-08 |
| P4 | R-12、R-16 |
| P5 | R-02、R-09、R-17 |
| P6 | R-05、R-18 |
| P7 | R-10 |
| P8 | R-11 |
| P9 | R-13 |
| P10 | R-14、R-07/R-04 的性能目标复测 |
