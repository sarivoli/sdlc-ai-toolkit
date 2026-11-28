import {defineConfig} from 'vite';
import {viteSingleFile} from 'vite-plugin-singlefile';

// MCP Apps load the HTML into a srcdoc iframe with no base URL: everything must be inlined.
export default defineConfig({
  plugins: [viteSingleFile()],
  build: {outDir: 'dist', emptyOutDir: true, target: 'es2022'},
});
