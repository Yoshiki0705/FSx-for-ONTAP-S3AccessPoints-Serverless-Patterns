#!/usr/bin/env node
// Derived from tools/check-ui.mjs in unslop-ai-app (commit 502945105eb7, 2026-11-09),
// Copyright 2026 Minoru Onda, licensed under the Apache License 2.0 (see ./LICENSE and /NOTICE).
// Changes: removed the `key-hint` rule (it encodes a stage-demo convention, not a mechanical
// check), added `--json`, made `emoji` skip console/logger lines, reworded this header. All other rules are unchanged.
//
// 画面のソース（HTML / CSS / JSX / TSX / Vue / Svelte）から、テンプレート的な書き方を拾う。
// 使い方: node check-ui.mjs [--json] <ファイルかフォルダ>...
// 行に check-ui-ignore と書くと、その行は対象外になる。指摘が0件なら終了コード0、1件以上なら1。
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, extname, relative } from 'node:path';

const EXTS = new Set(['.html', '.htm', '.css', '.scss', '.jsx', '.tsx', '.js', '.ts', '.vue', '.svelte', '.astro']);
const SKIP_DIRS = new Set(['node_modules', 'dist', 'build', '.git', '.next', 'out', 'coverage', 'cdk.out']);

function hexToHsl(hex) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = [...h].map(c => c + c).join('');
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min, l = (max + min) / 2;
  if (!d) return { h: 0, s: 0, l };
  const s = d / (1 - Math.abs(2 * l - 1));
  let hue = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: (hue * 60 + 360) % 360, s, l };
}

function rgbaIsColored(str) {
  const m = str.match(/rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/);
  if (!m) return false;
  const [r, g, b] = m.slice(1, 4).map(Number);
  return Math.max(r, g, b) - Math.min(r, g, b) > 40;
}

const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B50}\u{2B55}\u{2705}\u{274C}\u{2728}]/u;

