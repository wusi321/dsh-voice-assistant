# P4 Runtime 通信层验收报告

- 日期：2026-10-30
- 范围：版本化 JSON 控制协议、二进制 PCM 帧、Token 认证、心跳、重连、超时、事件测试。
- 结果：**通过**（Python 76 tests；TypeScript 18 protocol + 14 plugin tests）。

## 1. 协议

- `PROTOCOL_VERSION = 1`，每条 JSON 事件带 `version: 1`、`id`、`sessionId`、`sequence`、`timestamp`、`type`、`payload`。
- 事件表见 `docs/PROTOCOL.md`；Python 侧同时校验 envelope 与核心事件必填 payload 字段（`REQUIRED_PAYLOAD_FIELDS`）。
- 未知事件类型、缺失必填字段、负 sequence、错误 version 均被拒绝。

## 2. 二进制 PCM 帧

28 字节头（`VAP1`）：

```text
magic(4) | version(1) | flags(1) | headerLen(2) | sequence(4)
timestampMs(4) | sampleRate(4) | channels(2) | format(1) | reserved(1)
frameCount(4) | PCM16LE payload
```

- TypeScript 与 Python 编码字节完全一致；`test_protocol.py` 使用同一已知 hex。
- 校验 magic/version/headerLen/format/channels/frameCount/payload 长度；拒绝截断、坏头、帧数不匹配。
- WebSocket 二进制消息直接投递 `on_frame`；Python 测试覆盖有效帧与坏帧（坏帧返回 `runtime.error: invalid_message`）。

## 3. Token 认证

- Runtime 启动生成 32 字节 URL-safe token，写入 0600/ACL 发现文件。
- 首帧必须是 `auth`；`hmac.compare_digest` 常量时间比较。
- 错误 token → `auth.error: auth_failed` + close 4001。
- 协议版本不一致 → `auth.error: protocol_version_mismatch`。
- 首帧超时（默认 5 s，可配 0.5 s）→ `auth.error: auth_failed`，测试覆盖。

## 4. 心跳与超时

- Runtime 每 20 s WebSocket ping（底层），客户端应用层 `ping`/`pong` 每 10 s。
- 服务端 `idle_timeout_seconds`（默认 60 s）；超时发送 `runtime.error: timeout` 并 close 4002。
- TS `RuntimeClient` 心跳间隔 10 s、超时 5 s；未收到 `pong` 主动 close，`RuntimeManager` 触发指数退避重连。
- 连接握手超时 `connectTimeoutMs`；认证超时 `auth_timeout_seconds`。
- 测试：坏 token、版本不匹配、认证超时、空闲超时、心跳无响应。

## 5. 重连

- `RuntimeManager`：连接失败/关闭 → 指数退避（默认 500 ms → 15 s），成功后重置 attempt。
- `stop()` 清定时器、关客户端、杀子进程。
- 测试：首次 connect 失败，推进虚拟时间后第二次连接成功（`attempts === 2`，状态 connected）。

## 6. 事件测试

- Python：`parse_event` 对 `runtime.ready`/`tts.speak`/`ping` 等 envelope + payload 校验；未知类型/缺字段拒绝。
- Python WebSocket：auth.ok → runtime.ready → ping/pong → binary frame → shutdown；坏帧错误；超时关闭。
- TypeScript：auth 消息、runtime.ready、tts.speak、二进制帧、坏 magic/version/长度、心跳超时、重连。
- 跨语言：同一 PCM 帧字节在 TS/Python 测试中都断言为固定 hex。

## 7. 已知限制

1. **没有请求级 ack/超时**：`tts.speak` 等命令目前只有发送，没有逐命令响应；P5/P7 增加 `tts.started/finished` 关联与请求超时。
2. **没有 sequence gap 重传**：接收方可检测重复/缺口，但 P4 不重传；重连后以新 transport 继续。
3. **没有 TLS**：只允许 localhost；不计划远程暴露。
4. **单客户端状态**：多客户端连接时事件序列共享；多会话仲裁在 P5/P7。
5. **没有认证重放保护**：token 为长期进程 token；P8 可加 nonce/时间窗。
