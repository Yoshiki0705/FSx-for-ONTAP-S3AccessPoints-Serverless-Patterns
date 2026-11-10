/**
 * The icon of an agent or team member.
 *
 * Agents are stored records, and the `icon` field holds whatever string the
 * client saved. Records made before the line icons were added hold an emoji, and
 * the agent-chat backend still defaults to one. New records hold an icon name.
 * This component draws both, so no stored record changes.
 */
import { Icon, isIconName, type IconName } from "./Icon";

/** The icons offered when creating or editing an agent. */
export const AGENT_ICON_CHOICES: IconName[] = [
  "bot", "bar-chart", "search", "brain", "shield", "folder",
  "zap", "flask", "clipboard-list", "target", "lightbulb", "building",
];

/** Emoji that earlier versions offered, mapped to the icon that replaced them. */
const LEGACY_EMOJI: Record<string, IconName> = {
  "🤖": "bot", // check-ui-ignore
  "📊": "bar-chart", // check-ui-ignore
  "🔍": "search", // check-ui-ignore
  "🧠": "brain", // check-ui-ignore
  "🛡": "shield", // check-ui-ignore
  "📁": "folder", // check-ui-ignore
  "⚡": "zap", // check-ui-ignore
  "🔬": "flask", // check-ui-ignore
  "📋": "clipboard-list", // check-ui-ignore
  "🎯": "target", // check-ui-ignore
  "💡": "lightbulb", // check-ui-ignore
  "🏭": "building", // check-ui-ignore
};

/** The icon name for a stored value, or undefined when the value is neither a name nor a known emoji. */
export function resolveAgentIcon(value: string | undefined): IconName | undefined {
  if (!value) return "bot";
  const bare = value.replace(/\uFE0F/g, "");
  if (isIconName(bare)) return bare;
  return LEGACY_EMOJI[bare];
}

/** Draws a stored agent icon. A value that is not a known name or emoji is shown as the text it is. */
export function AgentIcon({ value, className }: { value: string | undefined; className?: string }) {
  const name = resolveAgentIcon(value);
  if (name) return <Icon name={name} className={className} />;
  return <span className={className}>{value}</span>;
}
