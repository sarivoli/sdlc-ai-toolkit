/**
 * SDLC AI Toolkit MCP App: renders the A2UI surfaces that scripts/sdlc_ui_mcp.py returns.
 *
 * The server's model-facing tools (sdlc_ui_*) return `application/a2ui+json` resources.
 * The host shows this page in a sandboxed iframe and forwards each tool result here.
 * Where the A2UI messages come from, first match wins:
 *   1. the tool result's embedded `application/a2ui+json` resource
 *   2. the tool result's `_meta["sdlc-ui/a2ui"]` (hosts that drop resources)
 *   3. `sdlc_ui_render` {tool, arguments}: the panel asks the server itself, using the tool input the
 *      host forwarded (hosts that never forward the result, e.g. the Copilot CLI agent host)
 * If nothing arrives, the panel says so instead of waiting forever.
 *
 * Button actions:
 *   sdlc.chat  {text, comment?}  -> sends `text` to the chat as the user's next message (ui/message)
 *   sdlc.open  {url}             -> asks the host to open a link
 *   anything else                -> tools/call on the server (app-only tools), result re-rendered
 */
import {html, render} from 'lit';
import '@a2ui/lit';
import {renderMarkdown} from '@a2ui/markdown-it';
import {
  basicCatalog,
  MessageProcessor,
  setMarkdownRenderer,
  type ActionPayload,
  type ProcessableMessagePayload,
  type SurfaceModel,
} from '@a2ui/web_core/v1_0';
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from '@modelcontextprotocol/ext-apps';
import type {CallToolResult} from '@modelcontextprotocol/sdk/types.js';
import './theme.css';

setMarkdownRenderer(renderMarkdown);

const A2UI_MIME = new Set(['application/a2ui+json', 'application/json+a2ui']);
const META_KEY = 'sdlc-ui/a2ui';
const RENDER_AFTER_MS = 1500; // tool input seen but no result yet: ask the server
const LAST_PANEL_AFTER_MS = 3000; // nothing at all: ask for the panel the server built last
const GIVE_UP_MS = 15000;
const root = document.getElementById('surface-root')!;
const toast = document.getElementById('toast')!;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const surfaces = new Map<string, SurfaceModel<any>>();

const app = new App(
  {name: 'sdlc-ai-toolkit-ui', version: '1.0.0'},
  {availableDisplayModes: ['inline']},
  {autoResize: true},
);

let notice = 'Waiting for the agent…';
function paint(): void {
  const list = [...surfaces.values()];
  render(
    list.length
      ? html`${list.map(s => html`<section class="sdlc-surface"><a2ui-surface .surface=${s}></a2ui-surface></section>`)}`
      : html`<p class="sdlc-empty">${notice}</p>`,
    root,
  );
}

function trace(message: string, level: 'info' | 'warning' | 'error' = 'info'): void {
  app.sendLog({level, logger: 'sdlc-ui', data: message}).catch(() => undefined);
}

let toastTimer: number | undefined;
function say(text: string, kind: 'ok' | 'warn' = 'ok'): void {
  toast.textContent = text;
  toast.className = `sdlc-toast sdlc-toast-${kind}`;
  toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toast.hidden = true), 6000);
}

async function toChat(text: string): Promise<void> {
  try {
    const res = await app.sendMessage({role: 'user', content: [{type: 'text', text}]});
    if (res?.isError) throw new Error('rejected');
    say('Sent to the chat.');
  } catch {
    // Host without ui/message support: the developer types it instead.
    say(`Type this in the chat: ${text}`, 'warn');
  }
}

function str(v: unknown): string {
  return v === undefined || v === null ? '' : String(v).trim();
}

async function onAction(action: ActionPayload): Promise<void> {
  const ctx = action.context ?? {};
  if (action.name === 'sdlc.chat') {
    const comment = str(ctx.comment);
    const text = str(ctx.text) + (comment ? `${str(ctx.separator) || ': '}${comment}` : '');
    if (str(ctx.require_comment) === 'true' && !comment) {
      say('Add a comment first.', 'warn');
      return;
    }
    if (text) await toChat(text);
    return;
  }
  if (action.name === 'sdlc.open') {
    const url = str(ctx.url);
    if (!url) return;
    try {
      await app.openLink({url});
    } catch {
      say(`Open: ${url}`, 'warn');
    }
    return;
  }
  try {
    const result = await app.callServerTool({name: action.name, arguments: ctx});
    applyResult(result);
    if (result.isError) say(firstText(result) || 'The toolkit reported an error.', 'warn');
  } catch (e) {
    say(`Could not reach the toolkit server (${(e as Error).message}).`, 'warn');
  }
}

