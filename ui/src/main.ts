/**
 * SDLC AI Toolkit MCP App: renders the A2UI surfaces that scripts/sdlc_ui_mcp.py returns.
 *
 * The server's model-facing tools (sdlc_ui_*) return `application/a2ui+json` resources.
 * The host shows this page in a sandboxed iframe and forwards each tool result here.
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
const root = document.getElementById('surface-root')!;
const toast = document.getElementById('toast')!;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const surfaces = new Map<string, SurfaceModel<any>>();

const app = new App(
  {name: 'sdlc-ai-toolkit-ui', version: '1.0.0'},
  {availableDisplayModes: ['inline']},
  {autoResize: true},
);

function paint(): void {
  const list = [...surfaces.values()];
  render(
    list.length
      ? html`${list.map(s => html`<section class="sdlc-surface"><a2ui-surface .surface=${s}></a2ui-surface></section>`)}`
      : html`<p class="sdlc-empty">Waiting for the agent…</p>`,
    root,
  );
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

function applyResult(result: CallToolResult): void {
  for (const block of result.content ?? []) {
    if (block.type === 'resource' && 'text' in block.resource && A2UI_MIME.has(String(block.resource.mimeType))) {
      try {
        processor.processMessages(JSON.parse(block.resource.text) as ProcessableMessagePayload);
      } catch (e) {
        say(`Could not draw this view: ${(e as Error).message}`, 'warn');
      }
    }
  }
  const follow = (result.structuredContent as {followup?: unknown} | undefined)?.followup;
  if (typeof follow === 'string' && follow) toChat(follow);
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

app.ontoolresult = r => applyResult(r as CallToolResult);
app.onhostcontextchanged = c => applyHost({...app.getHostContext(), ...c});
paint();
await app.connect();
applyHost(app.getHostContext());
