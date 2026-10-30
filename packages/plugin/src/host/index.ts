import { DshAgentBridge } from './agent-bridge.js';
import type { Config } from './config.js';
import { registerStatusRoute } from './http.js';
import { PetBridge } from './pet-bridge.js';
import { PetTtsProvider } from './pet-tts-provider.js';
import { RuntimeManager } from './runtime-manager.js';
import { SessionBinder } from './session-binder.js';
import { TtsOutput } from './tts-output.js';
import { log, type HostContext } from './types.js';

export { Config } from './config.js';
export type { RuntimeStatus } from './runtime-manager.js';
export type { AgentBridgeStatus } from './agent-bridge.js';
export type { PetStatus } from './pet-bridge.js';

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
  const pet = new PetBridge(ctx, config, bridge, tts);
  const petTts = new PetTtsProvider(ctx, config);

  ctx.effect(() => {
    void manager.start();
    return () => manager.stop();
  }, 'voice-assistant.runtime');

  ctx.effect(
    () =>
      manager.onEvent((event) => {
        tts.handleRuntimeEvent(event);
        bridge.handleRuntimeEvent(event);
        pet.handleRuntimeEvent(event);
      }),
    'voice-assistant.runtime-events',
  );

  ctx.effect(() => bridge.subscribe(), 'voice-assistant.agent');

  ctx.effect(() => {
    void pet.start();
    return () => {
      void pet.stop();
    };
  }, 'voice-assistant.pet');

  ctx.effect(() => petTts.start(), 'voice-assistant.pet-tts-provider');

  ctx.effect(
    () => registerStatusRoute(ctx, manager, binder, bridge, tts, pet, petTts, config.statusRoute),
    'voice-assistant.status-route',
  );

  log(ctx, 'info', 'voice assistant host loaded', {
    discoveryPath: manager.discoveryPath,
    autoStart: config.autoStart,
    sessionStrategy: config.sessionStrategy,
    petEnabled: config.petEnabled,
  });
}
