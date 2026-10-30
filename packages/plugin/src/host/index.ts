import type { Config } from './config.js';
import { registerStatusRoute } from './http.js';
import { RuntimeManager } from './runtime-manager.js';
import { log, type HostContext } from './types.js';

export { Config } from './config.js';
export type { RuntimeStatus } from './runtime-manager.js';

export const name = 'voice-assistant';

/** No hard service dependency: a missing web server only disables the status route. */
export const inject: string[] = [];

/**
 * Host half of the DSH voice plugin. P1 only owns the Runtime process and the
 * read-only status route; Agent/TTS/audio wiring is P4/P5.
 */
export function apply(ctx: HostContext, config: Config): void {
  const manager = new RuntimeManager(ctx, config);

  ctx.effect(() => {
    void manager.start();
    return () => manager.stop();
  }, 'voice-assistant.runtime');

  ctx.effect(
    () => registerStatusRoute(ctx, manager, config.statusRoute),
    'voice-assistant.status-route',
  );

  log(ctx, 'info', 'voice assistant host loaded', {
    discoveryPath: manager.discoveryPath,
    autoStart: config.autoStart,
  });
}
