# Roadmap

| Phase | Status | Goal | Exit gate |
|---|---|---|---|
| P0 | done | Source audit of Jarvis, dsh-pet, DSH API; selection/risk/P1 plan | three research docs reviewed |
| P1 | **current** | Monorepo, protocol, Runtime skeleton, plugin skeleton, CI | G1–G8 in `P1_PLAN.md` |
| P2 | planned | Real audio capture/playback, device management, AEC spike | device matrix + barge-in measurement |
| P3 | planned | Wake/VAD/ASR/TTS adapters and model benchmarks | WER/CER + latency report |
| P4 | planned | Full protocol: events, reconnect, cancellation, recovery | protocol conformance suite |
| P5 | planned | DSH Agent Bridge + full settings/mic UI | voice text into live Session |
| P6 | planned | dsh-pet bridge: lock, animation, work status, bubble | avatar mapping test |
| P7 | planned | Full duplex, barge-in, TTS/Agent/steer separation | interruption test matrix |
| P8 | planned | Permission confirmation, audit, red-team | no vague-consent bypass |
| P9 | planned | Windows installer + Ubuntu deb/systemd | clean-machine install |
| P10 | planned | Performance, 8 h soak, release | published report |

## P1 acceptance gates

1. Windows and Ubuntu build.
2. Lint/typecheck/tests green.
3. Runtime starts standalone, authenticates, heartbeats, stops cleanly.
4. Plugin loads in DSH 0.2.1-rc.3 and shows the settings status page.
5. Protocol JSON + binary round-trip and version mismatch rejection.
6. Model manifest schema + downloader negative tests.
7. Unauthenticated connections rejected; logs contain no token/transcript.
8. Docs complete; no stub is described as a feature.
