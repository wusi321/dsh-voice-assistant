import { DshAgentBridge } from './agent-bridge.js';
import type { Config } from './config.js';
import { registerStatusRoute } from './http.js';
import { RuntimeManager } from './runtime-manager.js';
import { SessionBinder } from './session-binder.js';
import { TtsOutput } from './tts-output.js';
import { log, type HostContext } from './types.js';

export { Config } from './config.js';
export type { RuntimeStatus } from './runtime-manager.js';
export type { AgentBridgeStatus } from './agent-bridge.js';

export const name = 'voice-assistant';

/** No hard service dependency: a missing web server only disables the status route. */
export const inject: string[] = [];

/**
 * Host half of the DSH voice plugin. P5 wires the verified Agent API:
 * session binding -> Agent followup/steer/cancel -> assistant-stream -> TTS.
 */
export function apply(ctx: HostContext, config: Config): void {
  const manager = new RuntimeManager(ctx, config);
  const binder = new SessionBinder(ctx, config);
  const tts = new TtsOutput(ctx, manager, config);
  const bridge = new DshAgentBridge(ctx, binder, tts, config);

  ctx.effect(() => {
    void manager.start();
    return () => manager.stop();
  }, 'voice-assistant.runtime');

  ctx.effect(
    () =>
      manager.onEvent((event) => {
        tts.handleRuntimeEvent(event);
        bridge.handleRuntimeEvent(event);
      }),
    'voice-assistant.runtime-events',
  );

  ctx.effect(() => bridge.subscribe(), 'voice-assistant.agent');

  ctx.effect(
    () => registerStatusRoute(ctx, manager, binder, bridge, tts, config.statusRoute),
    'voice-assistant.status-route',
  );

  log(ctx, 'info', 'voice assistant host loaded', {
    discoveryPath: manager.discoveryPath,
    autoStart: config.autoStart,
    sessionStrategy: config.sessionStrategy,
  });
}
