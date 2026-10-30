# P6 dsh-pet 集成验收报告

- 日期：2026-10-31
- 范围：PetBridge、Avatar 状态映射、动画、气泡、Lock、TTS Provider。
- 依据：本地 `dsh-pet` 0.3.8 源码与 `openapi.yaml`（只读，未修改）。
- 结果：Host 侧 PetBridge 与测试通过；**未在真实 dsh-pet + DSH 会话中做安装验收**（见 §8）。

## 1. 接口事实（源码核实）

| 能力 | 真实接口 | 关键约束 |
|---|---|---|
| 状态 | `GET /dsh-pet-7340/state` | 单一数据出口；`pets.<id>.{say,anim,position,throw,lock}` |
| 工作状态 | `POST/DELETE /dsh-pet-7340/work-status` | 6 档：thinking/working/result/waiting/success/error；外部槽 `api`；task ≤40 码点 |
| 气泡 | `POST /dsh-pet-7340/broadcast?pet=&lock=` | 只写 `say`；不生成内容；需锁（有锁时） |
| 清空气泡 | `POST /dsh-pet-7340/bubble/clear?pet=&lock=` | 只清说话气泡，不动动画/工作状态 |
| 动画 | `POST /dsh-pet-7340/anim?pet=&lock=` | `name` 或 `url` 二选一；name 必须在配置动画池；url 仅 http(s) |
| 取锁 | `POST /dsh-pet-7340/lock?pet=` `{ttl?}` | TTL 1 s–30 min，默认 120 s；实际响应含 `lockId` |
| 续期 | 同上，body 带 `{lockId,ttl}` | 旧编号过期后不能复活 |
| 释放 | `POST /dsh-pet-7340/lock/release?pet=` `{lockId}` | 用户可 `force:true` 抢占；插件不 force |
| 唤醒/睡眠 | `POST /wake` / `/sleep?pet=&lock=` | sleep 需要配置睡觉动画 |
| TTS Provider | `ctx.get('petApi7340').voice.register({id,name,synthesize})` | 单槽覆盖；mp3 `Uint8Array`；15 s；≤500 UTF-16；运行时队列 ≤3 |

`LockOn` schema 没写 `lockId`，但真实路由返回了它（`src/host/routes/interaction.ts:66`），因此 Bridge 以实际路由为准。

## 2. PetBridge

新增 `packages/plugin/src/host/pet-bridge.ts`：

- 不固定端口：优先 `petBaseUrl`，否则读取 `ctx.webServer.port` 拼 `http://127.0.0.1:<port>`。
- 启动时 `GET /state` 探测；失败每 5 s 重试；设置页显示 `disabled/unavailable/available`。
- 实现：
  - `getState()` / `refresh()`
  - `setWorkStatus(state, task)` / `clearWorkStatus()`
  - `broadcast(text, {duration, anim, image, url})`
  - `clearBubble()`
  - `playAnimation({name|url, facing})`
  - `acquireLock(ttl)` / `renewLock()` / `releaseLock()`
  - `wake()` / `sleep()`
- 所有动作失败按 dsh-pet 契约读 HTTP 200 + `{ok:false, reason}`，不以 `res.ok` 判断业务成功。
- 请求超时默认 3 s（`petBridgeTimeoutMs`），lock TTL 默认 120 s（`petLockTtlMs`）。
- `dispose` 时释放锁并清空本插件写入的外部工作状态，不留下冻结宠物。

## 3. Lock

- 气泡/动画/唤醒/睡眠/清空气泡统一走 `withLock`：先取锁，再带 `?lock=<lockId>` 调用。
- 锁在过半 TTL 时自动续期；续期失败清空本地锁并记录。
- `lock-required`/`lock-lost` 会清锁、重新取锁并重试一次。
- 用户接管（force release / 拖拽 / 点击）会让后续动作收到 `lock-lost`，插件停止占用，不抢用户。
- **Lock 不是权限边界**：它只保证第三方联动不互相打断；用户始终可抢占。

## 4. Avatar 状态映射

新增 `packages/plugin/src/host/avatar-state.ts`：

```text
Voice State + Agent State (+ TTS speaking) → Avatar State
优先级：error > waiting > working > speaking > thinking > listening > success > idle
```

