<p align="center">
  <img src="Resources/icon_squircle.png" width="150" alt="Blablabla">
</p>

<h1 align="center">Blablabla</h1>

<h3 align="center">Stop typing. Start talking.</h3>

<p align="center">
  The open-source voice-to-text app for macOS that types where your cursor is.<br>
  Hold a key. Speak. Release. Done.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS%2014%2B-black?style=flat-square" alt="macOS 14+">
  <img src="https://img.shields.io/badge/license-MIT%20%2B%20Commons%20Clause-green?style=flat-square" alt="MIT + Commons Clause">
  <img src="https://img.shields.io/badge/powered%20by-AssemblyAI-blue?style=flat-square" alt="AssemblyAI">
  <img src="https://img.shields.io/badge/built%20with-Swift-orange?style=flat-square" alt="Swift">
</p>

---

<br>

<p align="center">
  <strong>You think 4x faster than you type.</strong><br>
  Why are you still typing?
</p>

<br>

### The problem

Every day you type the same things: Slack replies, ChatGPT prompts, emails, code comments, Jira tickets, meeting notes. You know what you want to say — your fingers just can't keep up.

Voice-to-text apps exist, but they all suck. They open a separate window. They make you copy-paste. They don't work in your terminal. They cost $20/month.

### The solution

**Blablabla types where your cursor is.** No windows. No copy-paste. No subscriptions.

Hold a key. Speak. Release. Your words appear exactly where you were typing — Slack, VS Code, ChatGPT, Terminal, Notion, anywhere.

That's it. That's the app.

---

<br>

## Vibe coding at the speed of thought

You're building with Cursor, Claude Code, Copilot, ChatGPT — and your bottleneck is **typing prompts**.

You know exactly what you want the AI to do. You can explain it in 5 seconds. But typing it out takes 30. So you write shorter prompts. Lazier prompts. Worse prompts.

**With Blablabla, you just talk.**

Hold a key → describe what you want → release → your prompt is in the text box. Hit Enter. Next prompt. Hold key. Talk. Release. Enter. Again. Again. Again.

You'll send more prompts in 10 minutes than you used to send in an hour. Your AI gets better instructions because you're not too lazy to explain context. You iterate faster. You vibe harder.

<br>

---

<br>

## Features that matter

<table>
<tr>
<td width="50%">

**Push-to-talk**<br>
Hold your shortcut, speak, release. Transcript appears at your cursor instantly. Muscle memory in 5 minutes.

**Hands-free mode**<br>
Double-tap to lock. Talk as long as you need — long emails, detailed prompts, brain dumps. Tap again when done.

**Fn key trigger**<br>
One key. No modifiers. Enable Fn as your push-to-talk button for the fastest possible workflow.

**Works in any app**<br>
If it has a text cursor, Blablabla can type into it. Slack, VS Code, Terminal, Chrome, Notion, Mail, Pages — everything.

</td>
<td width="50%">

**20+ languages, zero config**<br>
Speak English, Spanish, French, German, Portuguese, Italian... the model auto-detects. Switch languages mid-sentence if you want.

**Floating indicator**<br>
A tiny waveform pill above your dock. Shows recording state, audio levels, and locked mode. Follows your active monitor.

**Transcript history**<br>
Searchable, paginated history of everything you've dictated. Copy any past transcript with one click.

**100% private**<br>
Your API key. Your audio. Direct to AssemblyAI. No middleman server. No telemetry. No analytics. Fully open source.

</td>
</tr>
</table>

<br>

---

<br>

## How much does it cost?

**$0.**

Blablabla is free and open source. You bring your own AssemblyAI API key:

- **$50 free credit** on signup (that's ~135 hours of streaming)
- **10 hours/month free** after that
- Pay-as-you-go: $0.37/hour if you go over

For most people, the free tier is more than enough. You'd need to dictate **20 minutes every single day** to hit the limit.

<p align="center">
  <a href="https://www.assemblyai.com/dashboard/signup"><strong>Get your free API key →</strong></a>
</p>

<br>

---

<br>

## Download

Grab the latest signed & notarized build — no Xcode needed:

<p align="center">
  <a href="https://github.com/arturogj92/blablabla/releases/latest"><strong>Download latest release →</strong></a>
</p>

Unzip, drag to Applications, and you're good to go.

<br>

---

<br>

## Build from source

### Windows 11 (local preview)

A separate native Windows client is available in [`Windows/`](Windows/README.md).
Run `Windows/run.cmd` with Python 3.11+, or open `Windows/dist/Blablabla.exe` after
building it with `Windows/build.ps1`. It supports microphone dictation, a global
**Ctrl + Alt + Space** toggle, text insertion and local history. Bring your own
AssemblyAI API key. See the Windows guide for setup and current limitations.

### macOS

```bash
# 1. Install XcodeGen if you don't have it
brew install xcodegen

# 2. Clone and build
git clone https://github.com/arturogj92/blablabla.git
cd blablabla
xcodegen generate

# 3. Build and run
xcodebuild -project Blablabla.xcodeproj -scheme Blablabla build
open ~/Library/Developer/Xcode/DerivedData/Blablabla-*/Build/Products/Debug/Blablabla.app
```

Or just open `Blablabla.xcodeproj` in Xcode and hit **Cmd+R**.

### First launch

1. Paste your AssemblyAI API key
2. Grant Microphone, Accessibility, and Input Monitoring permissions
3. Restart the app
4. Hold your shortcut and talk

Default shortcut: **Option + Shift + §** (customizable in Settings)

<br>

---

<br>

## Controls

| Action | Result |
|--------|--------|
| **Hold shortcut** | Push-to-talk — records while held |
| **Double-tap shortcut** | Locks recording hands-free |
| **Tap while locked** | Stops and transcribes |
| **Hold Fn** *(optional)* | Push-to-talk with one key |
| **Click dock pill** | Toggle recording |
| **Right-click dock pill** | Recent transcripts menu |

<br>

---

<br>

## Built with

- **Swift** + **AppKit** + **SwiftUI** — 100% native macOS, no Electron, no web views
- **AssemblyAI Universal Streaming v3** — real-time, multilingual speech-to-text
- **CGEvent taps** — true global shortcuts that work in any app
- **Accessibility APIs** — direct text insertion without clipboard pollution
- **AudioToolbox** — native system sounds that don't interrupt audio capture
- **XcodeGen** — clean, reproducible project generation

<br>

---

<br>

## Contribute

Blablabla is open source and contributions are welcome. Some ideas we'd love help with:

| Feature | Description |
|---------|-------------|
| **AI post-processing** | Clean up grammar, remove filler words, or reformat with an LLM before pasting |
| **Voice commands** | "Delete that", "new paragraph", "undo last sentence" |
| **Output templates** | Format as bullet points, email, code comment, meeting notes |
| **Whisper offline mode** | Local transcription fallback when there's no internet |
| **Auto-launch at login** | Start with macOS automatically |

<br>

---

<br>

<p align="center">
  <strong>Stop typing. Start talking.</strong><br><br>
  <a href="https://github.com/arturogj92/blablabla"><img src="https://img.shields.io/github/stars/arturogj92/blablabla?style=social" alt="GitHub stars"></a>
</p>

<br>

## License

MIT + Commons Clause — free to use, modify, and distribute. Commercial selling restricted to the original author. See [LICENSE](LICENSE).
