/**
 * Line icons for the portal, drawn as inline SVG.
 *
 * Replaces emoji in the UI. Emoji render with the OS font, so their shape and
 * colour differ per platform and cannot follow the theme. These icons use
 * `currentColor`, so they take the colour of the surrounding text in both the
 * light and dark themes.
 *
 * The icon is decorative (`aria-hidden`). The accessible name comes from the
 * text next to it or from the `aria-label` of the button that contains it.
 */
import type { SVGProps } from "react";

/** Path data on a 24x24 grid, stroked with a 1.75 width. Add names here as screens move off emoji. */
const PATHS = {
  bell: ["M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z", "M10 21h4"],
  "bar-chart": ["M5 20v-9", "M12 20V4", "M19 20v-6"],
  bot: ["M4 9a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z", "M12 7V4", "M9 13v1.5", "M15 13v1.5", "M2 12.5v3", "M22 12.5v3"],
  camera: ["M4 8h3l2-3h6l2 3h3v11H4z", "M12 10.5a3.25 3.25 0 1 0 0 6.5 3.25 3.25 0 0 0 0-6.5z"],
  "clipboard-list": ["M9 3h6v3H9z", "M7 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1", "M9 11h6", "M9 15h6"],
  clock: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 7v5l3 2"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  cloud: ["M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9.5 4.25 4.25 0 0 1 17.5 18z"],
  folder: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  folders: ["M8 7V5a1 1 0 0 1 1-1h3l1.5 1.5H19a1 1 0 0 1 1 1V15a1 1 0 0 1-1 1h-2", "M4 9a1 1 0 0 1 1-1h3.5L10 9.5h6a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"],
  lock: ["M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z", "M8 11V7a4 4 0 0 1 8 0v4"],
  menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
  puzzle: ["M10 4a2 2 0 1 1 4 0v1h4v4h-1a2 2 0 1 0 0 4h1v4h-4v-1a2 2 0 1 0-4 0v1H6v-4h1a2 2 0 1 0 0-4H6V5h4z"],
  refresh: ["M20 11a8 8 0 0 0-14.5-4.5L4 8", "M4 4v4h4", "M4 13a8 8 0 0 0 14.5 4.5L20 16", "M20 20v-4h-4"],
  search: ["M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z", "M20 20l-4-4"],
  shield: ["M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"],
  star: ["M12 3l2.8 5.8 6.2.8-4.5 4.4 1.1 6.3L12 17.3 6.4 20.3l1.1-6.3L3 9.6l6.2-.8z"],
  upload: ["M12 16V4", "M7 9l5-5 5 5", "M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"],
  wrench: ["M14.7 6.3a4 4 0 0 0-5 5L3 18l3 3 6.7-6.7a4 4 0 0 0 5-5l-2.4 2.4-2.6-.6-.6-2.6z"],
  zap: ["M13 3L5 13h6l-1 8 8-10h-6z"],
  // Status and feedback
  "alert-triangle": ["M12 4L2.5 20h19z", "M12 10v4", "M12 17.25h.01"],
  ban: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M5.6 5.6l12.8 12.8"],
  check: ["M5 12.5l4.5 4.5L19 7"],
  "check-circle": ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M8 12.5l3 3 5-6"],
  "x-circle": ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M9 9l6 6", "M15 9l-6 6"],
  hourglass: ["M6 3h12", "M6 21h12", "M7 3v3a5 5 0 0 0 2.5 4.3L12 12l-2.5 1.7A5 5 0 0 0 7 18v3", "M17 3v3a5 5 0 0 1-2.5 4.3L12 12l2.5 1.7A5 5 0 0 1 17 18v3"],
  "thumbs-up": ["M7 11v9H4v-9z", "M7 11l4-7a2 2 0 0 1 2.5 2.5L12.5 10H18a2 2 0 0 1 2 2.4l-1.4 6A2 2 0 0 1 16.7 20H7"],
  "thumbs-down": ["M7 13V4H4v9z", "M7 13l4 7a2 2 0 0 0 2.5-2.5L12.5 14H18a2 2 0 0 0 2-2.4l-1.4-6A2 2 0 0 0 16.7 4H7"],
  // Locks
  "lock-keyhole": ["M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z", "M8 11V7a4 4 0 0 1 8 0v4", "M12 15v3"],
  unlock: ["M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1z", "M8 11V7a4 4 0 0 1 7.5-2"],
  key: ["M8 11a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M11 12l9-9", "M17 6l3 3", "M15 8l2 2"],
  // Files and content
  file: ["M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z", "M14 3v5h5"],
  "file-text": ["M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z", "M14 3v5h5", "M9 13h6", "M9 17h6"],
  image: ["M4 5h16v14H4z", "M9 8.5a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5z", "M4 17l5-5 4 4 3-3 4 4"],
  "folder-plus": ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M12 10v6", "M9 13h6"],
  "book-open": ["M12 6c-2-1.5-5-2-8-2v14c3 0 6 .5 8 2 2-1.5 5-2 8-2V4c-3 0-6 .5-8 2z", "M12 6v14"],
  paperclip: ["M20 11l-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7"],
  package: ["M3 7.5L12 3l9 4.5v9L12 21l-9-4.5z", "M3 7.5L12 12l9-4.5", "M12 12v9"],
  tag: ["M3 12V4h8l10 10-8 8z", "M8 7.5a.5.5 0 1 0 0 1 .5.5 0 0 0 0-1z"],
  type: ["M5 7V5h14v2", "M12 5v14", "M9 19h6"],
  link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
  copy: ["M9 9h11v11H9z", "M5 15V4h11"],
  // Actions
  download: ["M12 4v12", "M7 11l5 5 5-5", "M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"],
  eye: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z", "M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z"],
  pencil: ["M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19z", "M14.5 6.5l3 3"],
  plus: ["M12 5v14", "M5 12h14"],
  send: ["M21 3L3 11l7 2.5L12.5 21z", "M21 3L10 13.5"],
  trash: ["M4 7h16", "M9 7V4h6v3", "M6 7l1 13h10l1-13", "M10 11v6", "M14 11v6"],
  undo: ["M9 14L4 9l5-5", "M4 9h10.5a5.5 5.5 0 0 1 0 11H11"],
  shuffle: ["M3 7h4l10 10h4", "M3 17h4l3-3", "M14 10l3-3h4", "M18 4l3 3-3 3", "M18 14l3 3-3 3"],
  scissors: ["M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M8.5 7.5L20 19", "M8.5 16.5L20 5"],
  "arrow-right": ["M5 12h14", "M13 6l6 6-6 6"],
  settings: ["M4 7h10", "M18 7h2", "M14 5v4", "M4 17h2", "M10 17h10", "M6 15v4", "M4 12h4", "M12 12h8", "M8 10v4"],
  calendar: ["M4 6h16v14H4z", "M4 10h16", "M8 3v4", "M16 3v4"],
  hand: ["M8 12V6a1.5 1.5 0 0 1 3 0v5", "M11 11V4.5a1.5 1.5 0 0 1 3 0V11", "M14 11V6a1.5 1.5 0 0 1 3 0v8a6 6 0 0 1-6 6h-1a5 5 0 0 1-4-2l-3-4a1.5 1.5 0 0 1 2.4-1.8L8 15"],
  // People and communication
  user: ["M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M4 20a8 8 0 0 1 16 0"],
  users: ["M9 5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z", "M2.5 20a6.5 6.5 0 0 1 13 0", "M16 5.5a3.5 3.5 0 0 1 0 6.5", "M18 14a6.5 6.5 0 0 1 3.5 6"],
  message: ["M4 5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H9l-5 4z"],
  globe: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M3 12h18", "M12 3c3 3.5 3 14.5 0 18", "M12 3c-3 3.5-3 14.5 0 18"],
  // Ideas and AI
  brain: ["M9.5 4A3.5 3.5 0 0 0 6 7.5V8a3 3 0 0 0-2 3 3 3 0 0 0 1.5 2.6A3.5 3.5 0 0 0 9 19.5a2.5 2.5 0 0 0 3-1.3V5.8A2.5 2.5 0 0 0 9.5 4z", "M14.5 4A3.5 3.5 0 0 1 18 7.5V8a3 3 0 0 1 2 3 3 3 0 0 1-1.5 2.6A3.5 3.5 0 0 1 15 19.5a2.5 2.5 0 0 1-3-1.3V5.8A2.5 2.5 0 0 1 14.5 4z"],
  lightbulb: ["M9 18h6", "M10 21h4", "M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"],
  sparkles: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", "M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"],
  flask: ["M9 3h6", "M10 3v6l-5.5 9.5A1.5 1.5 0 0 0 5.8 21h12.4a1.5 1.5 0 0 0 1.3-2.5L14 9V3", "M7.5 15h9"],
  target: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z", "M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2z"],
  // Storage and infrastructure
  archive: ["M3 4h18v4H3z", "M5 8v12h14V8", "M10 12h4"],
  building: ["M5 21V4h9v17", "M14 9h5v12", "M3 21h18", "M8 8h2", "M8 12h2", "M8 16h2"],
  bug: ["M12 8a4 4 0 0 1 4 4v3a4 4 0 0 1-8 0v-3a4 4 0 0 1 4-4z", "M9 6l1.5 2.2", "M15 6l-1.5 2.2", "M4 12h4", "M16 12h4", "M5 19l3-2", "M19 19l-3-2"],
  database: ["M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z", "M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6", "M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"],
  "git-branch": ["M6 3v12", "M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M18 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z", "M18 9v1a6 6 0 0 1-6 6H9"],
  "hard-drive": ["M3 14l3-9h12l3 9v5H3z", "M3 14h18", "M7 17h.01"],
  monitor: ["M3 4h18v12H3z", "M8 20h8", "M12 16v4"],
  plug: ["M9 3v5", "M15 3v5", "M6 8h12v3a6 6 0 0 1-12 0z", "M12 17v4"],
  server: ["M4 5h16v6H4z", "M4 13h16v6H4z", "M8 8h.01", "M8 16h.01"],
  signal: ["M4 13a8 8 0 0 1 16 0", "M8 13a4 4 0 0 1 8 0", "M12 13h.01"],
  smartphone: ["M7 3h10v18H7z", "M11 18h2"],
  "trending-up": ["M3 17l6-6 4 4 8-8", "M15 7h6v6"],
  // Theme
  moon: ["M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"],
  sun: ["M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M12 2v2", "M12 20v2", "M2 12h2", "M20 12h2", "M4.9 4.9l1.4 1.4", "M17.7 17.7l1.4 1.4", "M4.9 19.1l1.4-1.4", "M17.7 6.3l1.4-1.4"],
  flame: ["M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z"],
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  /** Width and height. Defaults to the surrounding font size. */
  size?: number | string;
}

/** Draws one line icon in the colour of the surrounding text. */
export function Icon({ name, size = "1em", className, ...rest }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className ? `icon ${className}` : "icon"}
      {...rest}
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

export type StatusTone = "ok" | "warning" | "error" | "neutral" | "off";

/**
 * A small filled circle that shows a state next to a text label.
 * The label stays the source of the meaning; the dot only adds colour.
 */
export function StatusDot({ tone }: { tone: StatusTone }) {
  return <span className={`state-dot state-dot-${tone}`} aria-hidden="true" />;
}

/** Whether a string is the name of an icon in this file. */
export function isIconName(value: string): value is IconName {
  return Object.prototype.hasOwnProperty.call(PATHS, value);
}
