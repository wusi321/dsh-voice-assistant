# dsh-voice-assistant

跨平台、本地优先、支持连续对话 / 语音打断 / 桌宠联动的 DSH 语音助手。

> 当前状态：**P1 基础工程已完成**。协议、Runtime 骨架、DSH 插件骨架、CI 已可运行；
> 真实麦克风 / 唤醒 / VAD / ASR / TTS / AEC 尚未实现（P2/P3）。

## 已实现（P1）

- pnpm workspace + uv Python 项目；严格 TypeScript、ESLint、Vitest、Ruff、mypy、pytest。
- `@dsh-voice/protocol`：版本化 `VoiceEvent`、错误码、28 字节二进制 PCM 帧头。
- `voice-runtime`：配置校验、发现文件（0600/ACL）、token 认证、WebSocket 握手、心跳、
  优雅退出、音频环形缓冲、流式重采样、Voice 状态机、Engine Adapter 接口与 fake。
- DSH 插件：Host 侧 Runtime 启停/发现/重连 + 只读状态路由；Client 侧设置页显示状态。
- Windows/Ubuntu CI（Python 3.11 + Node 24）。

## 快速开始

```bash
pnpm install
pnpm -r build
pnpm -r test

cd runtime
uv sync --python 3.11
uv run pytest
uv run voice-runtime doctor
uv run voice-runtime daemon --fake-audio
```

Windows 下如果仓库路径包含非 ASCII 字符，见 [WINDOWS.md](docs/WINDOWS.md) 的
`PYTHONPATH` 说明。

## 文档

| 文档 | 内容 |
|---|---|
| [P1 验收报告](docs/P1_REPORT.md) | 实际命令结果、G1–G8 状态、未验证项 |
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
