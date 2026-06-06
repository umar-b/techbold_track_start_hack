---
name: techbold AI Service Desk
description: Technician workspace built on techbold's navy-and-gold brand identity
colors:
  navy: "#262b4b"
  navy-mid: "#373652"
  gold: "#fcb514"
  gold-light: "#f7cf42"
  warm-surface: "#f3f2ea"
  white: "#ffffff"
  off-white: "#fbfbfb"
  border-light: "#e5e7ea"
  border-mid: "#dadada"
  muted: "#808080"
  muted-dark: "#747474"
typography:
  display:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', Arial, sans-serif"
    fontSize: "clamp(1.75rem, 4vw, 3rem)"
    fontWeight: 900
    lineHeight: 1.1
    letterSpacing: "-0.03em"
    fontVariation: "text-transform: uppercase"
  headline:
    fontFamily: "'Inter', 'Denim WD', Arial, sans-serif"
    fontSize: "clamp(1.25rem, 2.5vw, 1.875rem)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: "'Inter', 'Denim WD', Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "'Inter', 'Denim WD', Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.05em"
  mono:
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  none: "0px"
  sm: "2px"
  md: "4px"
  lg: "12px"
  pill: "50px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  "2xl": "64px"
  "3xl": "96px"
components:
  button-primary:
    backgroundColor: "{colors.navy-mid}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "13px 29px"
  button-primary-hover:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "13px 29px"
  button-gold:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.navy}"
    rounded: "{rounded.none}"
    padding: "13px 29px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.navy}"
    rounded: "{rounded.none}"
    padding: "12px 28px"
  badge-open:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.navy}"
    rounded: "{rounded.sm}"
    padding: "3px 8px"
  badge-done:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.white}"
    rounded: "{rounded.sm}"
    padding: "3px 8px"
---

# Design System: techbold AI Service Desk

## 1. Overview

**Creative North Star: "The Technician's Console"**

This is a precision instrument, not a dashboard. Every screen exists to help a trained professional solve a live incident faster and with more confidence. The design draws directly from techbold's established brand: deep navy anchors the structure, amber gold marks what demands attention, and sharp edges signal authority. Nothing decorative. Nothing that makes the technician hunt for the next action.

The system rejects the generic SaaS-admin look — the light-gray-everything, brand-agnostic "tool" that could belong to any company. This workspace belongs visibly to techbold. It also rejects the hacker-terminal cliché: black backgrounds and green monospace are atmosphere, not usability. The visual logic here is corporate precision: a Bloomberg terminal meets the techbold brand standards guide.

The AI is a participant, not the hero. It proposes; the technician decides. The visual hierarchy enforces this — human actions are primary, AI output is clearly labeled and secondary until the technician acts on it.

**Key Characteristics:**
- Navy-and-gold chromatics from techbold's live website, exact values
- Sharp corners (border-radius: 0 on interactive elements)
- Uppercase labels and CTAs, tight tracking
- Monospace font for all shell output, commands, and logs
- Gold used sparingly as a signal color, never as background texture

## 2. Colors: The Navy-and-Gold System

Techbold's palette is one of commitment. The navy is near-black and holds authority; the gold is unmissable and earns its appearances.

### Primary
- **Techbold Gold** (`#fcb514` / oklch(79% 0.18 72)): The brand accent. Used on hover states, active nav items, status badges (OPEN), and call-to-action highlights. Never as body text on white — contrast is insufficient. Always paired with navy or dark text.
- **Techbold Gold Light** (`#f7cf42` / oklch(85% 0.17 84)): Tinted highlight, progress fills, selected state backgrounds.

### Secondary
- **Deep Navy** (`#262b4b` / oklch(21% 0.07 268)): Primary surface for the top navigation, sidebar headers, and the most dominant structural elements. Text on this surface is white.
- **Navy Mid** (`#373652` / oklch(27% 0.07 272)): Button backgrounds, card headers, table row headers. The interactive-element navy.

### Neutral
- **Warm Surface** (`#f3f2ea` / oklch(96% 0.01 97)): Page background. Warm off-white that keeps the navy from feeling cold. Not cream — it is the exact value from techbold's live site.
- **White** (`#ffffff`): Card backgrounds, modal surfaces, input backgrounds.
- **Off-White** (`#fbfbfb`): Alternate card surface, striped table rows.
- **Border Light** (`#e5e7ea`): Dividers, card outlines, input borders.
- **Border Mid** (`#dadada`): Stronger dividers, section separators.
- **Muted** (`#808080`): Secondary text, placeholders, disabled states.
- **Muted Dark** (`#747474`): Supporting labels where muted is too light.

