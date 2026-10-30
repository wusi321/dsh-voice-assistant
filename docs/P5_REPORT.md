# P5 DSH Plugin 集成验收报告

- 日期：2026-10-30
- 范围：Agent Bridge、Session 绑定、Assistant Stream、工具状态、TTS 输出。
- 依据：P0 审计的 DSH **0.2.1-rc.3** 真实 API；未修改 DSH 安装目录或现有 profile。
- 结果：Host 插件与 Runtime TTS 链路完成并通过 Mock/单测；**未在真实 DSH 会话中安装插件做端到端验收**（见 §6）。

## 1. Agent Bridge 映射

| Bridge 方法 | 真实 DSH API | 说明 |
|---|---|---|
| `getActiveSession()` | Client 上报的 `sessionId` + `ctx.agents.get(id)` | Host 没有 active-session API；Client `conversation.composer.dock` 的 `sessionId` 通过 HTTP 上报 |
| `sendMessage(text)` | `agent.followup(userMessage)` | 用户消息 `{ role:'user', content:[{type:'text',text}], source:{kind:'user'} }`；0.2.1 稳定 source 变体 |
| `steerMessage(text)` | `agent.steer(userMessage)` | 中途引导，不新建轮次 |
| `cancelCurrentTurn()` | `agent.cancel({kind:'user'},{keepInbox:true})` + `await agent.whenIdle()` | 对齐 DSH GUI 停止按钮；`keepInbox` 保留排队输入；有超时 |
| `subscribe(handler)` | `ctx.on('agent/assistant-stream')`、`ctx.on('session/event')`、`ctx.on('agent/error')` | 只处理绑定的 Session |

`SessionBinder` 支持：

- `active`（默认）：Client 上报的当前会话；未上报时回退到最后一个 root Agent。
- `fixed`：配置 `fixedSessionId`。
- `last`：最后一个 root/注册 Agent。

**不会静默回退**：一旦 Client 上报了某个 `sessionId` 但它已不在线，`resolve()` 返回 `undefined`，语音消息被拒绝并记录错误，而不是发给别的会话。

## 2. Session 绑定

- Client 在 `conversation.composer.dock` 注册一个零渲染 `SessionReporter`，从 Slot props 读取 `sessionId`，POST `/dsh-voice-assistant/active-session`。
- Host 路由校验 body ≤8 KiB、`sessionId` 非空，然后 `SessionBinder.setActive()`。
- 设置页显示：绑定的 session、是否 live、来源（client/fixed/last）、Agent 状态、工具名、TTS 状态。
- 这不是“新权限”，只是选择消息投递目标；Agent 仍由 DSH 创建/恢复。

## 3. Assistant Stream

`DshAgentBridge.onAssistantStream()`：

- 只处理 `frame.type === 'start' | 'chunk' | 'end'`。
- `chunk` **只接受 `text-delta`**；`reasoning-delta`、`tool-call-delta`、工具参数一律不进入 TTS。
- `end` 时 flush 残余句子。
- `SentenceSegmenter` 按中文 `。！？!?；;`、英文 `.` 后空白分句；支持最大长度切分。
- `sanitizeForSpeech` 去除代码块、行内代码、Markdown 链接/加粗、URL、标题/列表前缀。
- 每个句子通过 `TtsOutput` 发 `tts.speak`；`utteranceId` 唯一。

## 4. 工具状态

`session/event` 映射：

| Session 事件 | Agent 状态 |
|---|---|
| `turn/start` | `THINKING` |
| `tool/call` | `TOOL_RUNNING`（记录 tool name） |
| `tool/result` | `TOOL_RESULT` |
| `approval/asked` | `WAITING_CONFIRMATION` |
| `turn/end.completed` | `SUCCESS` |
| `turn/end.aborted` | `CANCELLED` |
| `turn/end.error/max-tokens` | `ERROR` |
| `turn/end.blocked` | `WAITING_CONFIRMATION` |

状态通过 `/dsh-voice-assistant/status` 暴露给设置页；P6 再映射到 dsh-pet 动画。

## 5. TTS 输出

Host：

- `TtsOutput` 只在 Runtime 已认证连接时发送 `tts.speak`；未连接时丢弃并记录，不假装成功。
- 跟踪 `tts.started/finished/interrupted`；`TtsOutput.cancel()` 发送 `tts.cancel`。
- `RuntimeManager.onEvent()` 把 Runtime 事件分发给 `TtsOutput` 和 `DshAgentBridge`。

Runtime：

- `RuntimeVoiceService` 处理 `tts.speak`/`tts.cancel`。
- 真实模式：`SherpaTTS` 合成 → `AudioIO.play()`（唯一播放权威）→ 等 scheduler 排空 → `tts.finished`。
- 无 TTS 引擎 → `runtime.error: engine_unavailable`，不静默。
- `--voice off|fake|real`：
  - `off`：默认，不加载 TTS；
  - `fake`：Fake TTS + NullAudio，供协议测试；
  - `real`：本地模型 + 真实音频设备。

## 6. 验证结果

TypeScript：

```text
pnpm -r typecheck  PASS
pnpm -r test       PASS
protocol 18 tests；plugin 34 tests
```

新增 plugin 测试：`agent-bridge` 6、`session-binder` 4、`sentence` 5、`tts-output` 3、`http` 2、`host-apply` 1；RuntimeClient/Manager 原有用例保留。

Python：

```text
uv run pytest -q   PASS（82 passed, 1 skipped）
```

新增：`test_voice_service.py`（TTS 事件/错误/cancel）、`test_voice_integration.py`（WebSocket `tts.speak` → started/finished）、`test_p5_real_tts.py`（真实 VITS 模型经 WebSocket 合成）。

真实 TTS 测试结果：`tts.started` 采样率 22 050，随后 `tts.finished`。

CLI 验证：

```text
uv run voice-runtime daemon --voice fake --port 0
auth.ok → runtime.ready → tts.started → tts.finished → shutdown
```

## 7. 未验证/限制

1. **没有在真实 DSH 0.2.1-rc.3 中安装插件并跑一次真实会话**：当前 shell 的插件安装审批被禁用，且安装会修改用户 profile。AgentBridge 使用与实际 `.d.ts`/0.2.1 实现一致的稳定 API，并以 Mock Agent 覆盖。
2. **没有真实 approval/tool 会话**：工具状态映射由 `session/event` 单测覆盖，未跑真实工具调用。
3. **没有把 ASR 结果接入 Runtime daemon**：`speech.final` 事件与 Bridge 已实现并测试，但 daemon 目前只启用 TTS，不含常驻采集/唤醒/ASR Pipeline。
4. **TTS 一次一句**：`RuntimeVoiceService` 在已有 utterance 时会先 cancel；P7 做流式/打断。
5. **无 dsh-pet 联动**：P6。
6. **无真实 DSH Session 选择 UI**：Client 上报依赖 Slot 的 `sessionId`；桌面/Web 两模式仍需真机确认。