const RULES = [
  {
    id: 'side-stripe',
    msg: 'カードや枠の1辺だけに太い色の線がある。面・角丸・薄い影で作り、状態は小さな丸か文字で示す',
    test: line => {
      const css = line.match(/border-(left|right|top|bottom)(-width)?\s*:\s*(\d+(?:\.\d+)?)px/);
      if (css && Number(css[3]) >= 3) return true;
      return /\bborder-[lrtb]-(4|8|\[[3-9]px\]|\[\d{2}px\])\b/.test(line);
    },
  },
  {
    id: 'emoji',
    msg: '画面の文字に絵文字がある。線のアイコン1種類にするか、何も置かない',
    test: (line, ctx) => !ctx.isCss && !/\bconsole\.(log|warn|error|info|debug)\(|\blogger\./.test(line) && EMOJI.test(line.replace(/\/\/.*$|<!--.*?-->|\/\*.*?\*\//g, '')),
  },
  {
    id: 'gradient-text',
    msg: '文字にグラデーションがかかっている。単色にする',
    test: line => /background-clip\s*:\s*text|\bbg-clip-text\b/.test(line),
  },
  {
    id: 'loud-gradient',
    msg: '紫・青紫・桃色の派手なグラデーション。地は無彩色にし、強い色は意味のある1〜2か所だけ',
    test: line => {
      if (/\b(from|via|to)-(purple|violet|fuchsia|pink|indigo)-\d{3}\b/.test(line)) return true;
      if (!/gradient\(/.test(line)) return false;
      return (line.match(/#[0-9a-f]{6}\b|#[0-9a-f]{3}\b/gi) || [])
        .map(hexToHsl)
        .some(c => c.h >= 255 && c.h <= 335 && c.s > 0.45 && c.l > 0.25 && c.l < 0.8);
    },
  },
  {
    id: 'glow',
    msg: '色の付いた光る影。奥行きは地の明るさの差と細い線で作る',
    test: line => {
      if (/shadow-\[0_0_\d+px_rgba?\(/.test(line) && rgbaIsColored(line.replace(/_/g, ' '))) return true;
      const m = line.match(/(box-shadow|text-shadow|filter)\s*:[^;]*?\b0(px)?\s+0(px)?\s+(\d+)px[^;]*/);
      return Boolean(m && Number(m[4]) >= 8 && rgbaIsColored(m[0]));
    },
  },
  {
    id: 'transition-all',
    msg: 'transition: all。動かす性質を指定し、ホバーは地の色を1段変える程度にする',
    test: line => /transition\s*:\s*all\b|\btransition-all\b/.test(line),
  },
  {
    id: 'hover-scale',
    msg: 'ホバーで拡大している。地の色の変化にとどめる',
    test: line => /\bhover:scale-\d+|:hover[^{]*\{[^}]*scale\(1\.\d+\)/.test(line),
  },
  {
    id: 'looping-motion',
    msg: '常に動く飾り（pulse / ping / bounce）。実際に進行中のものにだけ使う',
    test: line => {
      if (/\banimate-(pulse|ping|bounce)\b/.test(line)) return true;
      const m = line.match(/animation\s*:\s*([^;}]*)/);
      return Boolean(m && /\binfinite\b/.test(m[1]) && !/spin|rotat|shimmer|loading/i.test(m[1]));
    },
  },
  {
    id: 'heavy-weight',
    msg: '極太の文字（800以上）。見出しは600〜700までにする',
    test: line => /font-weight\s*:\s*(800|900)\b|\bfont-(extrabold|black)\b/.test(line),
  },
  {
    id: 'tracked-uppercase',
    msg: '大文字にして字間を広げたラベル。日本語の画面では普通の文字にする',
    test: line => /text-transform\s*:\s*uppercase|\buppercase\b[^"'`]*\btracking-(wide|wider|widest)\b/.test(line),
  },
  {
    id: 'italic',
    msg: '斜体。日本語の書体は機械的に傾くだけなので、色か太さで区別する',
    test: line => /font-style\s*:\s*italic|className=["'`][^"'`]*\bitalic\b/.test(line),
  },
  {
    id: 'off-grid-spacing',
    msg: '余白が4pxの刻みから外れている',
    test: line => {
      const tw = [...line.matchAll(/\b-?(?:m|p|gap|space-[xy])[trblxy]?-\[(\d+)px\]/g)].map(m => Number(m[1]));
      const css = [...line.matchAll(/\b(?:margin|padding|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left))?\s*:\s*([^;}]+)/g)]
        .flatMap(m => [...m[1].matchAll(/(\d+(?:\.\d+)?)px/g)].map(x => Number(x[1])));
      return [...tw, ...css].some(v => v > 2 && v % 4 !== 0);
    },
  },
  {
    id: 'small-input-font',
    msg: '入力欄の文字が16px未満。iOS Safari がフォーカス時に画面を拡大する',
    test: line => {
      if (/<(input|textarea|select)\b[^>]*\btext-(xs|sm)\b/.test(line)) return true;
      const m = line.match(/(input|textarea|select)[^{]*\{[^}]*font-size\s*:\s*(\d+(?:\.\d+)?)px/);
      return Boolean(m && Number(m[2]) < 16);
    },
  },
  {
    id: 'hover-menu',
    msg: 'ホバーで開くメニュー。タッチ端末で開けないので、クリックで開く',
    test: line => /\bgroup-hover:(visible|block|flex|opacity-100)\b|:hover\s*>\s*[^{]*\{[^}]*display\s*:\s*(block|flex)/.test(line),
  },
  {
    id: 'waiting-copy',
    msg: '空の状態を埋める待機メッセージやあいさつ。何も出さないか、次に押すものだけを示す',
    test: (line, ctx) => !ctx.isCss && /ここに[^<"'`]{0,20}表示され|を準備中|準備しています|ようこそ|Welcome back|何でも(聞いて|お気軽)/.test(line),
  },
  {
    id: 'hype-copy',
    msg: '効能を盛る言葉。何をするのかを書く',
    test: (line, ctx) => !ctx.isCss && /爆速|シームレス|革新的|魔法のよう|次世代の|圧倒的な|supercharge|seamless|revolutioni[sz]e|unlock the power/i.test(line),
  },
  {
    id: 'exclamation',
    msg: '画面の文言に「！」。平叙で書く',
    test: (line, ctx) => !ctx.isCss && /！/.test(line.replace(/\/\/.*$|<!--.*?-->|\/\*.*?\*\//g, '')),
  },
];

function walk(p, out) {
  const st = statSync(p);
  if (st.isDirectory()) {
    for (const name of readdirSync(p)) {
      if (SKIP_DIRS.has(name) || name.startsWith('cdk.out') || (name.startsWith('.') && name !== '.')) continue;
      walk(join(p, name), out);
    }
  } else if (EXTS.has(extname(p).toLowerCase()) && !/\.min\.|-[A-Za-z0-9_-]{8}\.(js|css)$/.test(p)) {
    out.push(p);
  }
}

const argv = process.argv.slice(2);
const asJson = argv.includes('--json');
const args = argv.filter(a => a !== '--json');
if (!args.length) {
  console.error('使い方: node tools/check-ui.mjs <ファイルかフォルダ>...');
  process.exit(2);
}

const files = [];
for (const a of args) walk(a, files);

let count = 0;
const found = [];
for (const file of files) {
  const isCss = ['.css', '.scss'].includes(extname(file).toLowerCase());
  const lines = readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, i) => {
    if (line.includes('check-ui-ignore') || line.length > 1000) return;
    for (const rule of RULES) {
      if (rule.test(line, { isCss })) {
        count++;
        const where = `${relative(process.cwd(), file)}:${i + 1}`;
        found.push({ file: relative(process.cwd(), file), line: i + 1, rule: rule.id });
        if (!asJson) console.log(`${where}  [${rule.id}] ${rule.msg}`);
      }
    }
  });
}

if (asJson) console.log(JSON.stringify({ files: files.length, findings: found }));
else console.log(`\n${files.length}ファイルを確認し、${count}件の指摘`);
process.exit(count ? 1 : 0);