关键规则：

- Agent `TOOL_CALLING/TOOL_RUNNING` → `working`，`TOOL_RESULT` → `result`。
- **即使 Voice 已 IDLE 也不会被覆盖**（Agent 工具状态优先）。
- Agent `ERROR` / `WAITING_CONFIRMATION` 最高优先。
- TTS speaking 只在 Agent 不忙时映射 `speaking`。
- `SUCCESS` 低于 listening/thinking，随后可被新一轮覆盖。
- 6 档映射到 dsh-pet `work-status`；`speaking/idle` 不写 work-status。
- `petUseWorkStatus` 可关闭，避免与 dsh-pet 自身的 DSH session 监听重复竞争。

## 5. 气泡

- `TtsOutput.onText` 把每个实际送入 Runtime 的句子通知 PetBridge。
- 气泡文本经 `sanitizeForSpeech` 清洗（去代码/URL/Markdown），不会把推理或工具参数送进气泡。
- `broadcast` 带 `anim:true`、`duration` 按文本长度 3–30 s 估算。
- 需要锁；失败只记录 warn，不影响语音主链路。

## 6. 动画

- `playAnimation` 支持名称与 http(s) URL，支持 `facing`。
- 不硬编码/伪造动画名；名称是否合法由 dsh-pet 配置池校验，返回 `unknown-animation` 时如实记录。
- 状态动画不强制由本插件播放：dsh-pet 的 `workStatus`/`whisper` 自己会触发配置动画；插件只在显式调用 `playAnimation` 时写动画叶子。

## 7. TTS Provider 适配

新增 `packages/plugin/src/host/pet-tts-provider.ts`：

- 通过 Host `petApi7340.voice.register` 注册；`id` 固定 `dsh-voice-runtime`，不占用内置 `edge`。
- 只在 `petTtsProvider=true` 时尝试注册；默认 **关闭**，因为 Voice Runtime 必须独占主播放。
- 契约：
  - 文本 `trim()` 非空且 ≤500 UTF-16；
  - 15 s 超时；
  - 必须返回非空 `Uint8Array`；
  - 校验 MP3（ID3v2 或 MPEG frame sync），否则抛错，不把 WAV/PCM 冒充 mp3；
  - 注册返回 disposer，卸载时注销；后注册覆盖先注册（dsh-pet 单槽语义）。
- 生产路径需要配置 `petTtsProviderCommand`（stdin 文本、stdout mp3）或由未来 Runtime MP3 桥注入；没有合成器时状态为 `unsupported`，**不返回伪造音频**。
- 主 TTS 播放仍由 Runtime `AudioIO` 完成；Provider 仅在“宠物独立模式、Runtime 不播放”时使用，二者互斥。

## 8. 验证结果

```text
pnpm -r typecheck  PASS
pnpm -r test       PASS
protocol 18 tests；plugin 50 tests
```

P6 新增：

- `avatar-state.test.ts` 5
- `pet-bridge.test.ts` 6
- `pet-tts-provider.test.ts` 5

覆盖：状态优先级、发送气泡前的取锁与 `lock=` 参数、动画/工作状态请求、TTS 句子触发气泡、dsh-pet 不可达降级、Provider 注册/契约/空字节/注销。

## 9. 未验证/限制

1. **没有在真实 dsh-pet 0.3.8 安装中跑 HTTP 调用**：PetBridge 使用其 OpenAPI/源码契约和 Mock fetch 测试；没有固定端口/真实宠物窗口可验收。
2. **没有真实 animation 名称/配置池**：名称合法性由 dsh-pet 校验，插件不硬编码；未跑真实动画回执。
3. **external work-status 与 dsh-pet 内部 DSH 监听可能重复**：默认开启 `petUseWorkStatus`，两者都写同一状态档；V-10 仍需真机观察优先级。
4. **TTS Provider 未接生产 MP3 合成器**：需要显式命令或 Runtime MP3 桥；默认关闭是刻意避免双播放器。
5. **没有真实用户抢占锁测试**：只验证 lock-lost 重试路径。
6. **dsh-pet 桌面 Helper/Web 双渲染差异未验证**。
