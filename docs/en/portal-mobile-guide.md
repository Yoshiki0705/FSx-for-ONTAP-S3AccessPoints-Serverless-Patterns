# Using the portal on a phone — File Portal walkthrough

🌐 **Language / 言語**: [日本語](../ja/portal-mobile-guide.md) | **English**

> A walkthrough for people using the file portal from a phone browser. **No deployment knowledge required.**
> Each step carries the screen it describes, so you can follow it with the phone in your hand.

**There is no app to install.** Open the same URL you would on a desktop. Verified on Safari (iOS) and Chrome (Android).

---

## Contents

| What you want | Section |
|---------------|---------|
| Just open it and sign in | [1. Sign in](#1-sign-in) |
| Dismiss the notice that appeared first, or see it again | [The notice on first sign-in](#the-notice-on-first-sign-in) |
| Know what is where on screen | [2. The layout](#2-the-layout) |
| Open a folder, find a file | [3. Moving through folders](#3-moving-through-folders) |
| Share, rename or delete one file | [4. Acting on one file](#4-acting-on-one-file) |
| Delete several files at once | [5. Acting on several at once](#5-acting-on-several-at-once) |
| Add a photo or a document | [6. Adding files](#6-adding-files) |
| Have AI summarise something | [7. Running AI processing](#7-running-ai-processing) |
| Get a deleted file back | [8. Looking at an earlier state](#8-looking-at-an-earlier-state) |
| Change the language or use dark mode | [9. Changing the display](#9-changing-the-display) |
| Something is not working | [When something goes wrong](#when-something-goes-wrong) |

---

## What you need

| Requirement | Note |
|-------------|------|
| The portal URL | From your administrator. It starts with `https://` |
| An email address and password | An account your administrator created. Plus an authenticator app if MFA is on |
| A browser | Safari on iOS, Chrome on Android. Current version recommended |

**All three come from whoever set the portal up.** If you were given a URL but not the instructions, or
you have no account yet, ask them; their side of it is the
[handover and support guide](../../solutions/amplify-portal/docs/portal-handover-guide.en.md).

> **It has to be `https://`.** The portal uses browser features that are only available in a secure
> context for password handling and copying, so an `http://` URL — a development machine on the LAN,
> for instance — cannot complete sign-in. **If you were given an `http://` URL, ask for an `https://`
> one**; it is not something you can work around. Administrators: see
> [Getting Started, "Checking it on a real phone"](../../solutions/amplify-portal/docs/GETTING-STARTED.en.md#checking-it-on-a-real-phone).

---

## 1. Sign in

Opening the URL gives you this.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-signin.png" alt="The sign-in screen on a phone" width="320">

1. Enter your address under **Email**
2. Enter your password under **Password** (the eye icon reveals what you typed)
3. Tap **Sign in**

A password manager's autofill works normally. The input fields are at least 16px, so tapping one does
not make the page zoom in.

> **This screen is English only.** Everything after sign-in follows your chosen language. The sign-in
> screen comes from the authentication component and is not currently translated.

### The notice on first sign-in

**The first time only**, signing in brings up a "Welcome to File Portal" notice in the middle of the
screen. It sits over the file list, so **the list is not usable until you dismiss it.**

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-onboarding.png" alt="The first-run notice on a phone" width="320">

There are three cards, covering what the portal is for.

| Card | Subject |
|------|---------|
| 📂 | Browsing files |
| ⚡ | Running AI processing |
| 🔒 | Protecting data — snapshots, locks, ARP |

| Control | What happens |
|---------|--------------|
| **Next →** | Moves to the next card. On the third it becomes **Get Started 🚀**, which closes the notice |
| **●●●** (the dots) | Jumps straight to that card |
| Outside the notice (the dimmed area) | Closes it, part-way through if you like |
| **Don't show again** | Tick it before closing and the notice stops appearing |

> **"Don't show again" is remembered per browser.** Another device, another browser, or private
> browsing will show it again. That is not a fault.

---

## 2. The layout

Signing in opens the file list.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-files.png" alt="The file list on a phone" width="320">

**Along the top of the screen**, from the left:

| Control | What it does |
|---------|--------------|
| **☰** | Opens the navigation menu |
| ☀️ 🌙 🖥️ | Switches the theme. → [Section 9](#9-changing-the-display) |
| 🌐 | Switches the language. → [Section 9](#9-changing-the-display) |
| ⏻ | Signs out |

**The menu starts hidden on a phone.** The screen is narrow, so it only appears — over the content —
when you ask for it.

> **The buttons above the list stack vertically.** "Process this folder", "New folder" and the rest wrap
> two per line, so **you scroll once to reach the file list**. After the first time you know where it is.

> **The last row of the list sits behind the browser toolbar.** Safari on iOS and Chrome on Android
> overlay the address bar at the bottom of the screen, and a row goes under it. **Scroll down a little
> and the toolbar shrinks out of the way.** It is not a fault in the portal.

---

### Opening and closing the menu

Tap **☰** and the menu slides in from the left.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-drawer.png" alt="The navigation menu open on a phone" width="320">

- **☰** becomes **✕**; tapping it again closes the menu
- **Tapping the dimmed area also closes it**, for when you opened it without meaning to pick anything
- The device's **back** gesture and **Esc** (external keyboard) close it too
- Choosing an item **closes it automatically** and opens that screen

The menu has four groups. "Administration" is absent if your account does not hold admin rights.

| Group | Items |
|-------|-------|
| Browse | All files / Favourites / Recent / Upload |
| AI & processing | AI processing / Job history / Analytics |
| Data protection | Snapshots / Lock / ARP/AI |
| Administration | Resource management / Version diff / Audit trail |

---

## 3. Moving through folders

Tap a folder name to enter it.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-folder.png" alt="Inside a folder on a phone" width="320">

- The **`/ jaws90 / logs`** line near the top is where you are. **Tap any name in it to go back there**
- The **`..`** entry at the top of the list also goes up one level
- In a large folder, **"Load more"** at the bottom fetches the rest
- The **"Filter by name"** field narrows the current folder only

Each row carries, from the left: a **checkbox**, a **☆**, a **file icon**, **⋮**, and the **name**.

| Tap | What happens |
|-----|--------------|
| The name | Opens it — a preview for supported types, otherwise a download |
| The file icon | Downloads it, or selects it as a target for AI processing |
| ☆ | Adds to or removes from favourites |
| ⋮ | The rest of the actions (next section) |
| The checkbox | Selects it for a bulk action ([Section 5](#5-acting-on-several-at-once)) |

> **The "size" and "modified" columns are dropped on a narrow screen.** Sorting by name still works.
> Open the file on a desktop if you need the full attributes.

### Images show a small picture instead of an icon

A row for an image file carries **a small picture of its contents** rather than an icon,
so you can tell them apart before opening anything.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-thumbnails.png" alt="A file list on a phone with small pictures of the images" width="320">

In the example above five images have pictures and `estimate.pdf` keeps its 📕.

- **Only images get one.** PDFs and documents keep their icon, which is not a fault
- **Sometimes there is none.** An unsupported format such as SVG, a file that is too
  large, or a file whose extension says image while its contents say otherwise, all keep
  the icon
- **Opening the file still shows the original.** The list shows a display copy; the file
  itself is not changed
- The small pictures exist **to save data**: opening a folder does not download every
  original at full size


---

## 4. Acting on one file

Tapping **⋮** on a row **brings up a sheet from the bottom of the screen**.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-row-menu.png" alt="The row action sheet on a phone" width="320">

**The sheet names the file at the top**, so there is no doubt which row you are acting on.

| Icon | Action |
|------|--------|
| 🔗 | Create a share link, with an expiry |
| 🏷️ | Edit tags |
| 📋 | Copy or move elsewhere |
| ✏️ | Rename |
| 🗑️ | Move to the recycle bin |

Tap outside the sheet to dismiss it.

> **Why it comes from the bottom**: as a dropdown attached to the middle of a row, the rightmost
> actions (🗑️ among them) fell **outside the screen and could not be tapped**. Pinned to the bottom,
> all five are reachable regardless of where in the row you tapped. Each is at least 44×44 pixels.

---

## 5. Acting on several at once

Tapping the **checkbox** at the left of a row starts a selection.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-selection.png" alt="Several files selected on a phone" width="320">

- **"n selected"** and the available actions appear above the list
- **Move to recycle bin** deletes them together, recoverably
- **Clear selection** cancels
- The checkbox in the table header selects **everything currently listed**

> **Deleting means "move to the recycle bin".** Nothing disappears immediately, so a mistake is
> recoverable from there. Permanent deletion is a separate action inside the recycle bin.

---

## 6. Adding files

Choose **📤 Upload** from the menu.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-upload.png" alt="The upload screen on a phone" width="320">

- **Choose files** opens the iOS/Android picker, where Photos, Files and the camera are all options
- Pick the destination folder before starting
- Large files are sent in parts, so switching away from the screen does not interrupt them —
  but **closing the browser does**

> **Mind the data**: large uploads and folder ZIP downloads move a lot of bytes. On a mobile
> connection, check the count and the size before starting.

---

## 7. Running AI processing

Choose **⚡ AI processing** from the menu.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-ai.png" alt="The AI processing screen on a phone" width="320">

1. Choose the folder or file
2. Choose the kind of processing — summarise, classify, extract, and so on, depending on the deployment
3. Start it

Processing takes a while, so **results appear under "📋 Job history"**. You can leave the screen once
it has started.

> **If you see "PHI — AI blocked"**: you are in a protected folder, one holding medical or personal
> information. The block is deliberate. Run the job from a folder outside those paths.

---

## 8. Looking at an earlier state

Choose **📸 Snapshots** from the menu. This is how you recover a file you deleted or overwrote.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-snapshots.png" alt="The snapshot list on a phone" width="320">

- The list is **points in time the storage captured for you**, newest first
- **Browse** opens the contents as they were then, without touching anything current
- **🔒 Lock** makes a snapshot undeletable. **This cannot be undone**, so it asks for confirmation first

> **The "type" and "state" columns are dropped on a narrow screen.** The type is in the name
> (`daily.`, `hourly.`, `weekly.`) and the tabs above the list filter by it.

> **If a message about ONTAP appears**: something is wrong with the storage connection, and it is not
> something you can fix. Pass what it says to your administrator verbatim.

---

## 9. Changing the display

### Language

Tap **🌐** at the top for eight languages.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-language.png" alt="The language switcher on a phone" width="320">

日本語 / English / 한국어 / 简体中文 / 繁體中文 / Français / Deutsch / Español

The change is immediate and is remembered next time.

### Theme (light / dark)

Use ☀️ 🌙 🖥️ at the top.

<img src="../../solutions/amplify-portal/docs/screenshots/portal-mobile-dark.png" alt="The dark theme on a phone" width="320">

| Button | Meaning |
|--------|---------|
| ☀️ | Always light |
| 🌙 | Always dark |
| 🖥️ | **Follow the device setting** |

> **🖥️ is not a "switch to desktop view" button.** It means the portal follows your device's appearance
> setting, including any automatic night-time switch you have configured in iOS or Android.

---

## Differences from the desktop

| Item | On a phone |
|------|-----------|
| Menu | A drawer over the content. **☰** opens and closes it; choosing an item closes it |
| File list "size" and "modified" columns | Dropped (sorting by name still works) |
| Snapshot list "type" and "state" columns | Dropped (the tabs filter by type) |
| Row **⋮** menu | A sheet from the bottom, with the file name at the top |
| File preview | A sheet from the bottom. PDFs read better in landscape |
| Email address in the header | Hidden (sign-out is the icon alone) |
| AI assistant panel | A drawer from the right |
| Buttons above the list | Wrap two per line and stack |

---

## When something goes wrong

**Q: I cannot sign in. Tapping "Sign in" does nothing.**
A: Check that the URL starts with `https://`. Over `http://` the browser withholds features sign-in
needs. If it still fails, check the password and ask your administrator about the account.

**Q: There is no menu.**
A: Tap **☰** at the top left. The menu starts hidden on a phone.

**Q: The list looks empty.**
A: The buttons above it stack vertically, so the file list is below them. Scroll down.

**Q: The last row is hidden behind the bottom of the screen.**
A: The browser's address bar is over it. Scroll down a little and the address bar shrinks.

**Q: I want to see the first-run notice again.**
A: If you closed it with "Don't show again" ticked, it will not return in that browser. Open the portal
in another browser, or in private browsing, and it appears again.

**Q: I tapped a file name and it downloaded instead of previewing.**
A: That type has no preview. Images, PDFs and text open in place; anything else downloads.

**Q: I cannot find the share, rename or delete actions for a file.**
A: Tap **⋮** on its row. A sheet appears at the bottom of the screen.

**Q: A panel says "ONTAP connection required", or that ONTAP refused the credentials.**
A: The storage connection is at fault and you cannot fix it from here. Pass the heading and the
contents of "Error details" to your administrator — the wording tells them which layer to look at.

**Q: The screen is cut off on the right and I cannot reach a button.**
A: That is a defect. Report which screen and which button. At phone widths nothing should scroll
sideways.

**Q: The text is small.**
A: Pinch to zoom. Input fields are at least 16px, so tapping one does not zoom on its own.

### What to include when you report something

If the table above does not cover it, **these four let whoever set the portal up narrow it down almost
immediately.** A single screenshot will often carry all of them.

1. **Which screen** — the item's name in the left menu, e.g. "Snapshots"
2. **The heading and the text on screen, verbatim** — do not paraphrase; the classification of the cause is in that wording
3. **The contents of "Error details"** — tap the ▶ to open it
4. **Your device and browser**, e.g. iPhone / Safari

> **Items 2 and 3 matter most.** The portal classifies the cause and prints the storage's own message
> unchanged. "I got an error" leaves your administrator eliminating six possibilities one at a time.

---

## What has been verified

| Item | Status |
|------|--------|
| Layout and rendering | Checked under Chrome device emulation at 390×844, an iPhone-class width |
| Reachability of controls (inside the viewport, at least 44px) | Measured in the same environment |
| A physical iPhone (Safari on iOS, 402×874 CSS px) | Checked over the range in the table below |
| A physical Android handset | **Not verified** |

### What the iPhone covered

| Section | Status |
|---------|--------|
| [1. Sign in](#1-sign-in) / [The notice on first sign-in](#the-notice-on-first-sign-in) | Checked |
| [2. The layout](#2-the-layout) — the control row, the wrapping of the list | Checked |
| [8. Looking at an earlier state](#8-looking-at-an-earlier-state) — the snapshot list and its filter tabs | Checked |
| [9. Changing the display](#9-changing-the-display) — the eight languages, light and dark | Checked |
| The data-protection lock screen (all three tabs) | Checked |
| Resource management (storage health, listing and creating qtrees) | Checked |
| Image thumbnails in [3. Moving through folders](#3-moving-through-folders) — five shown, the PDF keeping its icon | Checked |
| Menu / folder navigation / row menu / multi-select / upload / AI processing | **Emulation only** |

**The handset found one defect, since fixed.** Qtrees under resource management stayed on
"Loading…" indefinitely: the panel treated "no volume chosen yet" as loading, and the loading state
hid the very control that chooses a volume. It affected the desktop equally. After the fix, creating
and listing a qtree were both confirmed on the handset.

Of the screenshots, the first-run notice and the image thumbnails are from the handset; the rest come from the emulated
environment. A real handset's browser chrome — address bar height and so on — differs. If a step does
not behave as described on real hardware, that difference is worth reporting.

---

## Related documents

- [User guide](portal-user-guide.md) — every feature, desktop-oriented
- [Portal quick reference](portal-quick-reference.md) — terms and where they appear
- [Getting Started](../../solutions/amplify-portal/docs/GETTING-STARTED.en.md) — the administrator's setup path
