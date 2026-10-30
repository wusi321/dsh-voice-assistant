import { build } from 'esbuild';

await build({
  entryPoints: ['src/client/index.ts'],
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: 'es2022',
  outfile: 'lib/client.js',
  sourcemap: false,
  legalComments: 'none',
  logLevel: 'info',
});
