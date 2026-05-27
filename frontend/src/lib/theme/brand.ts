/**
 * Single source of truth for the brand palette, typography, and theme.
 *
 * To rebrand the entire app:
 *   1. Change `brandPalette` for primary/accent colors.
 *   2. Change `surfacePalette` for chrome (sidebar/topbar) surfaces.
 *   3. Change the `next/font` imports in `app/layout.tsx` to swap typography.
 *
 * The whole UI re-derives — components consume Fluent tokens, which we
 * map to these values via `appTheme`. Plus `appTokens` for app-specific
 * surfaces that Fluent's neutral tokens don't cover well (sidebar bg,
 * table header bg, etc.).
 *
 * Anti-pattern: hard-coding hex / font-family values inside `makeStyles`
 * blocks. Always reach for `tokens.*` or `appTokens.*` so the design
 * system stays one-file-changeable.
 */

import { type Theme, webLightTheme } from "@fluentui/react-components";

// ── Brand palette ─────────────────────────────────
// The "Bold blue" used for primary buttons, active states, links.
// Override these for a different brand.
export const brandPalette = {
  primary: "#0F6CBD",
  primaryHover: "#115EA3",
  primaryPressed: "#0E4775",
  primarySelected: "#0F548C",
} as const;

// ── Surface palette (chrome vs content) ───────────
// Light chrome distinct from content for visual hierarchy.
export const surfacePalette = {
  // App shell
  chromeBg: "#F5F7FA",         // sidebar background
  chromeBgHover: "#E8ECF3",    // hover state for nav items
  chromeBgActive: "#E1E8F2",   // active/selected nav item
  chromeBorder: "#E1E5EB",     // separator between chrome and content
  chromeText: "#1F2A3C",
  chromeTextMuted: "#5A6B7D",

  // Content
  contentBg: "#FFFFFF",
  pageBg: "#FAFBFC",

  // Data table surfaces — distinct from chrome so the table feels like a
  // "data card" within the page, not part of the chrome.
  tableHeaderBg: "#F7F9FC",    // column header strip
  tableHeaderText: "#475569",
  tableRowHover: "#F4F6FA",
  tableRowStripe: "#FAFBFD",   // optional zebra
  tableBorder: "#E5E9F0",
} as const;

// ── Typography ────────────────────────────────────
// CSS variables `--font-body` and `--font-mono` are declared by
// `next/font/google` in `app/layout.tsx`. They cascade into Fluent UI
// through the `fontFamily*` overrides in `appTheme` below — every Fluent
// component picks up the brand fonts automatically.
const FONT_BODY =
  "var(--font-body), -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";
const FONT_MONO =
  "var(--font-mono), Menlo, Monaco, Consolas, 'Courier New', monospace";

// ── Fluent theme extension ────────────────────────
// Components use `tokens.colorBrandXxx` / `tokens.fontFamilyXxx` — these
// tokens read the values below.
export const appTheme: Theme = {
  ...webLightTheme,

  // Brand color tokens (used by primary buttons, links, focus rings)
  colorBrandBackground: brandPalette.primary,
  colorBrandBackgroundHover: brandPalette.primaryHover,
  colorBrandBackgroundPressed: brandPalette.primaryPressed,
  colorBrandBackgroundSelected: brandPalette.primarySelected,
  colorBrandStroke1: brandPalette.primary,
  colorBrandStroke2: brandPalette.primaryHover,
  colorBrandForeground1: brandPalette.primary,
  colorBrandForeground2: brandPalette.primaryHover,
  colorBrandForegroundLink: brandPalette.primary,
  colorBrandForegroundLinkHover: brandPalette.primaryHover,
  colorBrandForegroundLinkPressed: brandPalette.primaryPressed,

  // Typography — all Fluent components read these.
  fontFamilyBase: FONT_BODY,
  fontFamilyMonospace: FONT_MONO,
  fontFamilyNumeric: FONT_MONO, // tabular numerals for tables, counters, prices
};

// ── App-level semantic tokens ─────────────────────
// Surfaces and metrics Fluent's neutral tokens don't cover with the
// nuance we want. Components use these for sidebar, topbar, table chrome,
// etc.
export const appTokens = {
  // App shell chrome
  chromeBg: surfacePalette.chromeBg,
  chromeBgHover: surfacePalette.chromeBgHover,
  chromeBgActive: surfacePalette.chromeBgActive,
  chromeBorder: surfacePalette.chromeBorder,
  chromeText: surfacePalette.chromeText,
  chromeTextMuted: surfacePalette.chromeTextMuted,
  contentBg: surfacePalette.contentBg,
  pageBg: surfacePalette.pageBg,

  // Data table surfaces
  tableHeaderBg: surfacePalette.tableHeaderBg,
  tableHeaderText: surfacePalette.tableHeaderText,
  tableRowHover: surfacePalette.tableRowHover,
  tableRowStripe: surfacePalette.tableRowStripe,
  tableBorder: surfacePalette.tableBorder,

  // Typography (raw values, for non-Fluent contexts like inline elements
  // outside Fluent components). Prefer Fluent `tokens.fontFamilyBase`
  // when inside Fluent components.
  fontBody: FONT_BODY,
  fontMono: FONT_MONO,

  // Shell metrics — change once, reflects in layout + sidebar + topbar
  sidebarWidth: "260px",
  sidebarWidthCollapsed: "0px",
  topbarHeight: "56px",
  shellAnimationMs: "180ms",
} as const;
