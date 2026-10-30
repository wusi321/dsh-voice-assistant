# P2 音频系统验收报告

- 日期：2026-10-30
- 范围：设备枚举、选择、采集、播放、重采样、设备切换、异常恢复、Mock 测试。
- 目标：Windows 10/11 + Ubuntu 22.04；不假设 16 kHz 或 48 kHz 硬件。

## 1. 实现

| 模块 | 文件 | 行为 |
|---|---|---|
| Backend 抽象 | `audio/backend.py` | `AudioBackend` Protocol；`SoundDeviceBackend` 懒加载 sounddevice；所有 PortAudio 调用可注入 |
| 设备管理 | `audio/device_manager.py` | 枚举输入/输出、默认设备、按 index/名称选择、能力校验、采样率选择 |
| 采集 | `audio/capture.py` | 单 InputStream；回调只做拷贝；5 s 有界 ring buffer；状态/完成回调 |
| 播放调度 | `audio/playback.py` | `PlaybackScheduler` 是唯一播放权威；started/finished/interrupted 事件；可取消 |
| 播放流 | `audio/playback.py` | 单 OutputStream；把同一帧写入扬声器与 AEC 参考回调 |
| 重采样 | `audio/resampler.py` | 一次性 polyphase + 跨块线性相位连续；用于设备率 ↔ 内部 16 kHz、TTS 24 kHz ↔ 设备率 |
| AEC | `audio/aec.py` | livekit WebRTC APM（16 kHz/10 ms）；软件参考，不是 loopback；不可用时显式降级 |
| 组合 | `audio/audio_io.py` | 采集/播放/AEC/参考 ring、`play`、`read_clean`、`switch_devices`、`restart` |
| 异常恢复 | `audio/audio_io.py` | 打开失败包装为 `AudioBackendError`；`restart(retries, delay)` 重开；stream finished 触发错误回调 |
| 设备切换 | `audio/audio_io.py` | 停止 → 更新选择 → 重开；输入/输出可独立切换 |

意图停止（`stop()`）会设置 `_stopping`，不会把 sounddevice 的 `finished_callback` 误报为“设备异常”。

## 2. 自动化测试（Mock）

`runtime/tests/audio_fakes.py` 提供 `FakeBackend` / `FakeInputStream` / `FakeOutputStream`：

- 设备枚举/默认值/按名称或 index 选择/通道与采样率错误。
- 采集回调写入 ring buffer，读取顺序正确。
- 播放调度：分块、started/finished、按 utterance 取消。
- 播放流：输出与参考回调一致。
- AudioIO：启动/停止、播放、采集、输入+输出设备切换、打开失败后 restart、stream finished 错误回调。
- AEC：Passthrough 恒等；WebRTC APM 16k/10ms 处理（无 livekit 时 skip）。

结果：

```text
tests/test_device_manager.py   4 passed
tests/test_streams.py          3 passed
tests/test_audio_io.py         4 passed
tests/test_aec.py              3 passed
```

## 3. 真机验证（Windows）

实际运行：

```text
voice-runtime probe --json
available: true
default_input: 1 (AMD Audio Device, 44.1 kHz)
default_output: 4 (Realtek Audio, 44.1 kHz)
```

短采集：

```text
AudioIO.start(); sleep 0.5; read_clean()
captured 7680 samples; errors []
```

短播放（0.2 s，440 Hz，低音量）：

```text
AudioIO.play(...); sleep 0.6
scheduler.is_active == False; errors []
```

结论：Windows 上真实设备枚举、44.1 kHz 采集/播放、重采样链路、停止清理均工作。

## 4. Ubuntu 状态

**未在 Ubuntu 实机运行**。CI 的 Python/Node job 会运行 Mock 测试；真实设备需要：

- `libportaudio2`
- PipeWire 或 PulseAudio
- 至少一个输入/输出设备（或虚拟声卡）

P2 代码没有依赖 Windows API；`sounddevice`/PortAudio 在 Linux 走 ALSA/PulseAudio。设备选择/重采样/错误恢复逻辑与平台无关。**P2-G2（Ubuntu 真机）仍待补。**

## 5. 已知限制（继承到 P7/P9）

1. **无热插拔 watcher**：设备断开由 stream finished/错误回调发现，调用方需 `restart()`；没有后台轮询。
2. **无时钟漂移补偿**：输入/输出是两个独立流；长时间运行需测量并补偿，P7 处理。
3. **AEC 延迟固定 40 ms**：未做延迟估计；蓝牙设备可能失效，P7 做延迟估计/双讲检测。
4. **无 WASAPI exclusive / PulseAudio 设备优先级策略**：使用 shared mode 默认行为。
5. **未做真实 Linux 设备矩阵**。
6. **未做 8 小时 soak**。
