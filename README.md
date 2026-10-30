# dsh-voice-assistant

跨平台、本地优先、支持连续对话 / 语音打断 / 桌宠联动的 DSH 语音助手。

> 当前状态：**P2–P5 已完成（Windows 真机 + 本地模型；P5 未做真实 DSH 安装）**。
> P1 骨架、真实音频、sherpa-onnx VAD/KWS/流式 ASR/TTS、协议/认证/心跳/重连、
> Agent Bridge/Session 绑定/Assistant Stream/工具状态/TTS 输出均已实现；
> dsh-pet 联动（P6）、全双工打断（P7）尚未实现。

## 已实现

- P1：pnpm workspace + uv Python 项目；严格 TypeScript、ESLint、Vitest、Ruff、mypy、pytest。
- P2：设备枚举/选择、分离采集/播放流、有界缓冲、重采样、软件参考 WebRTC AEC、设备切换、
  打开失败 restart、Mock backend 测试；Windows 真机采集/播放验证。
- P3：`SherpaVAD`、`SherpaKWS`（中文唤醒）、`SherpaASR`（流式 partial/final）、
  `SherpaTTS`（VITS/Piper，Kokoro 路径）；TTS→VAD→ASR 与 KWS 真实模型 e2e 通过。
- P4：版本化 JSON 事件、28 字节 PCM 帧、Token 认证、心跳/空闲/认证超时、指数退避重连；
  Python + TypeScript 协议/认证/超时/重连测试。
- P5：Agent Bridge（`followup/steer/cancel/whenIdle`）、Client 上报 Session 绑定、
  `agent/assistant-stream` 分句与 TTS、`session/event` 工具状态、Runtime TTS 播报；
  未在真实 DSH 中安装验收。
- DSH 插件：Host 侧 Runtime 启停/发现/重连 + 只读状态路由；Client 侧设置页显示状态。
- Windows/Ubuntu CI 配置（Python 3.11 + Node 24；本机未运行 GitHub Actions）。

## 快速开始

```bash
pnpm install
pnpm -r build
pnpm -r test

cd runtime
uv sync --python 3.11 --extra full
uv run pytest
uv run voice-runtime probe --json
uv run voice-runtime doctor
uv run voice-runtime daemon --fake-audio
```

真实模型 e2e 需要 `DSH_VOICE_TEST_MODELS`（默认 `D:/dsh-voice-models`）和
`sherpa-onnx`；模型缺失时测试自动 skip。详见 [P3 报告](docs/P3_REPORT.md)。

Windows 下如果仓库路径包含非 ASCII 字符，见 [WINDOWS.md](docs/WINDOWS.md) 的
`PYTHONPATH` 说明；espeak/TTS 模型路径也应使用 ASCII 目录。

## 文档

| 文档 | 内容 |
|---|---|
| [P1 验收报告](docs/P1_REPORT.md) | 实际命令结果、G1–G8 状态、未验证项 |
| [P2 音频报告](docs/P2_REPORT.md) | 设备/采集/播放/重采样/切换/恢复与真机结果 |
| [P3 引擎报告](docs/P3_REPORT.md) | VAD/KWS/ASR/TTS Adapter、模型与真实 e2e |
| [P4 通信报告](docs/P4_REPORT.md) | 协议/帧/认证/心跳/超时/重连测试 |
| [P5 插件集成报告](docs/P5_REPORT.md) | Agent Bridge、Session 绑定、Assistant Stream、工具状态、TTS |
| [P1 计划](docs/P1_PLAN.md) | 目录、工作包、验收门、测试计划 |
| [架构](docs/ARCHITECTURE.md) | 三层边界、进程/线程、单一播放权威、状态分离 |
| [协议](docs/PROTOCOL.md) | 发现文件、认证、事件、二进制帧、重连 |
| [安全](docs/SECURITY.md) | localhost、token、日志脱敏、权限确认 |
| [引擎适配](docs/ENGINE_ADAPTERS.md) | Adapter 接口、模型清单与许可 |
| [Windows](docs/WINDOWS.md) / [Linux](docs/LINUX.md) | 平台安装、路径、音频待办 |
| [开发](docs/DEVELOPMENT.md) | 命令、测试、协议改动流程 |
| [路线图](docs/ROADMAP.md) | P2–P10 与验收门 |
| [P0 最终报告](docs/P0_FINAL_REPORT.md) | 审计结论、选型、风险 |
| [Jarvis 审计](docs/research/JARVIS_ANALYSIS.md) | 上游语音实现分析 |
| [dsh-pet 审计](docs/research/DSH_PET_ANALYSIS.md) | 桌宠接口与限制 |
| [DSH API 审计](docs/research/DSH_API_ANALYSIS.md) | 0.2.1-rc.3 插件/Agent/Session/UI API |

## 许可证

Apache-2.0。上游 `GDDXX-Jarvis`（GPL-3.0）、`piper-tts`（GPL-3.0）与
非商用模型均不作为默认依赖；详见 [NOTICE.md](NOTICE.md)。
