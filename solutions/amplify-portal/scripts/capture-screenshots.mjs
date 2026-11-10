#!/usr/bin/env node
/**
 * Capture portal screenshots from a running dev server, masked and reproducible.
 *
 * Why a script: the portal has about 130 documentation screenshots, and a UI change
 * (the emoji-to-line-icon change, #518) makes most of them stale at once. Taking them
 * by hand is hundreds of browser calls and the masking differs between shots. This
 * runs one signed-in session through a manifest, so the same manifest can be pointed at
 * an old build (Before) and a new build (After) and the pair differs only in the UI.
 *
 * Usage (from solutions/amplify-portal):
 *   PORTAL_USER=... PORTAL_PASSWORD=... node scripts/capture-screenshots.mjs \
 *     --base http://localhost:5188 --set blog --out ../../docs/screenshots/portal-ui-refresh/after
 *   node scripts/capture-screenshots.mjs --list
 *
 * Sets:  blog     the Before/After pairs (output file is NN-name.png under --out)
 *        replace  the existing documentation screenshots, written to their repo paths
 *                 (--out is the repository root; default ../..)
 *
 * Masking: placeholders are applied to the page text immediately before each capture
 * with one page.evaluate (not addInitScript, which accumulates, and not a
 * MutationObserver, which spins the renderer; see docs/agent/pitfalls-browser-automation.md).
 * Environment-specific names live in a gitignored JSON file (--subs, default
 * ../../docs/screenshots/originals/portal-refresh/_substitutions.json) with
 * { "substitutions": [[from, to], ...], "forbidden": [word, ...] }. Generic patterns
 * (IPv4, 12-digit account ids, file system ids) are built in.
 * After substituting, the visible text is scanned again. A shot whose text still holds
 * an address, an id or a forbidden word is NOT saved, and the run exits non-zero.
 */
import { chromium } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const DESKTOP = { width: 1512, height: 805 };
const MOBILE = { width: 390, height: 844 };
const WELCOME_KEY = "portal-welcome-dismissed";
const LOADING = /(読み込み中|Loading\.\.\.|로딩 중|加载中|載入中|Chargement\.\.\.|Laden\.\.\.|Cargando\.\.\.)/;
/** Documentation address ranges (RFC 5737) and the loopback address are not leaks. */
const SAFE_IPV4 = /^(198\.51\.100|203\.0\.113|192\.0\.2|127\.0\.0)\./;

// --- Manifest -------------------------------------------------------------------
// hash: portal section. lang/theme/viewport default to ja/light/desktop.
// act: runs after the section is ready, before masking (open a panel, a drawer...).
const clickCard = (text) => async (page) => {
  await page.locator(".rm-card", { hasText: text }).first().click();
  await page.waitForTimeout(500);
};
const openDrawer = async (page) => {
  await page.locator("button.sidebar-toggle").click();
  await page.waitForTimeout(500);
};
const showWelcome = async (page) => {
  await page.evaluate((k) => localStorage.removeItem(k), WELCOME_KEY);
  await page.reload();
  await page.waitForSelector("text=/ようこそ|Welcome/", { timeout: 15000 });
};

const BLOG = [
  ["01-files", { hash: "files" }],
  ["02-files-dark", { hash: "files", theme: "dark" }],
  ["03-snapshots", { hash: "snapshots" }],
  ["04-lock", { hash: "lock" }],
  ["05-arp", { hash: "arp" }],
  ["06-resources", { hash: "resources" }],
  ["07-flexcache", { hash: "resources", act: clickCard("FlexCache") }],
  ["08-ai-settings", { hash: "resources", act: clickCard("AI 設定") }],
  ["09-welcome", { hash: "files", act: showWelcome }],
  ["10-mobile-drawer", { hash: "files", viewport: "mobile", act: openDrawer }],
];

