# dsh-voice-assistant

跨平台、本地优先、支持连续对话 / 语音打断 / 桌宠联动的 DSH 语音助手。

> 当前状态：**P0 源码审计完成，P1 尚未开始**。本目录目前只有审计与计划文档，没有可运行代码。
> 所有结论以 2026-10-30 的本地源码/运行时为准；上游仓库 `GDDXX-Jarvis` 与 `dsh-pet` 保持只读。

## 先读什么

| 文档 | 内容 |
|---|---|
| [P0 最终报告](docs/P0_FINAL_REPORT.md) | 10 项交付：上游结构、可复用模块、dsh-pet 接口、DSH 真实 API、模型推荐、双平台、许可、选型调整、风险、P1 计划 |
| [Jarvis 审计](docs/research/JARVIS_ANALYSIS.md) | GDDXX-Jarvis 的音频/AEC/唤醒/VAD/ASR/TTS/插件/平台逐项分析（GPL-3.0，只读参考） |
| [dsh-pet 审计](docs/research/DSH_PET_ANALYSIS.md) | HTTP/OpenAPI、Cordis 服务、锁、动画、工作状态、TTS Provider、桌面/Web 差异 |
| [DSH API 审计](docs/research/DSH_API_ANALYSIS.md) | DSH 0.2.1-rc.3 的插件 manifest、`ctx.agents`、`agent/assistant-stream`、Session、UI Slot、确认/权限 |
| [技术选型](docs/TECH_SELECTION.md) | 依赖/模型/协议/平台选型与被否决方案 |
| [风险清单](docs/RISK_REGISTER.md) | 18 条风险、等级、缓解与关闭门 |
| [P1 计划](docs/P1_PLAN.md) | 目录结构、工作包、验收门、测试计划、9 天估算 |

## 三条硬结论

1. **DSH 以 0.2.1-rc.3 为准**：桌面 GUI 内置运行时是 0.2.1-rc.3；PATH 上的 `dsh` 是 0.1.5-rc.1，不要用它安装/验证插件。
2. **Jarvis 只能读，不能复制**：GPL-3.0；`piper-tts` 也是 GPL；openWakeWord 的 “hey jarvis” 模型是 CC BY-NC-SA 4.0。默认技术栈改用 Kokoro（Apache-2.0）+ sherpa-onnx 流式 ASR。
3. **DSH 没有 host 侧 “active session” API**：需要用 Client 的 session-scoped Slot 上报 `sessionId`，再配合固定绑定/最近活动回退。

## 下一步

按 [P1 计划](docs/P1_PLAN.md) 建立骨架；在 P1-G4 通过前不实现真实语音引擎。
