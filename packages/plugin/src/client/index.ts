declare global {
  interface Window {
    __ModuleLoader__: {
      load(definition: { id: string; factory: (require: (id: string) => any) => any }): void;
    };
  }
}

const PLUGIN_ID = 'dsh-voice-assistant';
const NS = 'voice-assistant';

// Kept in the bundle so the client has no build-time JSON import outside src/.
// The package-level locale/*.json files are the DSH display metadata source.
const EN = {
  meta: {
    title: 'Voice Assistant',
    description:
      'Local wake word, streaming speech recognition, TTS, and dsh-pet avatar integration.',
  },
  nav: 'Voice Assistant',
  title: 'Voice Assistant',
  status: {
    label: 'Runtime status',
    connected: 'Connected',
    starting: 'Starting',
    stopped: 'Stopped',
    error: 'Error',
    unknown: 'Unknown',
  },
  runtime: {
    version: 'Runtime version',
    port: 'Port',
    command: 'Runtime command',
    discovery: 'Discovery file',
    reconnect: 'Refresh',
  },
  notice: 'P1 skeleton: no microphone, wake word, ASR, or TTS is active yet.',
};

const ZH = {
  meta: {
    title: '语音助手',
    description: '本地唤醒词、流式语音识别、TTS 与 dsh-pet 桌宠联动。',
  },
  nav: '语音助手',
  title: '语音助手',
  status: {
    label: 'Runtime 状态',
    connected: '已连接',
    starting: '启动中',
    stopped: '已停止',
    error: '错误',
    unknown: '未知',
  },
  runtime: {
    version: 'Runtime 版本',
    port: '端口',
    command: 'Runtime 命令',
    discovery: '发现文件',
    reconnect: '刷新',
  },
  notice: 'P1 骨架：尚未启用麦克风、唤醒词、ASR 或 TTS。',
};

interface StatusPayload {
  state?: string;
  detail?: string;
  port?: number;
  pid?: number;
  runtimeVersion?: string;
  discoveryPath?: string;
}

const COLORS: Record<string, string> = {
  connected: '#22c55e',
  starting: '#f59e0b',
  error: '#ef4444',
  stopped: '#94a3b8',
  unknown: '#94a3b8',
};

function statusLabel(state: string | undefined, t: (key: string) => string): string {
  if (!state) return t('status.unknown');
  const value = t(`status.${state}`);
  return value || state;
}

function createSettings(React: any, t: (key: string) => string): any {
  return function VoiceSettings(): any {
    const [status, setStatus] = React.useState({ state: 'unknown' } as StatusPayload);
    const [error, setError] = React.useState('');
    const [loading, setLoading] = React.useState(false);

    const refresh = React.useCallback(async (): Promise<void> => {
      setLoading(true);
      try {
        const response = await fetch('/dsh-voice-assistant/status', { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setStatus((await response.json()) as StatusPayload);
        setError('');
      } catch (cause) {
        setStatus({ state: 'unknown' });
        setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        setLoading(false);
      }
    }, []);

    React.useEffect(() => {
      void refresh();
      const timer = setInterval(() => void refresh(), 2_000);
      return () => clearInterval(timer);
    }, [refresh]);

    const state = status.state ?? 'unknown';
    const row = (label: string, value: string | number | undefined): any =>
      React.createElement(
        'tr',
        null,
        React.createElement(
          'th',
          { style: { textAlign: 'left', padding: '4px 12px 4px 0', opacity: 0.7 } },
          label,
        ),
        React.createElement('td', { style: { padding: '4px 0' } }, value ?? '-'),
      );

    return React.createElement(
      'section',
      { style: { padding: '8px 0', maxWidth: 720, color: 'var(--dsh-color-text, #e5e7eb)' } },
      React.createElement('h2', { style: { margin: '0 0 4px' } }, t('title')),
      React.createElement(
        'p',
        { style: { margin: '0 0 16px', opacity: 0.7 } },
        'Local wake word, streaming ASR, TTS, and dsh-pet integration.',
      ),
      React.createElement(
        'div',
        {
          style: {
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '4px 10px',
            borderRadius: 999,
            background: 'var(--dsh-color-surface-2, #1f2937)',
            marginBottom: 12,
          },
        },
        React.createElement('span', {
          style: {
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: COLORS[state] ?? COLORS.unknown,
          },
        }),
        React.createElement('span', null, statusLabel(state, t)),
        loading ? React.createElement('span', { style: { opacity: 0.5 } }, '...') : null,
      ),
      React.createElement(
        'table',
        { style: { borderCollapse: 'collapse', fontSize: 13, marginBottom: 12 } },
        React.createElement(
          'tbody',
          null,
          row(t('runtime.version'), status.runtimeVersion),
          row(t('runtime.port'), status.port),
          row(t('runtime.discovery'), status.discoveryPath),
          row(t('runtime.command'), 'voice-runtime daemon'),
        ),
      ),
      error
        ? React.createElement(
            'p',
            { style: { color: '#f87171', fontSize: 13 } },
            `${t('status.error')}: ${error}`,
          )
        : null,
      React.createElement(
        'button',
        {
          type: 'button',
          onClick: () => void refresh(),
          disabled: loading,
          style: {
            padding: '6px 12px',
            borderRadius: 6,
            border: '1px solid var(--dsh-color-border, #475569)',
            background: 'var(--dsh-color-surface-2, #1f2937)',
            color: 'inherit',
            cursor: loading ? 'wait' : 'pointer',
          },
        },
        t('runtime.reconnect'),
      ),
      React.createElement(
        'p',
        { style: { marginTop: 16, fontSize: 12, opacity: 0.65 } },
        t('notice'),
      ),
    );
  };
}

window.__ModuleLoader__.load({
  id: PLUGIN_ID,
  factory(require) {
    const React = require('react');
    return {
      inject: ['slots', 'locale'],
      apply(ctx: any): void {
        ctx.locale.register(NS, { en: EN, zh: ZH });
        const t = ctx.locale.bind(NS);
        const VoiceSettings = createSettings(React, t);
        ctx.slots.inject('settings.section', () =>
          ctx.slots.register(
            {
              name: 'settings.section',
              id: PLUGIN_ID,
              order: 80,
              label: () => t('nav'),
              locale: NS,
            },
            VoiceSettings,
          ),
        );
      },
    };
  },
});
