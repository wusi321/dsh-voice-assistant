# Security

Voice is a new input surface, not a new permission system. DSH remains the
authority for Agent tools and approvals.

## Network

- The Runtime binds only to `127.0.0.1`. There is no public listener and no
  remote mode in P1.
- Every connection starts with the discovery-file token. Missing/wrong tokens
  receive `auth.error` and are closed.
- Tokens are random 32-byte URL-safe strings, compared in constant time, and
  never logged, placed in URLs, or passed on a command line.
- Discovery files are written atomically and restricted to the current user
  (`chmod 600` on POSIX, `icacls` on Windows). The plugin rejects non-loopback
  hosts and dead PIDs.
- The DSH status route (`/dsh-voice-assistant/status`) exposes no secrets or
  audio. The only write is `/dsh-voice-assistant/active-session`, which changes
  the voice routing target and cannot execute an Agent/TTS command.

## Audio and transcripts

- Raw recordings are not persisted by default.
- The AEC reference is a bounded in-memory ring fed by the playback scheduler;
  no WASAPI loopback or PulseAudio monitor recording is used by default.
- Debug clips are off by default; enabling them must be explicit and bounded.
- The logger redacts `token`, `authorization`, `audio`, `pcm`, `text`,
  `transcript`, and `recording` keys. Application logs must not print recognized
  speech.
- The DSH plugin never receives raw audio; it receives protocol events.

## Agent permissions

- Voice messages enter DSH through `agent.followup()`/`agent.steer()`, so the
  session's sandbox and approval policy still apply.
- L3 operations (sudo, disk, system-critical configuration) require on-screen
  DSH approval. Voice may announce the request and read a short code, but must
  not auto-answer an approval.
- Any voice confirmation must bind `sessionId + turn + tool/call + operation
  hash + expiry`; vague words ("好", "可以", "都行") never authorize an action.
- The plugin will not expose hidden reasoning or tool arguments through TTS:
  only `text-delta`/`block-end(text)` is eligible for speech.

## Local status/session route limitations

The Host route has no authentication beyond localhost binding. `GET /status`
returns runtime/session/agent/TTS state; `POST /active-session` only changes the
voice routing target and never executes an Agent command. The route validates a
small JSON body (≤8 KiB) and a non-empty `sessionId`. It must not be exposed
publicly or extended with Agent/TTS control without token and CSRF/origin checks
equivalent to a privileged local API.
