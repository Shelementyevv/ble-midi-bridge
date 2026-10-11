<p align="center">
  <img src="app_icon.png" alt="Shelementyev's BLE-MIDI Bridge" width="120">
</p>

<h1 align="center">Shelementyev's BLE-MIDI Bridge</h1>

<p align="center"><b>A reliable Bluetooth &amp; USB MIDI bridge for your digital piano — route it into Synthesia, DAWs, and MIDI files, and (uniquely) into Roblox piano games.</b></p>

Shelementyev's BLE-MIDI Bridge connects your digital piano to your PC and sends what you play wherever you need it: into Synthesia and DAWs, to and from MIDI files, with a live visualizer and recording. And because it speaks Bluetooth, it does something no other tool does — it lets a **Bluetooth piano play in Roblox** piano games like Piano Rooms and Visual Pianos.

**Works with any Bluetooth or USB MIDI keyboard — any size (25 to 88 keys), weighted or non-weighted, with or without pedals.**

![Shelementyev's BLE-MIDI Bridge](screenshot.png)

---

## Features
- **Practice tools** — a Synthesia-style **falling-notes** view (color-coded per hand), a **wait-for-my-notes** mode that pauses at every chord until you play it on your piano (waiting keys light amber and are labeled with the exact note names), a **track / hand filter** for one-hand practice, and a **middle-C marker** on the keyboard.
- **Sheet music out** — the **Sheet music...** button transcribes any loaded file into real notation: a `.musicxml` (opens in the free MuseScore) plus a printable browser preview. It detects keys (including mid-piece changes), triplets and sextuplets, dynamics, and phrase slurs, and writes proper stems, beams, ties, pedal lines, tempo and rehearsal marks, and glissando lines, with held notes kept as a second voice on a grand staff.
- **Sheet music in** — **Load MIDI / Sheet...** also opens MusicXML scores (`.musicxml` / `.mxl`). Two-staff piano scores split into hands, the score's full tempo map is honored, and you can save a `.mid` copy — any sheet becomes playable on your piano or in Roblox.

- **Bluetooth LE pianos** — connect a BLE digital piano directly, no virtual cables or workarounds.
- **USB pianos** — a rock-solid wired option that handles even very fast pieces flawlessly.
- **Two ways into Roblox:**
  - **MidiConnect** — drives the *Piano Rooms* and *Visual Pianos* games with full velocity and sustain, using the MidiConnect protocol (see Credits).
  - **QWERTY output** — plays the many letter-key piano games (the "Virtual Piano" style): keys held until you release the piano key, sharps on Shift, sustain on Space, with out-of-range notes folded in by octaves so every key plays.
- **MIDI file playback** — load a `.mid` and send it to your piano and/or straight into a game, with tempo, loop, and transpose.
- **Send to other software** — pass your piano through to Synthesia or a DAW with a built-in virtual MIDI port (macOS/Linux) or loopMIDI (Windows).
- **Live 88-key visualizer** and one-click **recording** to a `.mid` file.
- **F8 panic hotkey** — instantly release a stuck key or pedal without alt-tabbing out of the game.
- **Test button** — fires a C-major scale into the game so you can confirm your setup before you play.

<p align="center">
  <img src="practice-wait.png" alt="Wait-for-my-notes practice mode" width="820"><br>
  <i>Wait-for-my-notes: playback freezes until you play the labeled amber keys.</i>
</p>

<p align="center">
  <img src="sheet-example.png" alt="Sheet music exported by the app" width="820"><br>
  <i>Notation exported by the app from a MIDI file (demo piece).</i>
</p>

### A note on sheet-music accuracy

The MIDI &harr; sheet conversion is automated engraving, so set your expectations accordingly: treat the output as a **good working draft, not publication-quality typesetting**. Cleanly sequenced MIDIs — the kind piano communities usually share — come out very readable; free-time live recordings quantize roughly. Complex scores are approximated: at most two voices per staff, quintuplet/septuplet runs snap to the nearest supported grid, spelling follows one key per key-signature region, and editorial detail like fingerings or expression text simply isn't present in MIDI data. Importing MusicXML works best with standard two-staff piano scores. For a polished final copy, open the exported `.musicxml` in the free [MuseScore](https://musescore.org) and tidy it there — the notes, rhythms, and structure will already be in place.

## Requirements

- **Windows** for the Roblox feature (the keystroke output uses `pydirectinput`, which is Windows-only). The MIDI-port, file-playback, visualizer, and recording features also run on macOS/Linux.
- **Any** Bluetooth-MIDI or USB-MIDI keyboard — any size (25 to 88 keys), weighted or non-weighted, with or without pedals. It only needs standard MIDI over Bluetooth or USB, which is virtually every digital piano and keyboard.
- For Bluetooth, a PC with Bluetooth LE.

## Install

### Option A — download the app (easiest)

Grab the latest `Shelementyevs-BLE-MIDI-Bridge.exe` from the [Releases page](https://github.com/Shelementyevv/ble-midi-bridge/releases) and double-click it. It's a single file — no installer, nothing to set up.

### Option B — run from source

```bash
pip install -r requirements.txt
python ble_midi_bridge_gui.py
```

To build your own standalone `.exe`, run `build.bat` (it installs the build tools and produces `dist/Shelementyevs-BLE-MIDI-Bridge.exe`).

Run the keyboard-output regression tests with `python -m unittest discover -s tests -v`.
These tests use mocked key events and do not require a connected piano or Roblox.

## A note on antivirus warnings

Windows Defender or another scanner may flag the `.exe` as suspicious, or block the download. **This is a false positive.** Apps packaged from Python with PyInstaller bundle a whole Python runtime into one executable, and that self-unpacking behavior looks like the software "packers" malware uses — so heuristic and machine-learning scanners flag it by pattern, not because anything is actually wrong.

On [VirusTotal](https://www.virustotal.com/gui/file/c444839534cf86b831623f7ba0b08ee68fdc3d9253571bfad54c54ebd2df0f2e) only a handful of heuristic/ML engines flag it, while the major signature-based scanners — BitDefender, ESET, Avast, AVG, Avira, CrowdStrike, and others — all report it clean. The full source is in this repository and the build is reproducible with `build.bat`, so you can inspect or build it yourself.

- **If the download is blocked:** in your browser's downloads, choose *Keep* (Chrome/Edge), or download it again and allow it.
- **If Defender quarantines it:** open **Windows Security -> Virus & threat protection -> Protection history**, select the item, and choose **Allow**.
- **If you'd rather not run the prebuilt file:** follow **Option B (run from source)** above instead.

## Quick start

1. **Connect your piano.** Set *Source* to Bluetooth LE and Scan, or choose your USB port, then click **Connect**.
2. **Turn on Roblox output.** Tick **Send to Roblox** and choose a **Type**:
   - **MidiConnect** if you're playing *Piano Rooms* or *Visual Pianos* (open the game and click its in-game MidiConnect button first).
   - **QWERTY output** for any other piano game you'd normally play with letter keys.
3. **Open your game, keep its window focused, and play.** Press **Test** first if you want to confirm the keys are landing.

You do **not** need to pick a MIDI output for Roblox — that option is only for sending your piano to other PC software.

Full setup notes, including connecting over Bluetooth vs USB and using a virtual MIDI port, are in the in-app **Help / Setup** window.

## Choosing the Roblox type

| | MidiConnect | QWERTY output |
|---|---|---|
| **For** | *Piano Rooms* &amp; *Visual Pianos* | Letter-key piano games (Virtual Piano style) |
| **Velocity (dynamics)** | Yes | Usually no |
| **Sustain pedal** | Yes | Yes (held as the Space bar) |
| **Setup** | Click the in-game MidiConnect button | Just focus the game |

## Troubleshooting

- **Nothing happens in Roblox** — the game window must be focused, *Send to Roblox* must be on, and the Type must match the game. Press **Test**.
- **A "pydirectinput" message on first use** — run `pip install pydirectinput` (already included in the `.exe` build).
- **MidiConnect type does nothing** — make sure you clicked the MidiConnect button inside *Piano Rooms* or *Visual Pianos* so the game is listening.
- **QWERTY output plays wrong notes** — that game may use a different layout, or a non-US keyboard layout is interfering; set your system keyboard to US English while playing.
- **Fast songs bunch up over Bluetooth** — this is a hardware limit of the piano's Bluetooth, not the app. Use USB for those pieces.

## Credits

The **MidiConnect** option speaks to *Piano Rooms* and *Visual Pianos* using the **MidiConnect** protocol created by **LordHenryVonHenry**. Huge thanks for that work — it's what makes that connection possible, and this project builds directly on top of it.

→ [github.com/LordHenryVonHenry/RobloxMidiConnect](https://github.com/LordHenryVonHenry/RobloxMidiConnect)

## License

Shelementyev's BLE-MIDI Bridge is free software, licensed under the **GNU General Public License v3.0** (GPLv3). You're free to use, study, share, and modify it; if you distribute a modified version, it must also be released under the GPLv3. See the [`LICENSE`](LICENSE) file for the full text.

The **MidiConnect** protocol it speaks is the work of **LordHenryVonHenry** (see Credits). This project only links and credits that work and contains none of its source code, so the GPLv3 here covers this project's own code.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Roblox Corporation. Roblox is a trademark of Roblox Corporation. Use it in accordance with the terms of service of any game you connect to.