### Named Rules
**The Gold-Is-Signal Rule.** Gold appears on ≤15% of any screen. When gold is on screen, it is pointing at something — a status, an action, a live state. If gold is everywhere, the signal is gone. Ration it.

**The Navy-as-Structure Rule.** Deep navy (`#262b4b`) belongs on structural, non-interactive surfaces (nav bar, sidebar top, section headers). The mid-navy (`#373652`) belongs on interactive elements (buttons, toggles). Do not invert these.

## 3. Typography

**Display Font:** Barlow Condensed, 900 weight (approximates ProximaNova Condensed Black used on techbold.at; swap to the original if licensed)
**Body Font:** Inter (approximates Denim WD used on techbold.at; swap if licensed)
**Mono Font:** JetBrains Mono (for all shell commands, output, logs)

**Character:** Condensed display pairs with a clean, readable sans for body copy — professional compression at the top, comfortable openness in the content. The monospace is unapologetically functional: every command, every log line, every SSH output reads in Mono.

### Hierarchy
- **Display** (Barlow Condensed 900, clamp(1.75rem–3rem), lh 1.1, uppercase, -0.03em): Page-level titles only. Reserved for the workspace header and section anchors.
- **Headline** (Inter 700, clamp(1.25rem–1.875rem), lh 1.2, -0.02em): Card titles, ticket subject lines, panel headers.
- **Title** (Inter 600, 1.125rem, lh 1.3): Subsection labels within panels, column headers in tables.
- **Body** (Inter 400, 1rem, lh 1.5): Ticket descriptions, AI reasoning, activity log prose. Max 72ch.
- **Label** (Inter 700, 0.75rem, lh 1, 0.05em tracking, uppercase): Status badges, field labels, button text, nav items. Matches techbold's uppercase button convention exactly.
- **Mono** (JetBrains Mono 400, 0.875rem, lh 1.6): All shell commands, SSH output, log entries, code blocks.

### Named Rules
**The Uppercase-Is-a-Label Rule.** Uppercase text is reserved for labels: nav items, button text, status badges, field labels. Body copy, ticket descriptions, and AI output are always sentence case. Uppercase prose signals a label; sentence-case prose is content.

## 4. Elevation

This system is flat by default. Surfaces at rest use background color difference and border to establish hierarchy, not shadows. Shadows appear only when an element lifts out of the document flow — modals, dropdowns, popovers, floating panels.

Techbold's website uses minimal shadow; the workspace inherits that restraint. Depth is carried by the strong navy-to-warm-surface color contrast, not by blur.

### Shadow Vocabulary
- **Resting** (no shadow): Cards, inputs, nav items. The background-color difference is the signal.
- **Lift** (`box-shadow: 0 2px 8px rgba(38, 43, 75, 0.12)`): Hover state on interactive cards. Subtle lift to confirm the element is clickable.
- **Float** (`box-shadow: 0 8px 32px rgba(38, 43, 75, 0.18)`): Dropdowns, popovers, command confirmation dialogs.
- **Modal** (`box-shadow: 0 24px 64px rgba(38, 43, 75, 0.24)`): Full modal overlays.

### Named Rules
**The Flat-at-Rest Rule.** Shadows are state, not style. An element at rest is flat; it lifts on hover or when it floats above the document. If you find yourself adding a shadow to a resting card "to give it depth," use a `1px solid #e5e7ea` border instead.

## 5. Components

### Buttons
The button language is direct techbold: dark navy, sharp corners, uppercase label, tight padding. No gradients, no pill shapes, no softness.

- **Shape:** No radius (0px) — matches techbold's live site exactly
- **Primary:** Navy mid (`#373652`) background, white text, 13px 29px padding, Label typography (uppercase, 0.75rem, 700)
- **Hover / Active:** Background shifts to gold (`#fcb514`), white text remains. Transition: `background 200ms ease-out`
- **Gold variant:** Gold background, navy text — used for the highest-priority CTA on a page (e.g. "Submit Activity")
- **Ghost:** Transparent background, navy text, `1px solid #373652` border. Hover: navy fill, white text
- **Danger:** Used only on destructive actions (abort, discard). `#c0392b` background, white text. Never styled with gold

**Focus:** `outline: 2px solid #fcb514; outline-offset: 2px` — gold ring, always visible, never removed

### Status Badges
Compact uppercase labels that mirror techbold's label convention.

