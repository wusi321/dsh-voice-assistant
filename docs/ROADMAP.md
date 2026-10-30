# Roadmap

| Phase | Status | Goal | Exit gate |
|---|---|---|---|
| P0 | done | Source audit of Jarvis, dsh-pet, DSH API; selection/risk/P1 plan | three research docs reviewed |
| P1 | done | Monorepo, protocol, Runtime skeleton, plugin skeleton, CI | G1-G8 in `P1_PLAN.md` |
| P2 | done (Windows) | Real audio capture/playback, device management, AEC | Windows real device + mock tests; Ubuntu HW pending |
| P3 | done (local) | Wake/VAD/ASR/TTS adapters and local models | 3 real e2e tests pass; benchmark still pending |
| P4 | done | Versioned protocol, auth, heartbeat, reconnect, timeouts | protocol/auth/timeout/reconnect tests pass |
| P5 | done (core) | DSH Agent Bridge + settings/session UI | Agent/TTS tests pass; live DSH install pending |
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
8. Docs complete; no stub described as a feature.

## P2-P4 acceptance

- P2: `docs/P2_REPORT.md`; Windows real device capture/playback verified, Linux
  hardware pending.
- P3: `docs/P3_REPORT.md`; TTS, VAD+ASR, KWS real-model e2e verified.
- P4: `docs/P4_REPORT.md`; auth, heartbeat, idle/auth timeout, reconnect and
  binary frame tests pass.
- P5: `docs/P5_REPORT.md`; Agent Bridge/session/assistant-stream/tool status/TTS
  tests pass; live DSH installation remains.
