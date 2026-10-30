# P3 语音引擎验收报告

- 日期：2026-10-30
- 范围：统一 Adapter；本地模型 VAD/KWS/流式 ASR/TTS；中文端到端测试。
- 结果：**TTS、VAD+流式 ASR、KWS 的中文端到端测试通过**（本机 Windows，真实模型）。
- 未实现：Agent/DSH 回合接线（P5）、全双工打断（P7）。

## 1. 统一 Adapter

| Adapter | 文件 | 模型/实现 |
|---|---|---|
| `SherpaVAD` | `engines/sherpa_vad.py` | Silero VAD（512-sample window，flush，segment 提取） |
| `SherpaKWS` | `engines/sherpa_kws.py` | sherpa-onnx KeywordSpotter + WenetSpeech 3.3M，中文 pinyin 关键词 |
| `SherpaASR` | `engines/sherpa_asr.py` | sherpa-onnx 流式 Zipformer 中文 14M，partial + final |
| `SherpaTTS` | `engines/sherpa_tts.py` | VITS/Piper（测试）；Kokoro（默认候选，代码路径已实现） |
| `EngineManager` | `engines/manager.py` | 每种引擎单例注册、初始化、健康、关闭 |
| `SherpaModels` | `engines/models.py` | 模型根发现、目录/文件校验、Windows ORT DLL 准备 |
| `factory.py` | `engines/factory.py` | fake 或真实 sherpa 引擎组装 |

所有适配器实现 `engines/base.py` 的接口；Session/Pipeline 不直接 import sherpa SDK。

## 2. 本地模型与校验

模型放在 `D:\dsh-voice-models`（ASCII 路径，避免 Windows espeak 非 ASCII 路径问题）。仓库 `models/manifest.json` 的 `candidates` 记录了测试模型的 SHA256/大小/许可状态；它们**不进入默认自动下载**。

| 用途 | 目录/文件 | 归档 SHA256 | 许可状态 |
|---|---|---|---|
| VAD | `silero_vad.onnx` | `9e2449e...1fd6` | MIT |
| KWS | `sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01` | `b2f7c896...f35f` | 权重待核，禁止再分发 |
| ASR | `sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23` | `2cbd71b6...ba8b` | 权重待核，禁止再分发 |
| TTS（测试） | `vits-piper-zh_CN-huayan-medium` | `dbdfec42...ce6b` | Piper 模型卡待核 |

Kokoro 仍是默认推荐（Apache-2.0），但本次没有下载（348 MB，镜像多次截断）；TTS e2e 使用 VITS/Piper。`SherpaTTS` 同时支持 Kokoro 配置路径，但**Kokoro 未实测**。

## 3. 端到端测试

`runtime/tests/test_sherpa_e2e.py`，在模型存在且安装 `sherpa-onnx` 时运行；否则 skip。

```text
uv run pytest -q tests/test_sherpa_e2e.py
3 passed
```

1. **TTS**：`SherpaTTS` 生成“你好，这是语音测试。”，采样率 22 050 Hz，音频长度 >0.5 s，峰值 >0.01。
2. **VAD → 流式 ASR**：TTS 生成“你好，请打开台灯。”→ 重采样 16 kHz → `SherpaVAD` 512 样本窗口 → 1 个语音段 → `SherpaASR` 分块 feed，产生多个 partial；最终文本为 `你好请大开台台灯`（含“台灯”）。
3. **中文唤醒**：TTS 生成“你好军哥。”→ `SherpaKWS` 检测到命中（关键词来自模型自带 `keywords.txt`，需尾部静音）。

关键实现细节：

- VAD 必须按 **512 样本**窗口喂入；整段 `accept_waveform` 只会得到错误段。
- KWS 需要尾部静音才会 emit；测试补 1 s 静音。连续麦克风流天然带静音。
- ASR 分块 1 600 样本（100 ms）；`get_partial_result()` 每次 decode 后更新；`get_final_result()` 补 0.6 s 静音并 `input_finished()`。
- TTS 的 `generate()` 是阻塞调用，Adapter 用 `asyncio.to_thread`；chunk 200 ms，支持 `cancel()`。

## 4. Windows ONNX Runtime 兼容

`sherpa-onnx 1.13.8` 需要 ONNX Runtime API 28；本机 PATH 中存在旧 ORT 1.17 时会出现：

```text
The requested API version [28] is not available, only API versions [1, 17] ...
```

修复：

- 安装 `onnxruntime>=1.22`（`full` extra 已包含 1.31.1）。
- `engines/models.py:prepare_sherpa_runtime()` 在 import sherpa 前调用 `os.add_dll_directory(<onnxruntime>/capi)`。
- 不需要把 DLL 复制到 `sherpa_onnx/lib`。

## 5. 已知限制

1. **Kokoro 未实测**；VITS/Piper 仅用于测试。Kokoro 的 `OfflineTtsKokoroModelConfig` 代码路径需要在下载后单独验证。
2. **KWS 权重许可未清**：测试模型只在本机使用，未进入默认下载/分发。
3. **ASR 是中文 14M**：不支持中英混说；bilingual Zipformer 487 MB 未下载。
4. **无 Agent 接线**：Adapter 目前由测试/未来 Pipeline 调用；P5 才接 DSH `agent.followup`/`assistant-stream`。
5. **无全双工**：没有 AEC 真机打断测试；P7。
6. **无模型热切换/并发推理**：EngineManager 单例，未做多会话资源仲裁。