const SHOTS = "solutions/amplify-portal/docs/screenshots";
const DEMO = "docs/screenshots/portal-demo";
const LANGS = { ja: "ja", en: "en", ko: "ko", de: "de", es: "es", fr: "fr", zhcn: "zh-CN", zhtw: "zh-TW" };
const REPLACE = [];
for (const [key, lang] of Object.entries(LANGS)) {
  REPLACE.push([`${SHOTS}/portal-${key}-allfiles.png`, { hash: "files", lang }]);
}
for (const lang of ["ja", "en"]) {
  for (const s of ["snapshots", "arp", "lock", "audit"]) {
    REPLACE.push([`${SHOTS}/portal-${lang}-${s}.png`, { hash: s, lang }]);
  }
}
REPLACE.push(
  [`${SHOTS}/portal-main-view.png`, { hash: "files" }],
  [`${SHOTS}/portal-sidebar-layout.png`, { hash: "files" }],
  [`${SHOTS}/portal-files-dark.png`, { hash: "files", theme: "dark" }],
  [`${SHOTS}/portal-snapshots-connected.png`, { hash: "snapshots" }],
  [`${SHOTS}/portal-lock-connected.png`, { hash: "lock" }],
  [`${SHOTS}/portal-arp-status-connected.png`, { hash: "arp" }],
  [`${SHOTS}/portal-data-protection-snapshots.png`, { hash: "snapshots" }],
  [`${SHOTS}/portal-data-protection-lock.png`, { hash: "lock" }],
  [`${SHOTS}/portal-data-protection-arp.png`, { hash: "arp" }],
  [`${SHOTS}/portal-version-diff.png`, { hash: "versions" }],
  [`${SHOTS}/portal-analytics.png`, { hash: "analytics" }],
  [`${SHOTS}/portal-ai-processing.png`, { hash: "process" }],
  [`${SHOTS}/portal-upload.png`, { hash: "upload" }],
  [`${SHOTS}/portal-upload-tab.png`, { hash: "upload" }],
  [`${SHOTS}/portal-mobile-files.png`, { hash: "files", viewport: "mobile" }],
  [`${SHOTS}/portal-mobile-drawer.png`, { hash: "files", viewport: "mobile", act: openDrawer }],
  [`${SHOTS}/portal-mobile-dark.png`, { hash: "files", viewport: "mobile", theme: "dark" }],
  [`${SHOTS}/portal-mobile-snapshots.png`, { hash: "snapshots", viewport: "mobile" }],
  [`${SHOTS}/portal-mobile-upload.png`, { hash: "upload", viewport: "mobile" }],
  [`${DEMO}/02-files-root.png`, { hash: "files" }],
  [`${DEMO}/07-process-tab.png`, { hash: "process" }],
  [`${DEMO}/09-history-tab.png`, { hash: "history" }],
  [`${DEMO}/10-analytics-tab.png`, { hash: "analytics" }],
  [`${DEMO}/15-favorites-empty.png`, { hash: "favorites" }],
  [`${DEMO}/16-versions-tab.png`, { hash: "versions" }],
  [`${DEMO}/17-audit-tab.png`, { hash: "audit" }],
  [`${DEMO}/20-sidebar-layout-files.png`, { hash: "files" }],
  [`${DEMO}/21-sidebar-favorites.png`, { hash: "favorites" }],
  [`${DEMO}/22-sidebar-ai-processing.png`, { hash: "process" }],
  [`${DEMO}/23-recent-files.png`, { hash: "recent" }],
  [`${DEMO}/23-sidebar-audit.png`, { hash: "audit" }],
  [`${DEMO}/portal-i18n-ja.png`, { hash: "files", lang: "ja" }],
  [`${DEMO}/portal-i18n-en.png`, { hash: "files", lang: "en" }],
  [`${DEMO}/portal-i18n-ko.png`, { hash: "files", lang: "ko" }],
  [`${DEMO}/portal-i18n-zh-cn.png`, { hash: "files", lang: "zh-CN" }],
  [`${DEMO}/portal-snapshots-connected.png`, { hash: "snapshots" }],
  [`${DEMO}/portal-lock-connected.png`, { hash: "lock" }],
  [`${DEMO}/portal-arp-status-connected.png`, { hash: "arp" }],
);

