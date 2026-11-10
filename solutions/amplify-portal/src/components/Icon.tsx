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