const processor = new MessageProcessor([basicCatalog], a => {
  onAction(a).catch(() => say('Action failed.', 'warn'));
});
processor.onSurfaceCreated(s => {
  surfaces.set(s.id, s);
  paint();
});
processor.onSurfaceDeleted(id => {
  surfaces.delete(id);
  paint();
});

function firstText(result: CallToolResult): string {
  for (const b of result.content ?? []) if (b.type === 'text') return b.text;
  return '';
}

function a2uiOf(result: CallToolResult): unknown[] | null {
  for (const block of result.content ?? []) {
    if (block.type === 'resource' && 'text' in block.resource && A2UI_MIME.has(String(block.resource.mimeType))) {
      try {
        return JSON.parse(block.resource.text) as unknown[];
      } catch {
        /* try the next source */
      }
    }
  }
  const meta = (result._meta as Record<string, unknown> | undefined)?.[META_KEY];
  if (Array.isArray(meta)) return meta;
  const structured = (result.structuredContent as {a2ui?: unknown} | undefined)?.a2ui;
  return Array.isArray(structured) ? structured : null;
}

/** Draws a tool result; false when it carried no A2UI messages. */
function applyResult(result: CallToolResult): boolean {
  const messages = a2uiOf(result);
  if (messages) {
    try {
      processor.processMessages(messages as ProcessableMessagePayload);
    } catch (e) {
      say(`Could not draw this view: ${(e as Error).message}`, 'warn');
      trace(`processMessages failed: ${(e as Error).message}`, 'error');
    }
  }
  const follow = (result.structuredContent as {followup?: unknown} | undefined)?.followup;
  if (typeof follow === 'string' && follow) toChat(follow);
  return Boolean(messages);
}

// ---------------------------------------------------------------- fallback: ask the server
let toolInput: Record<string, unknown> | undefined;
let resultText = '';
let rendering = false;
let renderTimer: number | undefined;

function toolName(): string {
  return String(app.getHostContext()?.toolInfo?.tool?.name ?? '');
}

async function renderFromServer(why: string): Promise<void> {
  if (rendering || surfaces.size) return;
  rendering = true;
  trace(`no A2UI in the tool result (${why}); asking the server with sdlc_ui_render`, 'warning');
  try {
    const args = toolInput ? {tool: toolName(), arguments: toolInput} : {};
    const result = await app.callServerTool({name: 'sdlc_ui_render', arguments: args});
    if (!applyResult(result)) showProblem(firstText(result) || 'The toolkit returned no panel.');
  } catch (e) {
    showProblem(`The editor did not pass this panel its data, and the panel could not ask the toolkit (${(e as Error).message}).`);
  } finally {
    rendering = false;
  }
}

function showProblem(text: string): void {
  if (surfaces.size) return;
  notice = text + (resultText ? ` The agent's result: ${resultText}` : '');
  trace(notice, 'warning');
  paint();
}

function applyHost(ctx: McpUiHostContext | undefined): void {
  if (!ctx) return;
  if (ctx.theme) {
    applyDocumentTheme(ctx.theme);
    document.documentElement.classList.toggle('a2ui-dark', ctx.theme === 'dark');
    document.documentElement.classList.toggle('a2ui-light', ctx.theme === 'light');
  }
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
}

app.ontoolinput = p => {
  toolInput = (p.arguments ?? {}) as Record<string, unknown>;
  window.clearTimeout(renderTimer);
  renderTimer = window.setTimeout(() => void renderFromServer('no result after the tool input'), RENDER_AFTER_MS);
};
app.ontoolresult = r => {
  window.clearTimeout(renderTimer);
  const result = r as CallToolResult;
  resultText = firstText(result);
  if (applyResult(result)) return;
  if (result.isError) showProblem(resultText || 'The toolkit reported an error.');
  else void renderFromServer('result without A2UI');
};
app.ontoolcancelled = () => showProblem('The tool call was cancelled.');
app.onhostcontextchanged = c => applyHost({...app.getHostContext(), ...c});
paint();
await app.connect();
applyHost(app.getHostContext());
window.setTimeout(() => void renderFromServer('nothing arrived'), LAST_PANEL_AFTER_MS);
window.setTimeout(() => {
  if (!surfaces.size)
    showProblem('Nothing arrived from the editor for this panel. Ask the agent to show it again, or run `sdlc.py doctor`.');
}, GIVE_UP_MS);