// --- Arguments ------------------------------------------------------------------
const argv = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : fallback;
};
if (argv.includes("--list")) {
  for (const [n, o] of [...BLOG, ...REPLACE]) console.log(n, JSON.stringify({ ...o, act: o.act ? "yes" : undefined }));
  process.exit(0);
}
const BASE = opt("base", "http://localhost:5173");
const SET = opt("set", "blog");
const OUT = resolve(opt("out", SET === "blog" ? "out" : "../.."));
const ONLY = opt("only", "")?.split(",").filter(Boolean) ?? [];
const SUBS_PATH = resolve(opt("subs", "../../docs/screenshots/originals/portal-refresh/_substitutions.json"));
const USER = opt("user", process.env.PORTAL_USER);
const PASSWORD = opt("password", process.env.PORTAL_PASSWORD);
if (!USER || !PASSWORD) {
  console.error("Set PORTAL_USER and PORTAL_PASSWORD, or pass --user and --password.");
  process.exit(2);
}
if (!existsSync(SUBS_PATH)) {
  console.error(`Substitution file not found: ${SUBS_PATH}\nRefusing to capture without masking.`);
  process.exit(2);
}
const subsFile = JSON.parse(readFileSync(SUBS_PATH, "utf8"));
// Longest key first, so a name that contains another is not replaced in part.
const LITERAL = [...subsFile.substitutions].sort((a, b) => b[0].length - a[0].length);
const FORBIDDEN = subsFile.forbidden ?? [];

// --- Masking, run inside the page ------------------------------------------------
/** Replace text, then return what remains that should not be on screen. */
async function maskAndScan(page) {
  return page.evaluate(
    ({ literal, forbidden, safe, loading }) => {
      const SAFE = new RegExp(safe);
      const mapped = new Map();
      const ipOf = (ip) => {
        if (SAFE.test(ip)) return ip;
        if (!mapped.has(ip)) mapped.set(ip, `198.51.100.${10 + mapped.size}`);
        return mapped.get(ip);
      };
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const writes = [];
      while (walker.nextNode()) {
        const node = walker.currentNode;
        let v = node.nodeValue || "";
        const before = v;
        for (const [from, to] of literal) if (v.includes(from)) v = v.split(from).join(to);
        v = v.replace(/\b\d{1,3}(?:\.\d{1,3}){3}\b/g, ipOf);
        v = v.replace(/\b\d{12}\b/g, "123456789012");
        v = v.replace(/\bfs-0[0-9a-f]{16}\b/g, "fs-0123456789abcdef0");
        v = v.replace(/\bsvm-0[0-9a-f]{16}\b/g, "svm-0123456789abcdef0");
        v = v.replace(/\bfsvol-0[0-9a-f]{16}\b/g, "fsvol-0123456789abcdef0");
        v = v.replace(/\bFsxId[0-9a-f]{17,}\b/g, "FsxIdCluster");
        if (v !== before) writes.push([node, v]);
      }
      for (const [node, v] of writes) node.nodeValue = v;
      const text = document.body.innerText;
      const left = [];
      for (const ip of text.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/g) ?? []) if (!SAFE.test(ip)) left.push(`ip:${ip}`);
      for (const id of text.match(/\b\d{12}\b/g) ?? []) if (id !== "123456789012") left.push("account-id");
      for (const id of text.match(/\bfs-0[0-9a-f]{16}\b/g) ?? []) if (id !== "fs-0123456789abcdef0") left.push("fs-id");
      if (/amazonaws\.com/.test(text)) left.push("amazonaws.com");
      for (const w of forbidden) if (text.toLowerCase().includes(w.toLowerCase())) left.push(`word:${w}`);
      return { replaced: writes.length, left: [...new Set(left)], loading: new RegExp(loading).test(text) };
    },
    { literal: LITERAL, forbidden: FORBIDDEN, safe: SAFE_IPV4.source, loading: LOADING.source },
  );
}

