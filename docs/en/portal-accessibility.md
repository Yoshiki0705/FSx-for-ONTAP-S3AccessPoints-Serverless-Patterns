# File Portal — Accessibility Statement

> Accessibility features implemented and guidance for further validation.

## Implemented Accessibility Features

### Keyboard Navigation

All interactive elements are operable via keyboard:
- `Tab` navigates between focusable elements
- `Enter` / `Space` activates buttons and links
- `Escape` closes modals and dropdowns
- Arrow keys navigate within lists and menus
- Focus indicators are visible on all interactive elements

### ARIA Markup

| Component | ARIA Implementation |
|-----------|-------------------|
| AgentChat messages | `role="log"` with `aria-label` |
| ActionApproval modal | `role="alertdialog"` with `aria-modal="true"` |
| Search results | `role="button"` with `tabIndex` on result items |
| File listing | `aria-label` on table/grid |
| Language switcher | `role="radiogroup"` with `aria-checked` |
| Mode selector pills | `role="radio"` with `aria-checked` |
| Alert messages | Dynamic content with appropriate live regions |

### Screen Reader Compatibility

- Chat messages include role identification (user/assistant/system)
- Tool execution traces are structured with `<details>`/`<summary>` for progressive disclosure
- File operation results include text alternatives
- Status badges include accessible text (not just color-coded)
- Error messages are announced to assistive technology

### Visual Accessibility

- **Color contrast**: Meets WCAG 2.1 AA minimum contrast ratios (4.5:1 for text, 3:1 for UI components)
- **Dark/Light mode**: Respects `prefers-color-scheme` media query
- **Text sizing**: Uses `rem` units; scales with browser text size settings
- **No reliance on color alone**: Status indicators use both color and icon/text

### Internationalization (i18n)

- 8 languages supported with runtime switching
- Language auto-detection from `navigator.language`
- No flags used for language selection (languages ≠ countries)
- All user-facing text is translatable; technical terms remain in English

---

## Known Limitations

| Area | Limitation | Workaround |
|------|-----------|-----------|
| PDF Preview | Embedded PDF viewer may not be screen-reader accessible | Use file download + native PDF reader |
| ASCII art (architecture diagrams) | Not meaningful to screen readers | Alt text describes the architecture in prose |
| Drag-and-drop (image upload) | Keyboard alternative exists (file input button) | Click 📎 button instead |
| Real-time typing indicator | Animation may be distracting | Respects `prefers-reduced-motion` |

---

## WCAG 2.1 Compliance Note

This portal implements accessibility features aligned with WCAG 2.1 Level AA guidelines. However, **full WCAG 2.1 AA compliance requires manual testing with assistive technologies (screen readers, switch devices, voice control) and expert accessibility review**. The developers have not yet conducted formal accessibility audits by certified specialists.

Organizations with regulatory accessibility requirements (e.g., Section 508, JIS X 8341-3, EN 301 549) should conduct independent accessibility testing before production deployment.

---

## Reporting Issues

If you encounter accessibility barriers, please:
1. Open a GitHub Issue with the `accessibility` label
2. Describe the barrier, assistive technology used, and browser/OS version
3. We will prioritize fixes for reported barriers

---

## Related Documents

- [User Guide](./portal-user-guide.md)
- [Implementation Guide](../../solutions/amplify-portal/docs/IMPLEMENTATION.md)
