/** Voice State + Agent State → Avatar State; Agent work must not be masked by idle voice. */

export type VoiceState =
  | 'IDLE'
  | 'WAKEUP'
  | 'LISTENING'
  | 'TRANSCRIBING'
  | 'DISPATCHING'
  | 'THINKING'
  | 'SPEAKING'
  | 'INTERRUPTING'
  | 'CONFIRMATION'
  | 'ERROR';

export type AgentBridgeState =
  | 'IDLE'
  | 'THINKING'
  | 'TOOL_CALLING'
  | 'TOOL_RUNNING'
  | 'TOOL_RESULT'
  | 'WAITING_CONFIRMATION'
  | 'SUCCESS'
  | 'ERROR'
  | 'CANCELLED';

export type AvatarState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'working'
  | 'result'
  | 'speaking'
  | 'waiting'
  | 'success'
  | 'error';

export interface AvatarInputs {
  readonly voiceState?: VoiceState;
  readonly agentState?: AgentBridgeState;
  readonly ttsSpeaking?: boolean;
}

const priority: Record<AvatarState, number> = {
  error: 9,
  waiting: 8,
  working: 7,
  result: 6,
  speaking: 5,
  thinking: 4,
  listening: 3,
  success: 2,
  idle: 1,
};

function voiceAvatar(input: AvatarInputs): AvatarState {
  if (input.ttsSpeaking || input.voiceState === 'SPEAKING') return 'speaking';
  switch (input.voiceState) {
    case 'ERROR':
      return 'error';
    case 'CONFIRMATION':
      return 'waiting';
    case 'LISTENING':
    case 'WAKEUP':
    case 'TRANSCRIBING':
    case 'DISPATCHING':
      return 'listening';
    case 'THINKING':
      return 'thinking';
    default:
      return 'idle';
  }
}

function agentAvatar(state: AgentBridgeState | undefined): AvatarState | null {
  switch (state) {
    case 'ERROR':
      return 'error';
    case 'WAITING_CONFIRMATION':
      return 'waiting';
    case 'TOOL_CALLING':
    case 'TOOL_RUNNING':
      return 'working';
    case 'TOOL_RESULT':
      return 'result';
    case 'THINKING':
      return 'thinking';
    case 'SUCCESS':
      return 'success';
    case 'CANCELLED':
    case 'IDLE':
      return null;
    default:
      return null;
  }
}

export function deriveAvatarState(input: AvatarInputs): AvatarState {
  const voice = voiceAvatar(input);
  const agent = agentAvatar(input.agentState);
  if (!agent) return voice;
  return priority[agent] >= priority[voice] ? agent : voice;
}

/** External `work-status` endpoint accepts exactly these six states. */
export function toPetWorkStatus(
  state: AvatarState,
): 'thinking' | 'working' | 'result' | 'waiting' | 'success' | 'error' | null {
  switch (state) {
    case 'thinking':
      return 'thinking';
    case 'working':
      return 'working';
    case 'result':
      return 'result';
    case 'waiting':
      return 'waiting';
    case 'success':
      return 'success';
    case 'error':
      return 'error';
    default:
      return null;
  }
}