- **OPEN:** Gold (`#fcb514`) background, navy (`#262b4b`) text, 2px radius
- **PENDING:** Navy mid (`#373652`) background, white text, 2px radius
- **DONE:** Deep navy (`#262b4b`) background, white text, 2px radius

### Cards / Containers
- **Corner Style:** 4px radius (md) on cards — the only softening in an otherwise sharp system
- **Background:** White (`#ffffff`) on warm-surface page background
- **Shadow Strategy:** No resting shadow. `1px solid #e5e7ea` border. Lift shadow on hover (interactive cards only)
- **Border:** `1px solid #e5e7ea` by default; `1px solid #fcb514` on selected or active state
- **Internal Padding:** 24px (lg) standard; 16px (md) for compact/list cards

### Inputs / Fields
- **Style:** `1px solid #dadada` border, white background, 4px radius, 0.875rem body font
- **Focus:** Border shifts to navy (`#262b4b`), no glow. Clean and sharp
- **Placeholder:** `#808080` (muted). Must clear 4.5:1 against white — `#808080` passes
- **Error:** `1px solid #c0392b` border, error message in `#c0392b` below field, 0.75rem label font
- **Disabled:** `#fbfbfb` background, `#dadada` border, `#808080` text. No interaction

### Navigation
- **Style:** White background top nav with deep navy (`#262b4b`) text, uppercase label font
- **Active item:** Gold (`#fcb514`) underline or left border (4px solid), navy text stays
- **Hover:** Gold background strip, navy text — matches techbold.at nav hover exactly
- **Mobile:** Hamburger toggle, full-screen overlay nav with navy background and white text

### Command Approval Panel (Signature Component)
The human-in-the-loop core. Every AI-proposed command surfaces here before execution.

The panel shows: the proposed command in monospace on a `#f3f2ea` background (not dark — this is not a terminal, it is a workspace); the AI's stated reason in body text; and three actions: **Approve** (primary button), **Edit** (ghost button), **Reject** (text link in muted). The three actions are always in this left-to-right order. The panel header is labeled "AI Proposal" in uppercase label style with the gold badge. Commands waiting for approval have a `1px solid #fcb514` left accent border on the panel.

### Log Viewer
Scrollable panel showing executed commands and their output. All text in Mono font. Timestamp in muted (`#808080`), command in navy, stdout in body color, stderr in `#c0392b`. Background `#f3f2ea` (warm surface, not black — not a terminal aesthetic). Line height 1.6 for readability at extended viewing.

## 6. Do's and Don'ts

### Do:
- **Do** use `#262b4b` (deep navy) as the structural anchor — top nav, sidebar headers, the dominant dark surface
- **Do** use `#fcb514` (gold) to mark what is active, selected, or demanding attention — and then stop
- **Do** use `border-radius: 0` on all buttons; use `4px` on cards and inputs — the mix is intentional
- **Do** use uppercase + 0.05em tracking for all label text: nav items, button labels, status badges, field labels
- **Do** render all shell commands and SSH output in JetBrains Mono on the warm-surface background (`#f3f2ea`) — not a dark terminal background
- **Do** keep body text at a maximum 72ch line length in any reading context
- **Do** pair gold backgrounds with navy text only — never gold text on white (fails contrast)
- **Do** label every AI output clearly: "AI Proposal", "AI Reasoning", "AI Generated" in the label style
- **Do** make the Approve / Edit / Reject triad the most prominent element when a command is pending
- **Do** include `@media (prefers-reduced-motion: reduce)` alternatives for all transitions

### Don't:
- **Don't** use a dark or black terminal background anywhere in the UI — this is a branded corporate tool, not a hacker interface
- **Don't** use gold (`#fcb514`) as body text color on white or light backgrounds — contrast fails WCAG AA
- **Don't** use border-radius greater than 12px on any element — the brand language is sharp
- **Don't** add gradients — background fills are solid; techbold's site uses no gradients
- **Don't** use purple, neon, or glow effects — wrong register for a professional IT firm
- **Don't** use the cream / sand / beige default (`oklch L 0.84-0.97, C < 0.06, hue 40-100`) as the UI background; use the exact warm-surface value (`#f3f2ea`) extracted from techbold's live site
- **Don't** make the AI the hero — the AI proposes, the technician decides; never style AI output more prominently than human actions
- **Don't** use glassmorphism or frosted glass effects — off-brand
- **Don't** scatter gold across every section as decoration; the Gold-Is-Signal Rule makes each appearance matter
- **Don't** use consumer chat-interface patterns (bubble messages, avatar + text rows) for the AI interaction — use structured proposal panels