// --- Run -------------------------------------------------------------------------
const wanted = (SET === "blog" ? BLOG : SET === "replace" ? REPLACE : [...BLOG, ...REPLACE]).filter(
  ([name]) => ONLY.length === 0 || ONLY.some((o) => name.includes(o)),
);
if (wanted.length === 0) {
  console.error("No shot matches.");
  process.exit(2);
}

const browser = await chromium.launch({ headless: true, channel: opt("channel", "chrome") });
let failures = 0;
try {
  // Sign in once on the desktop context and reuse the session for the phone context.
  const first = await browser.newContext({ viewport: DESKTOP });
  const page0 = await first.newPage();
  await page0.goto(BASE);
  await page0.locator("input[name=username]").fill(USER);
  await page0.locator("input[type=password]").fill(PASSWORD);
  await page0.getByRole("button", { name: /^sign in$/i }).click();
  await page0.waitForSelector("nav[aria-label='Main navigation']", { timeout: 30000 });
  await page0.evaluate((k) => localStorage.setItem(k, "true"), WELCOME_KEY);
  const state = await first.storageState();
  await first.close();

  const ordered = [...wanted].sort(
    (a, b) =>
      (a[1].viewport === "mobile") - (b[1].viewport === "mobile") ||
      (a[1].lang ?? "ja").localeCompare(b[1].lang ?? "ja") ||
      (a[1].theme ?? "light").localeCompare(b[1].theme ?? "light"),
  );
  let ctx = null;
  let page = null;
  let key = "";
  for (const [name, o] of ordered) {
    const viewport = o.viewport === "mobile" ? MOBILE : DESKTOP;
    const lang = o.lang ?? "ja";
    const theme = o.theme ?? "light";
    const k = `${viewport.width}/${lang}/${theme}`;
    if (k !== key) {
      if (ctx) await ctx.close();
      ctx = await browser.newContext({ viewport, storageState: state, isMobile: o.viewport === "mobile", hasTouch: o.viewport === "mobile" });
      page = await ctx.newPage();
      await page.goto(BASE);
      await page.evaluate(([l, t, w]) => {
        localStorage.setItem("portal-locale", l);
        localStorage.setItem("portal-theme", t);
        localStorage.setItem(w, "true");
      }, [lang, theme, WELCOME_KEY]);
      key = k;
    }
    await page.goto(`${BASE}/#${o.hash}`);
    await page.reload();
    await page.waitForSelector("nav[aria-label='Main navigation'], button.sidebar-toggle", { timeout: 30000 });
    // The data screens wait on ONTAP; wait for the loading text to go, then let it settle.
    await page.waitForFunction((src) => !new RegExp(src).test(document.body.innerText), LOADING.source, { timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(800);
    if (o.act) await o.act(page);
    await page.waitForFunction((src) => !new RegExp(src).test(document.body.innerText), LOADING.source, { timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(500);
    const res = await maskAndScan(page);
    const file = SET === "blog" || !name.includes("/") ? join(OUT, name.endsWith(".png") ? name : `${name}.png`) : join(OUT, name);
    if (res.loading) {
      console.log(`SKIP ${name}: still loading`);
      failures++;
      continue;
    }
    if (res.left.length > 0) {
      console.log(`SKIP ${name}: unmasked text remains (${res.left.join(", ")})`);
      failures++;
      continue;
    }
    mkdirSync(dirname(file), { recursive: true });
    await page.screenshot({ path: file });
    console.log(`OK   ${name} (replaced ${res.replaced})`);
  }
  if (ctx) await ctx.close();
} finally {
  await browser.close();
}
process.exit(failures > 0 ? 1 : 0);
