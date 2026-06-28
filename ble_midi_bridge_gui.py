#!/usr/bin/env python3
#
# Shelementyev's BLE-MIDI Bridge
# Copyright (C) 2026  Shelementyev
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""
Shelementyev's BLE-MIDI Bridge - GUI

A desktop app that connects a digital piano to the PC and bridges its MIDI,
either over Bluetooth LE or a USB/DIN MIDI cable. It forwards the piano to a
virtual MIDI output (LoopBe1, loopMIDI, ...) and/or Roblox piano games (Piano
Rooms via its MIDI mod, or any Virtual Piano style keyboard game), plays
MIDI files back to the piano, records what you play to a .mid file, and shows a
live 88-key visualizer with transpose, velocity scaling, pedals, and a panic.

Run from source:
    pip install bleak python-rtmidi mido pydirectinput pynput
    python ble_midi_bridge_gui.py

Build a standalone .exe (Windows): run build.bat (see that file).
"""

import asyncio
import json
import queue
import sys
import threading
import webbrowser
import time
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# BLE-MIDI identifiers and parser (self-contained so the .exe is one file)
# ---------------------------------------------------------------------------
MIDI_SERVICE_UUID = "03b80e5a-ede8-4b33-a751-6ce34ec4c700"
MIDI_CHAR_UUID = "7772e5db-3868-4112-a1a9-f2669d106bf3"

PIANO_LOW, PIANO_HIGH = 21, 108  # A0 .. C8
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CONFIG_PATH = Path.home() / ".ble_midi_bridge_gui.json"
APP_VERSION = "1.0"

# The app can publish its own MIDI output port so other software (Synthesia, a
# DAW) can receive the piano without installing loopMIDI. rtmidi supports this
# on macOS (CoreMIDI) and Linux (ALSA), but NOT on Windows: WinMM has no API to
# create an app-visible virtual port - that's exactly what loopMIDI's driver is.
VIRTUAL_PORT_NAME = "BLE-MIDI Bridge"
VIRTUAL_OUT_SUPPORTED = not sys.platform.startswith("win")
BUILTIN_PORT_LABEL = "Built-in port (this app - no loopMIDI needed)"


def note_name(num: int) -> str:
    return f"{_NOTE_NAMES[num % 12]}{num // 12 - 1}"


def _channel_data_bytes(status: int) -> int:
    high = status & 0xF0
    if high in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
        return 2
    if high in (0xC0, 0xD0):
        return 1
    return 0


def _system_common_data_bytes(status: int) -> int:
    if status == 0xF1:
        return 1
    if status == 0xF2:
        return 2
    if status == 0xF3:
        return 1
    return 0


class BLEMIDIParser:
    """Stateful BLE-MIDI payload parser. parse(packet) -> list[list[int]]."""

    def __init__(self):
        self.running_status = 0
        self.in_sysex = False
        self.sysex_buffer = []

    def parse(self, data: bytes):
        messages = []
        n = len(data)
        if n < 1:
            return messages
        pos = 1
        while pos < n:
            byte = data[pos]
            if self.in_sysex:
                if byte & 0x80:
                    pos += 1
                    if pos >= n:
                        break
                    nxt = data[pos]
                    if nxt == 0xF7:
                        self.sysex_buffer.append(0xF7)
                        messages.append(self.sysex_buffer)
                        self.sysex_buffer = []
                        self.in_sysex = False
                        pos += 1
                    elif 0xF8 <= nxt <= 0xFF:
                        messages.append([nxt])
                        pos += 1
                    else:
                        self.in_sysex = False
                        self.sysex_buffer = []
                else:
                    self.sysex_buffer.append(byte)
                    pos += 1
                continue
            if not (byte & 0x80):
                pos += 1
                continue
            pos += 1
            if pos >= n:
                break
            b = data[pos]
            if b & 0x80:
                status = b
                pos += 1
                if status == 0xF0:
                    self.in_sysex = True
                    self.sysex_buffer = [0xF0]
                    self.running_status = 0
                elif 0xF8 <= status <= 0xFF:
                    messages.append([status])
                elif 0xF1 <= status <= 0xF7:
                    self.running_status = 0
                    k = _system_common_data_bytes(status)
                    messages.append([status] + list(data[pos:pos + k]))
                    pos += k
                else:
                    self.running_status = status
                    k = _channel_data_bytes(status)
                    messages.append([status] + list(data[pos:pos + k]))
                    pos += k
            else:
                if self.running_status:
                    k = _channel_data_bytes(self.running_status)
                    messages.append([self.running_status] + list(data[pos:pos + k]))
                    pos += k
                else:
                    pos += 1
        return messages


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------------------
# Roblox "Piano Rooms" MidiConnect protocol (numpad keystroke output)
# ---------------------------------------------------------------------------
# Each event = the numpad '*' (multiply) delimiter, then four base-12 digits:
# [note//12, note%12, value//12, value%12]. Digits 0-9 are numpad 0-9, 10 is
# numpad '-', 11 is numpad '+'. Sustain (CC64) is sent as virtual note 143.
_MC_DIGITS = ["num0", "numpad1", "numpad2", "numpad3", "numpad4", "numpad5",
              "numpad6", "numpad7", "numpad8", "numpad9", "subtract", "add"]

# DirectInput scan codes for the numpad digit keys (others are pydirectinput
# built-ins: multiply=0x37, subtract=0x4A, add=0x4E).
_MC_SCANCODES = {"num0": 0x52, "numpad1": 0x4F, "numpad2": 0x50, "numpad3": 0x51,
                 "numpad4": 0x4B, "numpad5": 0x4C, "numpad6": 0x4D, "numpad7": 0x47,
                 "numpad8": 0x48, "numpad9": 0x49}


def midiconnect_keys(msg):
    """Return the numpad key sequence for a MIDI message, or None to ignore it."""
    status = msg[0]
    high = status & 0xF0
    if high == 0x90 and len(msg) >= 3 and msg[2] > 0:
        note, vel = msg[1], msg[2]
        digits = [note // 12, note % 12, vel // 12, vel % 12]
    elif high == 0x80 or (high == 0x90 and len(msg) >= 3 and msg[2] == 0):
        note = msg[1]
        digits = [note // 12, note % 12, 0, 0]
    elif high == 0xB0 and len(msg) >= 3 and msg[1] == 64:  # sustain pedal
        ctrl, value = 143, msg[2]
        digits = [ctrl // 12, ctrl % 12, value // 12, value % 12]
    else:
        return None
    return ["multiply"] + [_MC_DIGITS[d] for d in digits]


# ---------------------------------------------------------------------------
# "Virtual Piano" keyboard layout (virtualpiano.net standard, used by most
# Roblox/online pianos that map notes to letter keys).
# ---------------------------------------------------------------------------
# The 36 white keys, low->high, are these characters; black keys are Shift +
# the white key just below them (C# = Shift+C's key, etc). The first character
# maps to the base note (C2 by default), giving the canonical C2..C7 range with
# middle C (C4) on the "t" key. Users can override the string / base note for
# other games.
VIRTUAL_PIANO_KEYS = "1234567890qwertyuiopasdfghjklzxcvbnm"
VP_BASE_NOTE = 36  # C2

# Roblox output modes shown in the UI dropdown (index 0 is the default).
ROBLOX_MODES = ["MidiConnect", "QWERTY output"]

# DirectInput (Set-1) scan codes for every key the keyboard layout can use, so
# output doesn't depend on pydirectinput's built-in name table.
_QWERTY_SCANCODES = {
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07,
    "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15,
    "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23,
    "j": 0x24, "k": 0x25, "l": 0x26,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
    "shiftleft": 0x2A, "space": 0x39,
}

_WHITE_PCS = frozenset((0, 2, 4, 5, 7, 9, 11))


def build_keyboard_map(white_keys=VIRTUAL_PIANO_KEYS, base_note=VP_BASE_NOTE):
    """Map MIDI note number -> (key_char, shift_bool) for a keyboard piano.

    White keys consume the characters of `white_keys` in order, starting at
    `base_note` (which should be a C). Each black key reuses the character of
    the white key just below it, with shift. Notes outside the covered range
    have no entry (they're simply not played).
    """
    mapping = {}
    ptr = 0
    last_white = None
    note = base_note
    while ptr < len(white_keys):
        if (note % 12) in _WHITE_PCS:
            ch = white_keys[ptr]
            mapping[note] = (ch, False)
            last_white = ch
            ptr += 1
        elif last_white is not None:
            mapping[note] = (last_white, True)
        note += 1
    return mapping


class RobloxKeySender:
    """
    Sends MIDI notes/sustain into a Roblox piano on a private worker thread.
    Two output modes:
      - "midiconnect": Piano Rooms numpad protocol (note + velocity + sustain).
      - "keyboard":    Virtual Piano style, where each note taps a letter/number
                       key (Shift for sharps) and the sustain pedal holds Space.
    pydirectinput is imported lazily (Windows-only) the first time it's needed.
    """

    def __init__(self, log):
        self._log = log
        self.enabled = False
        self.mode = "midiconnect"     # or "keyboard"
        self.kbd_map = {}             # note -> (key_char, shift) for keyboard mode
        self._kbd_lo = 0
        self._kbd_hi = 127
        self._q = queue.Queue()
        self._pdi = None
        self._failed = False
        self._last_sustain = None
        self._held = set()            # notes held down (midiconnect release tracking)
        self._space_down = False      # keyboard-mode sustain state
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- public API (called from other threads) -----------------------------
    def send(self, msg, force=False):
        if (not self.enabled and not force) or self._failed:
            return
        high = msg[0] & 0xF0
        if high == 0xB0:
            if len(msg) < 3 or msg[1] != 64:
                return  # only the sustain pedal is meaningful
            if msg[2] == self._last_sustain:
                return  # collapse the piano's repeated pedal messages
            self._last_sustain = msg[2]
        self._q.put(bytes(msg))

    def release_all(self):
        """Refocus Roblox and lift everything this sender currently holds."""
        if self._failed:
            return
        self._q.put(("release_all",))

    def focus(self):
        self._q.put(("focus",))

    def set_keyboard_map(self, mapping):
        self.kbd_map = mapping
        if mapping:
            self._kbd_lo = min(mapping)
            self._kbd_hi = max(mapping)

    # -- worker -------------------------------------------------------------
    def _load(self):
        import pydirectinput as pdi
        pdi.PAUSE = 0
        pdi.FAILSAFE = False
        pdi.KEYBOARD_MAPPING.update(_MC_SCANCODES)
        pdi.KEYBOARD_MAPPING.update(_QWERTY_SCANCODES)
        return pdi

    def _ensure(self):
        if self._pdi is not None:
            return True
        if self._failed:
            return False
        try:
            self._pdi = self._load()
            return True
        except Exception as e:
            self._failed = True
            self._log("Roblox output needs pydirectinput "
                      f"(pip install pydirectinput): {e}")
            return False

    def _focus_roblox(self):
        """Best-effort: bring the Roblox window to the foreground."""
        try:
            import ctypes
            u = ctypes.windll.user32
            hwnd = u.FindWindowW(None, "Roblox")
            if hwnd:
                u.SetForegroundWindow(hwnd)
                time.sleep(0.05)
        except Exception:
            pass

    # --- midiconnect (Piano Rooms) helpers ---
    def _press_keys(self, msg):
        keys = midiconnect_keys(msg)
        if not keys:
            return
        for k in keys:
            try:
                self._pdi.press(k)
            except Exception:
                pass

    # --- keyboard (Virtual Piano) helpers ---
    def _key_tap(self, key, shift):
        pdi = self._pdi
        try:
            if shift:
                pdi.keyDown("shiftleft")
                pdi.press(key)
                pdi.keyUp("shiftleft")
            else:
                pdi.press(key)
        except Exception:
            pass

    def _set_space(self, down):
        try:
            if down and not self._space_down:
                self._pdi.keyDown("space")
                self._space_down = True
            elif not down and self._space_down:
                self._pdi.keyUp("space")
                self._space_down = False
        except Exception:
            pass

    def _kbd_message(self, msg):
        high = msg[0] & 0xF0
        if high == 0x90 and len(msg) >= 3 and msg[2] > 0:
            note = msg[1]
            # fold notes outside the layout's range in by octaves, so every key
            # on an 88-key piano still plays something in a 61-key game
            while note < self._kbd_lo:
                note += 12
            while note > self._kbd_hi:
                note -= 12
            km = self.kbd_map.get(note)
            if km:
                self._key_tap(km[0], km[1])
        elif high == 0xB0 and len(msg) >= 3 and msg[1] == 64:
            self._set_space(msg[2] >= 64)
        # note-offs are ignored: Virtual Piano notes are triggered on key-down

    def _run(self):
        while True:
            item = self._q.get()
            if item is None:
                continue
            if not self._ensure():
                continue
            if isinstance(item, tuple):
                if item[0] == "focus":
                    self._focus_roblox()
                elif item[0] == "release_all":
                    self._focus_roblox()
                    if self.mode == "keyboard":
                        self._set_space(False)
                        try:
                            self._pdi.keyUp("shiftleft")
                        except Exception:
                            pass
                    else:
                        for note in sorted(self._held):
                            self._press_keys(bytes([0x80, note, 0]))
                        self._press_keys(bytes([0xB0, 64, 0]))  # sustain off
                    self._held.clear()
                    self._last_sustain = None
                continue
            msg = item
            if self.mode == "keyboard":
                self._kbd_message(msg)
                continue
            high = msg[0] & 0xF0
            if high == 0x90 and len(msg) >= 3 and msg[2] > 0:
                self._held.add(msg[1])
            elif high == 0x80 or (high == 0x90 and len(msg) >= 3 and msg[2] == 0):
                self._held.discard(msg[1])
            self._press_keys(msg)


def piano_layout(width, height):
    """
    Return drawing rectangles for an 88-key keyboard.
    Yields dicts: {note, x, y, w, h, black}. White keys first, then black.
    """
    white_notes = [n for n in range(PIANO_LOW, PIANO_HIGH + 1)
                   if (n % 12) in (0, 2, 4, 5, 7, 9, 11)]
    nw = len(white_notes)  # 52
    ww = width / nw
    bw = ww * 0.62
    bh = height * 0.62

    white_x = {}
    rects = []
    for i, n in enumerate(white_notes):
        x = i * ww
        white_x[n] = x
        rects.append({"note": n, "x": x, "y": 0, "w": ww, "h": height, "black": False})

    # Black keys sit between the white key to their left and the next white.
    for n in range(PIANO_LOW, PIANO_HIGH + 1):
        if (n % 12) in (1, 3, 6, 8, 10):
            left_white = n - 1  # the white key just below a black is always n-1
            if left_white in white_x:
                x = white_x[left_white] + ww - bw / 2
                rects.append({"note": n, "x": x, "y": 0, "w": bw, "h": bh, "black": True})
    return rects


# ---------------------------------------------------------------------------
# Bridge controller: owns the asyncio loop, BLE connection, and MIDI output.
# Communicates with the GUI through a thread-safe queue.
# ---------------------------------------------------------------------------
class BridgeController:
    def __init__(self, event_queue: "queue.Queue"):
        self.q = event_queue
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self.roblox = RobloxKeySender(lambda text: self.emit("log", text))

        self.midiout = None
        self.parser = BLEMIDIParser()
        self.active_map = {}     # (channel, in_note) -> out_note actually sent
        self._last_cc = {}       # (channel, controller) -> last value sent (de-dup)
        self._send_err = False
        self._stop = None        # asyncio.Event, created on connect
        self._task = None
        self._active = False     # a connection attempt/session is live
        self.user_disconnect = False

        # Input transport: "ble" (Bluetooth) or "midi" (USB/DIN cable).
        self.source_mode = "ble"
        self.midiin = None       # rtmidi.MidiIn when wired

        # Set while connected so the playback feature can write to the piano.
        self._client = None
        self._char = None
        self._mtu = 20            # negotiated ATT MTU (payload = mtu - 3)
        self._wwr_max = 20        # max write-without-response payload (<=20 for BLE-MIDI)
        self._last_ble_write = 0.0
        self._write_err = False   # latch so a BLE write error is logged only once
        self._ble_gap = 0.002     # min seconds between consecutive BLE writes
        # BLE-MIDI is sent in connection-interval-sized batches with per-event
        # timestamps; the receiver reconstructs exact timing. The "lookahead" is
        # the buffer the piano gets to schedule against - bigger absorbs Bluetooth
        # hiccups on fast pieces (if the piano honors timestamps). Both tunable.
        self._ble_interval = 0.015   # transmit cadence (~connection interval)
        self._ble_lookahead = 0.030  # how far ahead of play time events are sent
        self._tx_last_ms = 0.0       # monotonic BLE-MIDI timestamp high-water (ms)
        self._running_status = True  # pack more notes per packet (fewer BLE writes)

        # Playback-to-piano uses the same transport as the input (source_mode).
        self.piano_out = None     # rtmidi.MidiOut to the piano, when wired

        # MIDI recording (capture what is played on the piano).
        self._rec = False
        self._rec_events = []     # [(seconds_from_start, message_bytes)]
        self._rec_t0 = 0.0

        # MIDI-file playback (PC -> piano).
        self._events = []        # [(delay_seconds, message_bytes_or_None)]
        self._play_future = None
        self._play_stop = False
        self._play_pause = False
        self.play_tempo = 1.0     # 0.5 .. 2.0
        self.loop_play = False    # repeat the file when it finishes
        self.remap_ch1 = True     # send everything on channel 1 (piano voice)
        self.play_to_output = True  # also mirror playback to the virtual port
        self.piano_voice = None   # program number to force on the piano, or None

        # Live, GUI-adjustable settings (plain attributes; int/float reads are atomic).
        self.transpose = 0
        self.vel_scale = 1.0
        self.auto_reconnect = True
        self.clean_output = True  # drop sensing/clock/SysEx, collapse duplicate CCs

    # -- loop plumbing ------------------------------------------------------
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def emit(self, *event):
        self.q.put(event)

    # -- scanning -----------------------------------------------------------
    def scan(self, timeout=6.0):
        self._submit(self._scan(timeout))

    async def _scan(self, timeout):
        try:
            from bleak import BleakScanner
            self.emit("status", "Scanning...", "busy")
            devices = await BleakScanner.discover(timeout=timeout)
            found = sorted(
                ((d.name, d.address) for d in devices if d.name),
                key=lambda t: t[0].lower(),
            )
            self.emit("devices", found)
            self.emit("status", "Scan complete", "idle")
        except Exception as e:
            self.emit("log", f"Scan error: {e}")
            self.emit("status", "Scan failed", "error")

    # -- MIDI output --------------------------------------------------------
    def list_output_ports(self):
        import rtmidi
        return rtmidi.MidiOut().get_ports()

    def list_input_ports(self):
        import rtmidi
        return rtmidi.MidiIn().get_ports()

    def _open_output(self, port_index):
        import rtmidi
        self.midiout = rtmidi.MidiOut()
        self.midiout.open_port(port_index)

    def _open_virtual_output(self):
        """Create our own MIDI port other apps can connect to (macOS/Linux)."""
        import rtmidi
        self.midiout = rtmidi.MidiOut()
        self.midiout.open_virtual_port(VIRTUAL_PORT_NAME)

    def _open_midi_input(self, port_index):
        import rtmidi
        self.midiin = rtmidi.MidiIn()
        self.midiin.open_port(port_index)
        # Drop transport noise at the source; clean_output handles the rest.
        try:
            self.midiin.ignore_types(sysex=True, timing=True, active_sense=True)
        except Exception:
            pass
        self.midiin.set_callback(self._on_midi_in)

    def _open_piano_out_matching(self, input_name):
        """When wired, the piano shows up as both a MIDI in and a MIDI out with
        the same name. Open the matching output so file playback can reach it."""
        import rtmidi
        outs = rtmidi.MidiOut().get_ports()
        base = (input_name or "").split(":")[0].strip().lower()
        idx = None
        for i, name in enumerate(outs):
            if base and base in name.lower():
                idx = i
                break
        if idx is None:
            self.piano_out = None
            self.emit("log", "No matching MIDI-out for the piano; "
                             "file playback over USB is disabled.")
            return
        self.piano_out = rtmidi.MidiOut()
        self.piano_out.open_port(idx)
        self.emit("log", f"Playback will use MIDI-out: {outs[idx]}")

    def _on_midi_in(self, event, _data=None):
        msg, _dt = event
        if msg:
            self._forward(bytes(msg))

    # -- connection ---------------------------------------------------------
    def connect(self, source_mode, source_index, address, out_port_index):
        """source_mode: 'ble' or 'midi'. For 'ble', address is used. For 'midi',
        source_index selects the input port. out_port_index is the (optional)
        virtual port to forward to (LoopBe/loopMIDI)."""
        if self._active:
            return
        self.user_disconnect = False
        self.source_mode = source_mode
        self.midiout = None
        if out_port_index == "virtual":
            try:
                self._open_virtual_output()
                self.emit("log", f"Created built-in MIDI port '{VIRTUAL_PORT_NAME}'. "
                                 "Pick it as the input in Synthesia or your DAW.")
            except Exception as e:
                self.emit("log", f"Could not create a built-in MIDI port: {e}")
                self.emit("status", "MIDI port error", "error")
                return
        elif isinstance(out_port_index, int) and out_port_index >= 0:
            try:
                self._open_output(out_port_index)
            except Exception as e:
                self.emit("log", f"Could not open MIDI port: {e}")
                self.emit("status", "MIDI port error", "error")
                return

        self._send_err = False
        self._last_cc = {}
        self._play_stop = False

        if source_mode == "midi":
            self._connect_wired(source_index)
            if not self._active and self.midiout is not None:
                try:
                    self.midiout.close_port()
                except Exception:
                    pass
                self.midiout = None
        else:
            self._active = True
            self._stop = asyncio.Event()
            self.parser = BLEMIDIParser()
            self._task = self._submit(self._bridge(address))

    def _connect_wired(self, source_index):
        names = []
        try:
            names = self.list_input_ports()
        except Exception as e:
            self.emit("log", f"Could not list MIDI inputs: {e}")
            self.emit("status", "MIDI input error", "error")
            return
        if not (0 <= source_index < len(names)):
            self.emit("status", "MIDI input error", "error")
            self.emit("log", "Selected MIDI input is no longer available.")
            return
        try:
            self._open_midi_input(source_index)
        except Exception as e:
            self.emit("log", f"Could not open MIDI input: {e}")
            self.emit("status", "MIDI input error", "error")
            return
        try:
            self._open_piano_out_matching(names[source_index])
        except Exception as e:
            self.piano_out = None
            self.emit("log", f"Could not open piano MIDI-out: {e}")
        self._active = True
        self.emit("status", "Connected (USB)", "ok")
        self.emit("log", f"Connected to MIDI input: {names[source_index]}")

    def disconnect(self):
        self.user_disconnect = True
        if self.source_mode == "midi":
            self.loop.call_soon_threadsafe(self._close_wired)
        elif self._stop:
            self.loop.call_soon_threadsafe(self._stop.set)

    def _close_wired(self):
        self._play_stop = True
        self._panic()
        for port in (self.midiin, self.piano_out):
            try:
                if port is not None:
                    port.close_port()
            except Exception:
                pass
        self.midiin = None
        self.piano_out = None
        self._active = False
        self.emit("status", "Disconnected", "idle")
        self.emit("clear")
        self.emit("log", "Disconnected")

    def _piano_ready(self):
        """True when there is a live transport to send playback to the piano."""
        if self.source_mode == "midi":
            return self.piano_out is not None
        return self._client is not None

    async def _bridge(self, address):
        from bleak import BleakClient
        while not self._stop.is_set():
            try:
                self.emit("status", "Connecting...", "scan")
                async with BleakClient(address) as client:
                    char = MIDI_CHAR_UUID
                    try:
                        await client.start_notify(char, self._on_ble_data)
                    except Exception:
                        char = None
                        for service in client.services:
                            if service.uuid.lower() == MIDI_SERVICE_UUID:
                                for c in service.characteristics:
                                    if "notify" in c.properties:
                                        char = c.uuid
                                        break
                        if char is None:
                            raise RuntimeError("No BLE-MIDI notify characteristic.")
                        await client.start_notify(char, self._on_ble_data)

                    self._client = client
                    self._char = char
                    try:
                        self._mtu = max(20, int(client.mtu_size))
                    except Exception:
                        self._mtu = 20
                    # Proper payload bound for write-without-response (capped at 20:
                    # classic BLE-MIDI devices choke on larger packets).
                    self._wwr_max = 20
                    try:
                        gc = client.services.get_characteristic(char)
                        if gc is not None and gc.max_write_without_response_size:
                            self._wwr_max = max(5, int(gc.max_write_without_response_size))
                    except Exception:
                        pass
                    self.emit("status", "Connected", "ok")
                    self.emit("log", f"Connected to {address}")
                    self.emit("log", f"BLE negotiated: MTU {self._mtu}, "
                                     f"max write {self._wwr_max}B/packet")
                    while client.is_connected and not self._stop.is_set():
                        await asyncio.sleep(0.3)
                    try:
                        await client.stop_notify(char)
                    except Exception:
                        pass
            except Exception as e:
                self.emit("log", f"Connection error: {e}")
            finally:
                self._client = None
                self._char = None
                self._play_stop = True  # any playback needs a live connection

            if self.user_disconnect or self._stop.is_set():
                break
            if not self.auto_reconnect:
                break
            self.emit("status", "Reconnecting...", "scan")
            await asyncio.sleep(2)

        self._panic()  # clear anything stuck on the way out
        self._active = False
        self.emit("status", "Disconnected", "idle")
        self.emit("clear")
        self.emit("log", "Disconnected")

    # -- incoming data ------------------------------------------------------
    def _on_ble_data(self, _sender, data: bytearray):
        for msg in self.parser.parse(bytes(data)):
            self._forward(msg)

    def _safe_send(self, msg):
        """Send to the virtual port without ever letting a port error crash us."""
        if self.midiout is None:
            return
        try:
            self.midiout.send_message(msg)
            self._send_err = False
        except Exception as e:
            if not self._send_err:
                self._send_err = True
                self.emit("log", f"MIDI output error (is LoopBe muted?): {e}")

    def _roblox_msg(self, msg):
        """Apply the live transpose to notes before Roblox encoding."""
        high = msg[0] & 0xF0
        if high in (0x80, 0x90) and len(msg) >= 3 and self.transpose:
            return bytes([msg[0], clamp(msg[1] + self.transpose, 0, 127), msg[2]])
        return bytes(msg)

    def _forward(self, msg):
        if not msg:
            return
        status = msg[0]
        high = status & 0xF0
        ch = status & 0x0F

        # Recording: capture channel-voice messages as the player performs them.
        if self._rec and 0x80 <= status < 0xF0:
            self._rec_events.append((time.monotonic() - self._rec_t0, bytes(msg)))

        # Display events for the visualizer.
        if high in (0x80, 0x90) and len(msg) >= 3:
            if high == 0x90 and msg[2] > 0:
                self.emit("note_on", msg[1], msg[2])
            else:
                self.emit("note_off", msg[1])
        elif high == 0xB0 and len(msg) >= 3:
            self.emit("cc", msg[1], msg[2])

        # Roblox keystrokes (independent of the MIDI port).
        if self.roblox.enabled:
            self.roblox.send(self._roblox_msg(msg))

        # MIDI port output is optional (Roblox-only mode has no port).
        if self.midiout is None:
            return

        if self.clean_output:
            if status >= 0xF0:
                return  # drop active sensing, clock, other realtime, and SysEx
            if high == 0xB0 and len(msg) >= 3:
                key = (ch, msg[1])
                if self._last_cc.get(key) == msg[2]:
                    return  # collapse repeated identical CCs (triple pedal sends)
                self._last_cc[key] = msg[2]

        if high in (0x80, 0x90) and len(msg) >= 3:
            note, vel = msg[1], msg[2]
            if high == 0x90 and vel > 0:
                out_note = clamp(note + self.transpose, 0, 127)
                out_vel = clamp(int(round(vel * self.vel_scale)), 1, 127)
                self.active_map[(ch, note)] = out_note
                self._safe_send([0x90 | ch, out_note, out_vel])
            else:
                out_note = self.active_map.pop((ch, note),
                                               clamp(note + self.transpose, 0, 127))
                self._safe_send([0x80 | ch, out_note, 0])
        else:
            self._safe_send(list(msg))  # CC, pitch bend, program, (system if not clean)

    # -- panic --------------------------------------------------------------
    def panic(self):
        self.loop.call_soon_threadsafe(self._panic)

    def _panic(self):
        # Release Roblox keys and reset the visualizer even when no MIDI port
        # is open (Roblox-only mode) - otherwise stuck keys never clear.
        if self.roblox.enabled:
            self.roblox.release_all()
        if self.midiout is not None:
            for (ch, note), out_note in list(self.active_map.items()):
                self._safe_send([0x80 | ch, out_note, 0])
            for ch in range(16):
                self._safe_send([0xB0 | ch, 123, 0])  # all notes off
                self._safe_send([0xB0 | ch, 64, 0])    # sustain off
        self.active_map.clear()
        self._last_cc.clear()
        self.emit("clear")

    # -- MIDI file playback (PC -> piano) -----------------------------------
    def load_midi(self, path):
        import mido
        mid = mido.MidiFile(path)
        events = []
        for m in mid:  # iteration applies tempo; m.time is delta seconds
            data = None if m.is_meta else bytes(m.bytes())
            events.append((m.time, data))
        self._events = events
        n_notes = sum(1 for _, d in events
                      if d and (d[0] & 0xF0) == 0x90 and len(d) >= 3 and d[2] > 0)
        return {"length": mid.length, "notes": n_notes,
                "name": Path(path).name}

    def _can_play(self):
        """A file can be played if there is at least one destination: the piano,
        Roblox keystrokes, or a virtual output port."""
        return (self._piano_ready() or self.roblox.enabled
                or self.midiout is not None)

    def play(self):
        if not self._events:
            self.emit("log", "Load a MIDI file first.")
            return
        if not self._can_play():
            self.emit("log", "Connect the piano, enable Roblox, or pick an "
                             "output port before playing.")
            return
        if self._play_future and not self._play_future.done():
            return
        self._play_stop = False
        self._play_pause = False
        self._play_future = self._submit(self._play_task())

    def stop_play(self):
        self._play_stop = True
        if self.roblox.enabled:
            self.roblox.release_all()

    def pause_toggle(self):
        self._play_pause = not self._play_pause
        return self._play_pause

    async def _ble_write(self, pkt):
        """Write-without-response, lightly paced. Pacing keeps the piano's receive
        buffer from overflowing; we never fall back to a response=True write, which
        on Windows can block for hundreds of ms and stall everything that follows."""
        if self._client is None:
            return False
        wait = self._last_ble_write + self._ble_gap - self.loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_ble_write = self.loop.time()
        try:
            await self._client.write_gatt_char(self._char, pkt, response=False)
            self._write_err = False
            return True
        except Exception as e:
            if not self._write_err:
                self._write_err = True
                self.emit("log", f"BLE write error: {e}")
            return False

    def _pkt_max(self):
        # Honor the device's write-without-response limit, but never exceed 20:
        # classic BLE-MIDI peripherals drop larger packets.
        return max(5, min(20, self._wwr_max))

    def _stamp(self, render_ms=None):
        """Return a monotonic BLE-MIDI render time in ms that never moves backwards.
        Pass an event's intended play moment, or nothing to stamp 'now'. A single
        high-water mark keeps every BLE write - playback, note-offs, program changes
        - in one clock domain so the receiver never sees a backwards jump (which it
        would misread as an 8-second wrap). The value is unmasked; the packet
        encoders mask it to 13 bits (and use the unmasked delta to split packets)."""
        if render_ms is None:
            render_ms = self.loop.time() * 1000.0
        if render_ms < self._tx_last_ms:
            render_ms = self._tx_last_ms
        self._tx_last_ms = render_ms
        return int(round(render_ms))

    async def _emit_piano(self, msgs):
        """Deliver prepared MIDI messages to the piano over the active transport.
        BLE packs them into <=20-byte packets and paces; a wired MIDI-out sends
        each one immediately (USB needs no pacing)."""
        if not msgs or not self._piano_ready():
            return
        if self.source_mode == "midi":
            po = self.piano_out
            if po is None:
                return
            for m in msgs:
                try:
                    po.send_message(list(m))
                except Exception:
                    pass
        else:
            small = [m for m in msgs if len(m) <= 16]  # SysEx won't fit one packet
            ts = self._stamp()                          # all share one "play now" stamp
            for pkt in self._encode_timed([(ts, m) for m in small], self._pkt_max(),
                                          running=self._running_status):
                await self._ble_write(pkt)

    def _piano_bytes(self, data):
        """Transform a file message for the piano: drop voice-override messages,
        scale velocity, transpose notes, force channel 1. Returns bytes, or None
        to drop the message."""
        high = data[0] & 0xF0
        if data[0] >= 0xF0:
            return None  # System Common/Real-Time/SysEx are not useful to the piano
        if self.piano_voice is not None:
            if high == 0xC0:  # Program Change
                return None
            if high == 0xB0 and len(data) >= 3 and data[1] in (0, 32):  # Bank Select
                return None
        data = bytes(data)
        if high in (0x80, 0x90) and len(data) >= 3:
            note, vel = data[1], data[2]
            if high == 0x90 and vel > 0 and self.vel_scale != 1.0:
                vel = clamp(int(round(vel * self.vel_scale)), 1, 127)
            if self.transpose:
                note = clamp(note + self.transpose, 0, 127)
            data = bytes([data[0], note, vel])
        if self.remap_ch1 and 0x80 <= data[0] < 0xF0:
            data = bytes([data[0] & 0xF0]) + data[1:]  # force channel 1
        return data

    def select_voice(self, program):
        """Set (and immediately send, if connected) the piano's playback voice.
        program is 0-based, or None to leave the file/panel in control."""
        self.piano_voice = program
        if program is not None and self._piano_ready():
            self._submit(self._send_program(program))

    async def _send_program(self, program):
        if not self._piano_ready():
            return
        await self._emit_piano([bytes([0xC0, program & 0x7F])])

    def test_voice(self, program):
        """Select a program number and play a sustained chord so the user can
        hear which voice that number maps to on their piano."""
        if not self._piano_ready():
            self.emit("log", "Connect to the piano first to test voices.")
            return
        self._submit(self._test_voice(program))

    async def _test_voice(self, program):
        if not self._piano_ready():
            return
        await self._send_program(program)
        await asyncio.sleep(0.08)
        chord = [60, 64, 67, 72]  # C major, channel 1
        await self._emit_piano([bytes([0x90, n, 95]) for n in chord])
        await asyncio.sleep(1.6)
        await self._emit_piano([bytes([0x80, n, 0]) for n in chord])

    def test_roblox(self):
        """Focus Roblox and play a C-major scale through the current Roblox
        output mode, so the user can confirm their setup is wired up."""
        self._submit(self._test_roblox())

    async def _test_roblox(self):
        self.emit("log", "Roblox test: focusing the Roblox window, then "
                         "playing a C scale...")
        self.roblox.focus()
        await asyncio.sleep(0.35)
        scale = [60, 62, 64, 65, 67, 69, 71, 72]  # C major up one octave
        for n in scale:
            self.roblox.send(bytes([0x90, n, 90]), force=True)
            await asyncio.sleep(0.22)
            self.roblox.send(bytes([0x80, n, 0]), force=True)
            await asyncio.sleep(0.03)
        self.emit("log", "Roblox test done. If you didn't see notes, check the "
                         "Help window's Roblox section.")

    def _flatten_schedule(self):
        """Absolute-time event list: [(play_time_seconds, message_bytes), ...]
        (tempo is applied by mido iteration in load_midi)."""
        sched, t = [], 0.0
        for delay, data in self._events:
            t += delay
            if data is not None:
                sched.append((t, data))
        return sched

    def _group_events(self):
        """Collapse simultaneous events (delta 0) into one group so chords go
        out together. Returns [(gap_seconds, [messages]), ...]."""
        groups = []
        t = 0.0
        cur_t = None
        cur = None
        for delay, data in self._events:
            t += delay
            if data is None:
                continue
            if cur is not None and t == cur_t:
                cur.append(data)
            else:
                if cur is not None:
                    groups.append((cur_t, cur))
                cur_t, cur = t, [data]
        if cur is not None:
            groups.append((cur_t, cur))
        out, prev = [], 0.0
        for gt, msgs in groups:
            out.append((gt - prev, msgs))
            prev = gt
        return out

    @staticmethod
    @staticmethod
    def _encode_timed(timed, max_len, max_span_ms=100, running=True):
        """Pack (render_ms, message_bytes) pairs into BLE-MIDI packets. Each message
        gets its own timestamp byte so the receiver reproduces exact inter-note
        timing; `render_ms` is the UNMASKED monotonic render time, masked to 13 bits
        here. A new packet starts when adding a message would exceed `max_len` bytes
        OR span more than `max_span_ms` from the packet's first message (the latter
        keeps at most one 128 ms timestamp wrap per packet, which the receiver can
        track). `timed` must be ordered by render_ms.

        With `running` set, the spec's Running Status is used: a message with the
        same status as the previous one in the packet drops its status byte, and if
        it also shares the timestamp it drops that too. Note-Offs are sent as
        Note-On velocity 0 so a whole arpeggio shares one status - this fits ~50%
        more notes per packet, which is the main lever for fast pieces over BLE."""
        packets = []
        cur = None
        base_ms = 0
        run_status = None   # status byte currently in effect within the packet
        run_low = None      # last timestamp-low byte emitted within the packet
        for ms, m in timed:
            m = bytes(m)
            status = m[0]
            if running and (status & 0xF0) == 0x80 and len(m) >= 3:
                status = 0x90 | (status & 0x0F)   # Note-Off -> Note-On vel 0
                data = bytes([m[1], 0])
            else:
                data = m[1:]
            ts = ms & 0x1FFF
            low = 0x80 | (ts & 0x7F)
            high = 0x80 | ((ts >> 7) & 0x3F)
            if cur is not None:
                if running and status == run_status and status < 0xF0:
                    chunk = data if low == run_low else bytes([low]) + data
                else:
                    chunk = bytes([low, status]) + data
                if len(cur) + len(chunk) <= max_len and ms - base_ms <= max_span_ms:
                    cur += chunk
                    run_status, run_low = status, low
                    continue
                packets.append(bytes(cur))
            cur = bytearray([high, low, status]) + data   # first msg of packet: full
            base_ms = ms
            run_status, run_low = status, low
        if cur is not None:
            packets.append(bytes(cur))
        return packets

    async def _emit_timed(self, timed):
        """Send timestamped messages to the piano over BLE (one or more packets)."""
        if self._client is None or not timed:
            return
        for pkt in self._encode_timed(timed, self._pkt_max(),
                                      running=self._running_status):
            await self._ble_write(pkt)

    def _dispatch_event(self, data, held):
        """Fan ONE playback event out to every destination, consistently:
          - visualizer  : the original file notes (a 'score' view, like live)
          - Roblox       : transposed notes (so Piano Rooms matches the piano)
          - virtual port : transposed + velocity-scaled (mirrors the piano)
          - piano        : the fully transformed bytes (returned to the caller)
        Held notes remember the exact transposed pitch at Note-On time, so a
        mid-song transpose change can never strand a note on any destination.
        Returns the bytes to send to the piano, or None to send nothing."""
        high = data[0] & 0xF0
        ch = data[0] & 0x0F
        od = self._piano_bytes(data)

        # Note-On
        if high == 0x90 and len(data) >= 3 and data[2] > 0:
            tnote, tvel = od[1], od[2]            # transposed note, scaled velocity
            self.emit("note_on", data[1], data[2])
            if self.roblox.enabled:
                # Roblox uses the transposed note but the file's own velocity
                # (velocity scaling is for the piano/port, matching the live path).
                self.roblox.send(bytes([0x90 | ch, tnote, data[2]]))
            if self.play_to_output and self.midiout is not None:
                self._safe_send([0x90 | ch, tnote, tvel])
            held[(ch, data[1])] = (bytes([0x80 | (od[0] & 0x0F), tnote, 0]), tnote)
            return od

        # Note-Off (status 0x80, or 0x90 with velocity 0)
        if high in (0x80, 0x90) and len(data) >= 3:
            self.emit("note_off", data[1])
            stored = held.pop((ch, data[1]), None)
            if stored:
                piano_off, tnote = stored
            else:
                piano_off = od if od is not None else bytes([0x80 | ch, data[1], 0])
                tnote = piano_off[1]
            if self.roblox.enabled:
                self.roblox.send(bytes([0x80 | ch, tnote, 0]))
            if self.play_to_output and self.midiout is not None:
                self._safe_send([0x80 | ch, tnote, 0])
            return piano_off

        # Other channel messages (CC, pitch bend, program). System/SysEx -> od is
        # None and is dropped everywhere.
        if high == 0xB0 and len(data) >= 3:
            self.emit("cc", data[1], data[2])
            if self.roblox.enabled:
                self.roblox.send(bytes(data))   # sustain (CC64) is the only one used
        if self.play_to_output and self.midiout is not None and 0x80 <= data[0] < 0xF0:
            self._safe_send(list(data))
        return od

    async def _play_task(self):
        self.emit("play_state", "playing")
        if self.piano_voice is not None:
            await self._send_program(self.piano_voice)  # set the piano's voice
            await asyncio.sleep(0.05)
        sched = self._flatten_schedule()
        total_s = sched[-1][0] if sched else 0.0
        try:
            while True:
                # (orig channel, note) -> (exact piano Note-Off bytes, transposed note)
                held = {}
                if self.source_mode == "ble" and self._client is not None:
                    await self._run_playback_ble(sched, held)
                else:
                    await self._run_playback_wired(sched, held)
                await self._finish_playback(held)
                if self._play_stop or not self.loop_play or not self._can_play():
                    break
                await asyncio.sleep(0.15)  # brief gap before the file repeats
        except Exception as e:
            self.emit("log", f"Playback error: {e}")
        self.emit("play_progress", total_s, total_s)
        self.emit("play_state", "stopped")

    async def _run_playback_wired(self, sched, held):
        """Precise per-event scheduler (no BLE batching): used for USB/DIN MIDI
        and for Roblox/virtual-port-only playback. Sends each event at its exact
        time, grouping simultaneous events into one burst."""
        n = len(sched)
        total_s = sched[-1][0] if sched else 0.0
        idx = 0
        next_t = self.loop.time()
        prev_play = 0.0
        last_emit = -1.0
        while idx < n:
            if self._play_stop or not self._can_play():
                break
            while self._play_pause and not self._play_stop:
                await asyncio.sleep(0.03)
                next_t = self.loop.time()
            if self._play_stop or not self._can_play():
                break
            play_s = sched[idx][0]
            group = []
            while idx < n and sched[idx][0] == play_s:
                group.append(sched[idx][1])
                idx += 1
            next_t += (play_s - prev_play) / max(0.1, self.play_tempo)
            prev_play = play_s
            now = self.loop.time()
            if next_t > now:
                await asyncio.sleep(next_t - now)
            elif now - next_t > 0.12:
                next_t = now
            out = []
            for d in group:
                pm = self._dispatch_event(d, held)
                if pm is not None:
                    out.append(pm)
            await self._emit_piano(out)
            if play_s - last_emit >= 0.2:
                last_emit = play_s
                self.emit("play_progress", play_s, total_s)

    async def _run_playback_ble(self, sched, held):
        """Spec-correct BLE-MIDI playback: a steady transmit loop (~one packet
        per connection interval) sends upcoming events slightly ahead of time,
        each stamped with its render time, so the piano reproduces exact timing
        while the send rate stays bounded (no buffer overflow, no dropped notes)."""
        n = len(sched)
        total_s = sched[-1][0] if sched else 0.0
        i = 0
        last_emit = -1.0
        prev = self.loop.time()
        music = 0.0          # elapsed musical time (advances with tempo, not pause)
        MAX_PER_TICK = 24    # cap events per tick so a burst can't overflow the link
        while i < n:
            if self._play_stop or self._client is None:
                break
            if self._play_pause:
                while self._play_pause and not self._play_stop:
                    await asyncio.sleep(0.02)
                prev = self.loop.time()  # don't advance musical time while paused
                if self._play_stop or self._client is None:
                    break
            now = self.loop.time()
            tempo = max(0.1, self.play_tempo)
            music += (now - prev) * tempo
            prev = now
            horizon = music + self._ble_lookahead * tempo
            now_ms = now * 1000.0    # absolute monotonic; same domain as _stamp
            batch = []
            count = 0
            while i < n and sched[i][0] <= horizon and count < MAX_PER_TICK:
                play_s, data = sched[i]
                i += 1
                count += 1
                pm = self._dispatch_event(data, held)
                if pm is None:
                    continue
                # Render time = now + (real seconds until this event is due).
                render_ms = now_ms + max(0.0, (play_s - music) / tempo * 1000.0)
                batch.append((self._stamp(render_ms), pm))
            if batch:
                await self._emit_timed(batch)
            if music - last_emit >= 0.2:
                last_emit = music
                self.emit("play_progress", min(music, total_s), total_s)
            await asyncio.sleep(self._ble_interval)

    async def _finish_playback(self, held):
        """Release everything still sounding on every destination: exact Note-Offs
        to the piano and the virtual port (using the pitch actually sent), a held-
        key release for Roblox, and a sustain/all-notes-off backstop per channel
        (the piano ignores CC123 but honors CC64; Synthesia honors CC123)."""
        piano_offs = []
        for (ch, _note), (piano_off, tnote) in held.items():
            piano_offs.append(piano_off)
            if self.play_to_output and self.midiout is not None:
                self._safe_send([0x80 | ch, tnote, 0])
        await self._emit_piano(piano_offs)
        if self.roblox.enabled:
            self.roblox.release_all()
        backstop = []
        for ch in range(16):
            if self.play_to_output and self.midiout is not None:
                self._safe_send([0xB0 | ch, 123, 0])
                self._safe_send([0xB0 | ch, 64, 0])
            backstop.append(bytes([0xB0 | ch, 123, 0]))
            backstop.append(bytes([0xB0 | ch, 64, 0]))
        await self._emit_piano(backstop)
        self.emit("clear")

    # -- recording (capture what is played on the piano) --------------------
    def record_start(self):
        self._rec_events = []
        self._rec_t0 = time.monotonic()
        self._rec = True
        self.emit("log", "Recording started.")

    def record_stop(self):
        self._rec = False
        return len(self._rec_events)

    def save_recording(self, path):
        """Write the captured performance to a Standard MIDI File."""
        import mido
        ppq, tempo = 480, 500000  # 120 BPM reference grid
        scale = ppq * 1_000_000 / tempo  # seconds -> ticks
        mid = mido.MidiFile(ticks_per_beat=ppq)
        tr = mido.MidiTrack()
        mid.tracks.append(tr)
        tr.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
        prev_tick = 0
        for ta, raw in self._rec_events:
            try:
                m = mido.Message.from_bytes(bytes(raw))
            except Exception:
                continue
            abs_tick = int(round(ta * scale))
            m.time = max(0, abs_tick - prev_tick)
            prev_tick = abs_tick
            tr.append(m)
        tr.append(mido.MetaMessage("end_of_track", time=1))
        mid.save(path)
        return len(self._rec_events)


# ---------------------------------------------------------------------------
# Colors / theme
# ---------------------------------------------------------------------------
BG = "#14161b"
PANEL = "#1c1f27"
FG = "#e6e8ee"
MUTED = "#8b90a0"
ACCENT = "#5b8cff"
ACCENT2 = "#27c093"
KEY_WHITE = "#f4f5f8"
KEY_WHITE_EDGE = "#c5c8d2"
KEY_BLACK = "#2a2d36"
KEY_ON_WHITE = "#5b8cff"
KEY_ON_BLACK = "#3f6fe0"
STATUS_COLORS = {
    "idle": MUTED, "scan": "#e0a13c", "ok": ACCENT2,
    "error": "#e0584c", "off": MUTED,
}


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Shelementyev's BLE-MIDI Bridge {APP_VERSION}")
        self.configure(bg=BG)

        self.q = queue.Queue()
        self.controller = BridgeController(self.q)

        self.devices = []          # [(name, address)]
        self.input_ports = []      # MIDI input port names (USB sources)
        self.active_notes = set()  # notes currently held (for visualizer)
        self.key_items = {}        # note -> canvas rect id
        self.note_count = 0
        self.sustain_on = False
        self._log_lines = 0
        self._recording = False
        self._rec_started = 0.0
        self._midi_len = 0.0       # loaded file length (s), for the time display

        self._build_style()
        self._build_ui()
        self._load_config()

        # Open at a size that shows everything, capped to the screen so it never
        # spills off the edges. (Avoids the user having to resize on first run.)
        self.update_idletasks()
        req_w, req_h = self.winfo_reqwidth(), self.winfo_reqheight()
        max_w = self.winfo_screenwidth() - 60
        max_h = self.winfo_screenheight() - 100
        self.geometry(f"{min(req_w, max_w)}x{min(req_h, max_h)}")
        self.minsize(min(req_w, 900), min(req_h, 600))
        self._raise_timer_resolution()  # 1 ms timers on Windows -> smooth timing
        self._hk_listener = None
        self._start_hotkey()

        self.after(33, self._poll_queue)
        self.refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.cfg.get("auto_connect") and self.cfg.get("last_address"):
            self.after(400, self._auto_connect)

    # -- styling ------------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        # The Combobox dropdown is a classic Tk Listbox that ignores ttk themes,
        # so colour it through the option database (must happen before the
        # widgets are created). Without this the list is dark text on dark bg.
        self.option_add("*TCombobox*Listbox.background", "#21242e")
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#0d1118")
        self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))
        style.configure(".", background=PANEL, foreground=FG,
                        fieldbackground=PANEL, bordercolor="#2a2d36")
        style.configure("TFrame", background=PANEL)
        style.configure("Bg.TFrame", background=BG)
        style.configure("TLabel", background=PANEL, foreground=FG)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI Semibold", 15))
        style.configure("TButton", background="#2a2d36", foreground=FG,
                        borderwidth=0, focuscolor=PANEL, padding=6)
        style.map("TButton",
                  background=[("active", "#343845"), ("disabled", "#22242c")],
                  foreground=[("disabled", MUTED)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#0d1118")
        style.map("Accent.TButton", background=[("active", "#6f9aff")])
        style.configure("Danger.TButton", background="#3a2730", foreground="#ffb3ac")
        style.map("Danger.TButton", background=[("active", "#4a2f3a")])
        style.configure("TCombobox", fieldbackground="#2a2d36",
                        background="#2a2d36", foreground=FG, arrowcolor=FG,
                        bordercolor="#2a2d36", padding=4)
        # Pin the readonly/disabled colours so the selected value stays readable
        # (otherwise the highlighted text matches the field and vanishes).
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#2a2d36"), ("disabled", "#22242c")],
                  foreground=[("readonly", FG), ("disabled", MUTED)],
                  selectbackground=[("readonly", "#2a2d36")],
                  selectforeground=[("readonly", FG)],
                  arrowcolor=[("disabled", MUTED)])
        style.configure("TSpinbox", fieldbackground="#2a2d36", background="#2a2d36",
                        foreground=FG, arrowcolor=FG, bordercolor="#2a2d36",
                        insertcolor=FG, padding=4)
        style.map("TSpinbox",
                  fieldbackground=[("disabled", "#22242c")],
                  foreground=[("disabled", MUTED)],
                  arrowcolor=[("disabled", MUTED)])
        style.configure("TCheckbutton", background=PANEL, foreground=FG)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("Horizontal.TScale", background=PANEL)

    # -- layout -------------------------------------------------------------
    def _build_ui(self):
        # Header
        header = ttk.Frame(self, style="Bg.TFrame")
        header.pack(fill="x", padx=16, pady=(14, 8))
        ttk.Label(header, text="Shelementyev's BLE-MIDI Bridge", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Help / Setup",
                   command=self._open_help).pack(side="left", padx=(12, 0))
        self.status_dot = tk.Canvas(header, width=12, height=12, bg=BG,
                                    highlightthickness=0)
        self.status_dot.pack(side="right")
        self._dot = self.status_dot.create_oval(2, 2, 11, 11, fill=MUTED, outline="")
        self.status_lbl = ttk.Label(header, text="Idle", style="Title.TLabel")
        self.status_lbl.configure(font=("Segoe UI", 10))
        self.status_lbl.pack(side="right", padx=(0, 8))

        # Connection panel
        conn = ttk.Frame(self, padding=12)
        conn.pack(fill="x", padx=16, pady=6)
        conn.columnconfigure(1, weight=1)

        ttk.Label(conn, text="Source").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.source_cb = ttk.Combobox(conn, state="readonly",
                                      values=["Bluetooth LE"])
        self.source_cb.current(0)
        self.source_cb.grid(row=0, column=1, sticky="ew")
        self.source_cb.bind("<<ComboboxSelected>>", self._on_source_change)
        ttk.Button(conn, text="Refresh", command=self.refresh_ports).grid(
            row=0, column=2, padx=(8, 0))

        self.piano_lbl = ttk.Label(conn, text="Piano (BLE)")
        self.piano_lbl.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self.device_cb = ttk.Combobox(conn, state="readonly", values=[])
        self.device_cb.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.scan_btn = ttk.Button(conn, text="Scan", command=self.on_scan)
        self.scan_btn.grid(row=1, column=2, padx=(8, 0), pady=(8, 0))

        ttk.Label(conn, text="Forward to").grid(row=2, column=0, sticky="w",
                                                padx=(0, 10), pady=(8, 0))
        self.port_cb = ttk.Combobox(conn, state="readonly", values=[])
        self.port_cb.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(conn, text="(LoopBe / loopMIDI - optional)",
                  style="Muted.TLabel").grid(row=2, column=2, padx=(8, 0),
                                             pady=(8, 0), sticky="w")

        btns = ttk.Frame(conn)
        btns.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.connect_btn = ttk.Button(btns, text="Connect", style="Accent.TButton",
                                      command=self.on_connect)
        self.connect_btn.pack(side="left")
        self.disconnect_btn = ttk.Button(btns, text="Disconnect",
                                         command=self.on_disconnect, state="disabled")
        self.disconnect_btn.pack(side="left", padx=(8, 0))
        self.autoconn_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btns, text="Auto-connect on launch",
                        variable=self.autoconn_var).pack(side="right")
        self.autorecon_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btns, text="Auto-reconnect", variable=self.autorecon_var,
                        command=self._sync_settings).pack(side="right", padx=(0, 14))

        # Controls panel (transpose / velocity / panic)
        ctrl = ttk.Frame(self, padding=12)
        ctrl.pack(fill="x", padx=16, pady=6)

        ttk.Label(ctrl, text="Transpose").pack(side="left")
        ttk.Button(ctrl, text="-12", width=4,
                   command=lambda: self.bump_transpose(-12)).pack(side="left", padx=(8, 2))
        ttk.Button(ctrl, text="-1", width=3,
                   command=lambda: self.bump_transpose(-1)).pack(side="left", padx=2)
        self.transpose_lbl = ttk.Label(ctrl, text="0 st", width=6, anchor="center")
        self.transpose_lbl.pack(side="left", padx=2)
        ttk.Button(ctrl, text="+1", width=3,
                   command=lambda: self.bump_transpose(1)).pack(side="left", padx=2)
        ttk.Button(ctrl, text="+12", width=4,
                   command=lambda: self.bump_transpose(12)).pack(side="left", padx=(2, 2))
        ttk.Button(ctrl, text="Reset", width=6,
                   command=lambda: self.set_transpose(0)).pack(side="left", padx=(6, 0))

        self.panic_btn = ttk.Button(ctrl, text="Panic  (All Notes Off)",
                                    style="Danger.TButton", command=self.on_panic)
        self.panic_btn.pack(side="right")

        vel = ttk.Frame(self, padding=(12, 0, 12, 8))
        vel.pack(fill="x", padx=16)
        ttk.Label(vel, text="Velocity").pack(side="left")
        self.vel_var = tk.IntVar(value=100)
        self.vel_scale = ttk.Scale(vel, from_=25, to=200, variable=self.vel_var,
                                   command=self._on_vel, length=240)
        self.vel_scale.pack(side="left", padx=(8, 8))
        self.vel_lbl = ttk.Label(vel, text="100%", width=6)
        self.vel_lbl.pack(side="left")
        self.clean_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(vel, text="Clean output (filter sensing/clock - recommended)",
                        variable=self.clean_var,
                        command=self._sync_settings).pack(side="right")

        # Roblox keystroke output: Piano Rooms (MIDI mod) or Virtual Piano keys
        rbx = ttk.Frame(self, padding=(12, 0, 12, 6))
        rbx.pack(fill="x", padx=16)
        ttk.Label(rbx, text="Roblox").pack(side="left")
        self.roblox_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(rbx, text="Send to Roblox  (keep the game window focused)",
                        variable=self.roblox_var,
                        command=self._sync_settings).pack(side="left", padx=(8, 0))
        ttk.Label(rbx, text="Type:", style="Muted.TLabel").pack(side="left", padx=(12, 4))
        self.roblox_mode_var = tk.StringVar(value=ROBLOX_MODES[0])
        self.roblox_mode_cb = ttk.Combobox(
            rbx, state="readonly", width=16, values=ROBLOX_MODES,
            textvariable=self.roblox_mode_var)
        self.roblox_mode_cb.pack(side="left")
        self.roblox_mode_cb.bind("<<ComboboxSelected>>", lambda _=None: self._sync_settings())
        ttk.Button(rbx, text="Test", width=6,
                   command=self.on_test_roblox).pack(side="left", padx=(8, 0))
        ttk.Label(rbx, text="Stop hotkey: F8", style="Muted.TLabel").pack(side="right")

        # Recording (capture what you play on the piano -> .mid)
        rec = ttk.Frame(self, padding=(12, 0, 12, 6))
        rec.pack(fill="x", padx=16)
        ttk.Label(rec, text="Record").pack(side="left")
        self.record_btn = ttk.Button(rec, text="● Record", command=self.on_record)
        self.record_btn.pack(side="left", padx=(8, 0))
        self.record_lbl = ttk.Label(rec, text="idle", style="Muted.TLabel")
        self.record_lbl.pack(side="left", padx=(10, 0))

        # Play MIDI file -> piano
        play = ttk.Frame(self, padding=12)
        play.pack(fill="x", padx=16, pady=6)
        play.columnconfigure(1, weight=1)
        ttk.Label(play, text="Play to piano").grid(row=0, column=0, sticky="w",
                                                    padx=(0, 10))
        self.file_lbl = ttk.Label(play, text="No file loaded", style="Muted.TLabel")
        self.file_lbl.grid(row=0, column=1, sticky="w")
        ttk.Button(play, text="Load MIDI...", command=self.on_load_midi).grid(
            row=0, column=2, padx=(8, 0))

        row2 = ttk.Frame(play)
        row2.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.play_btn = ttk.Button(row2, text="Play", style="Accent.TButton",
                                   command=self.on_play, state="disabled")
        self.play_btn.pack(side="left")
        self.pause_btn = ttk.Button(row2, text="Pause", command=self.on_pause,
                                    state="disabled")
        self.pause_btn.pack(side="left", padx=(8, 0))
        self.stop_btn = ttk.Button(row2, text="Stop", command=self.on_stop_play,
                                   state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Loop", variable=self.loop_var,
                        command=self._sync_settings).pack(side="left", padx=(14, 0))

        ttk.Label(row2, text="Speed").pack(side="left", padx=(16, 4))
        self.tempo_var = tk.IntVar(value=100)
        ttk.Scale(row2, from_=50, to=200, variable=self.tempo_var,
                  command=self._on_tempo, length=140).pack(side="left")
        self.tempo_lbl = ttk.Label(row2, text="100%", width=5)
        self.tempo_lbl.pack(side="left", padx=(4, 0))

        self.ch1_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="Send on ch.1", variable=self.ch1_var,
                        command=self._sync_settings).pack(side="right")
        self.play_out_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="To output (Synthesia)",
                        variable=self.play_out_var,
                        command=self._sync_settings).pack(side="right", padx=(0, 12))

        prow = ttk.Frame(play)
        prow.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        prow.columnconfigure(0, weight=1)
        self.play_prog = ttk.Progressbar(prow, mode="determinate")
        self.play_prog.grid(row=0, column=0, sticky="ew")
        self.time_lbl = ttk.Label(prow, text="0:00 / 0:00", style="Muted.TLabel",
                                  width=12, anchor="e")
        self.time_lbl.grid(row=0, column=1, padx=(8, 0))

        # Voice finder: the piano's Program-Change->voice map isn't documented,
        # so let the user step through numbers and hear each one.
        vrow = ttk.Frame(play)
        vrow.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.voice_on_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(vrow, text="Set piano voice  #",
                        variable=self.voice_on_var,
                        command=self._on_voice).pack(side="left")
        self.voice_num = tk.IntVar(value=0)
        ttk.Spinbox(vrow, from_=0, to=15, width=4, textvariable=self.voice_num,
                    command=self._on_voice).pack(side="left", padx=(4, 8))
        ttk.Button(vrow, text="Test voice", command=self.on_test_voice).pack(side="left")
        ttk.Label(vrow, text="BLE interval", style="Muted.TLabel").pack(side="left",
                                                                       padx=(16, 2))
        self.gap_var = tk.IntVar(value=15)
        ttk.Spinbox(vrow, from_=5, to=30, width=4, textvariable=self.gap_var,
                    command=self._sync_settings).pack(side="left")
        ttk.Label(vrow, text="ms", style="Muted.TLabel").pack(side="left", padx=(2, 0))
        ttk.Label(vrow, text="Buffer", style="Muted.TLabel").pack(side="left",
                                                                  padx=(14, 2))
        self.buffer_var = tk.IntVar(value=30)
        ttk.Spinbox(vrow, from_=20, to=400, increment=10, width=5,
                    textvariable=self.buffer_var,
                    command=self._sync_settings).pack(side="left")
        ttk.Label(vrow, text="ms", style="Muted.TLabel").pack(side="left", padx=(2, 12))
        self.pack_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(vrow, text="Pack notes (faster, for dense songs)",
                        variable=self.pack_var,
                        command=self._sync_settings).pack(side="left")

        # Visualizer
        viz = ttk.Frame(self, padding=12)
        viz.pack(fill="both", expand=True, padx=16, pady=6)
        self.canvas = tk.Canvas(viz, height=130, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda e: self._draw_keyboard())

        info = ttk.Frame(viz)
        info.pack(fill="x", pady=(8, 0))
        self.sustain_lbl = ttk.Label(info, text="Sustain: off", style="Muted.TLabel")
        self.sustain_lbl.pack(side="left")
        self.sost_lbl = ttk.Label(info, text="Sostenuto: off", style="Muted.TLabel")
        self.sost_lbl.pack(side="left", padx=(14, 0))
        self.soft_lbl = ttk.Label(info, text="Soft: off", style="Muted.TLabel")
        self.soft_lbl.pack(side="left", padx=(14, 0))
        self.last_lbl = ttk.Label(info, text="Last: -", style="Muted.TLabel")
        self.last_lbl.pack(side="left", padx=(18, 0))
        self.count_lbl = ttk.Label(info, text="Notes: 0", style="Muted.TLabel")
        self.count_lbl.pack(side="right")

        # Log
        logf = ttk.Frame(self, padding=(12, 0, 12, 12))
        logf.pack(fill="x", padx=16)
        self.log = tk.Text(logf, height=5, bg="#0f1116", fg=MUTED, relief="flat",
                           font=("Consolas", 9), highlightthickness=0, wrap="none")
        self.log.pack(fill="x")
        self.log.configure(state="disabled")

    # -- keyboard drawing ---------------------------------------------------
    def _draw_keyboard(self):
        c = self.canvas
        c.delete("all")
        self.key_items.clear()
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10:
            return
        for r in piano_layout(w, h):
            if r["black"]:
                continue
            item = c.create_rectangle(r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"],
                                      fill=KEY_WHITE, outline=KEY_WHITE_EDGE)
            self.key_items[r["note"]] = (item, False)
        for r in piano_layout(w, h):
            if not r["black"]:
                continue
            item = c.create_rectangle(r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"],
                                      fill=KEY_BLACK, outline="#0c0d11")
            self.key_items[r["note"]] = (item, True)
        for n in self.active_notes:
            self._paint_key(n, True)

    def _paint_key(self, note, on):
        entry = self.key_items.get(note)
        if not entry:
            return
        item, black = entry
        if on:
            self.canvas.itemconfig(item, fill=KEY_ON_BLACK if black else KEY_ON_WHITE)
        else:
            self.canvas.itemconfig(item, fill=KEY_BLACK if black else KEY_WHITE)

    @staticmethod
    def _fmt_time(seconds):
        seconds = max(0, int(round(seconds)))
        return f"{seconds // 60}:{seconds % 60:02d}"

    # -- queue / event handling --------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                ev = self.q.get_nowait()
                self._handle(ev)
        except queue.Empty:
            pass
        if self._recording:
            secs = int(time.monotonic() - self._rec_started)
            self.record_lbl.configure(text=f"recording... {secs}s")
        self.after(33, self._poll_queue)

    def _handle(self, ev):
        kind = ev[0]
        if kind == "status":
            _, text, key = ev
            self.status_lbl.configure(text=text)
            self.status_dot.itemconfig(self._dot, fill=STATUS_COLORS.get(key, MUTED))
            busy = key in ("ok", "scan")
            self.connect_btn.configure(state="disabled" if busy else "normal")
            self.disconnect_btn.configure(state="normal" if busy else "disabled")
            self.source_cb.configure(state="disabled" if busy else "readonly")
            if busy:
                self.scan_btn.configure(state="disabled")
            else:
                self._on_source_change()  # restore device/scan states for the source
        elif kind == "devices":
            self.devices = ev[1]
            labels = [f"{name}   ({addr})" for name, addr in self.devices]
            self.device_cb.configure(values=labels)
            if labels and not self.device_cb.get():
                self.device_cb.current(0)
        elif kind == "note_on":
            _, note, vel = ev
            self.active_notes.add(note)
            self._paint_key(note, True)
            self.note_count += 1
            self.count_lbl.configure(text=f"Notes: {self.note_count}")
            self.last_lbl.configure(text=f"Last: {note_name(note)}  v{vel}")
        elif kind == "note_off":
            note = ev[1]
            self.active_notes.discard(note)
            self._paint_key(note, False)
        elif kind == "cc":
            _, num, val = ev
            on = val >= 64
            if num == 64:
                self.sustain_on = on
                self.sustain_lbl.configure(text=f"Sustain: {'ON' if on else 'off'}")
            elif num == 66:
                self.sost_lbl.configure(text=f"Sostenuto: {'ON' if on else 'off'}")
            elif num == 67:
                self.soft_lbl.configure(text=f"Soft: {'ON' if on else 'off'}")
        elif kind == "clear":
            for n in list(self.active_notes):
                self._paint_key(n, False)
            self.active_notes.clear()
        elif kind == "play_state":
            playing = ev[1] == "playing"
            self.play_btn.configure(state="disabled" if playing else "normal")
            self.pause_btn.configure(state="normal" if playing else "disabled",
                                     text="Pause")
            self.stop_btn.configure(state="normal" if playing else "disabled")
            if ev[1] == "stopped":
                self.play_prog["value"] = 0
                self.time_lbl.configure(text=f"0:00 / {self._fmt_time(self._midi_len)}")
        elif kind == "play_progress":
            _, pos, total = ev
            self.play_prog["maximum"] = max(0.001, total)
            self.play_prog["value"] = min(pos, total)
            self.time_lbl.configure(
                text=f"{self._fmt_time(pos)} / {self._fmt_time(total)}")
        elif kind == "log":
            self._append_log(ev[1])

    def _append_log(self, text):
        self.log.configure(state="normal")
        stamp = time.strftime("%H:%M:%S")
        self.log.insert("end", f"[{stamp}] {text}\n")
        self._log_lines += 1
        if self._log_lines > 200:
            self.log.delete("1.0", "2.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    # -- actions ------------------------------------------------------------
    def on_scan(self):
        self.scan_btn.configure(state="disabled")
        self.controller.scan(timeout=6.0)

    def refresh_ports(self):
        # Output ports. On macOS/Linux we can publish our own port, listed first.
        try:
            real_ports = self.controller.list_output_ports()
        except Exception as e:
            self._append_log(f"Could not list MIDI ports: {e}")
            real_ports = []
        display = ([BUILTIN_PORT_LABEL] if VIRTUAL_OUT_SUPPORTED else []) + list(real_ports)
        self.port_cb.configure(values=display)
        if display:
            target = self.cfg.get("last_port") if hasattr(self, "cfg") else None
            idx = None
            for i, p in enumerate(display):
                if target and target.lower() in p.lower():
                    idx = i
                    break
                if "loopbe" in p.lower() or "loopmidi" in p.lower():
                    idx = i
            self.port_cb.current(idx if idx is not None else 0)
        else:
            self._append_log("No MIDI output ports found. To drive Synthesia or a "
                             "DAW, install loopMIDI (see Help), then Refresh - this "
                             "isn't needed for Roblox.")

        # Input sources: Bluetooth + each MIDI input port (the piano via USB).
        try:
            self.input_ports = self.controller.list_input_ports()
        except Exception as e:
            self.input_ports = []
            self._append_log(f"Could not list MIDI inputs: {e}")
        keep = self.source_cb.get()
        values = ["Bluetooth LE"] + self.input_ports
        self.source_cb.configure(values=values)
        saved = getattr(self, "_saved_source", None)
        if saved and saved in values:
            self.source_cb.set(saved)
            self._saved_source = None
        elif keep in values:
            self.source_cb.set(keep)
        else:
            self.source_cb.current(0)
        self._on_source_change()

    def _source_is_ble(self):
        return self.source_cb.current() <= 0

    def _on_source_change(self, _=None):
        ble = self._source_is_ble()
        state = "readonly" if ble else "disabled"
        self.device_cb.configure(state=state)
        self.scan_btn.configure(state="normal" if ble else "disabled")
        self.piano_lbl.configure(
            text="Piano (BLE)" if ble else "Piano (USB - selected above)")

    def _selected_address(self):
        i = self.device_cb.current()
        if 0 <= i < len(self.devices):
            return self.devices[i][1]
        # Fall back to a saved address if the dropdown is empty.
        return self.cfg.get("last_address")

    def _selected_output(self):
        """Translate the output dropdown into what the controller expects:
        'virtual' for our built-in port, an rtmidi index for a real port, or -1."""
        sel = self.port_cb.current()
        if sel < 0:
            return -1
        if VIRTUAL_OUT_SUPPORTED:
            return "virtual" if sel == 0 else sel - 1
        return sel

    def on_connect(self):
        if self._source_is_ble():
            addr = self._selected_address()
            if not addr:
                messagebox.showinfo("Select a device",
                                    "Scan and pick your piano first.")
                return
            if self.port_cb.current() < 0 and not self.roblox_var.get():
                messagebox.showinfo("Select an output",
                                    "Pick a MIDI output port (e.g. LoopBe), "
                                    "or enable Roblox keystroke output.")
                return
            self._sync_settings()
            self.controller.connect("ble", -1, addr, self._selected_output())
        else:
            src_index = self.source_cb.current() - 1  # offset past "Bluetooth LE"
            self._sync_settings()
            self.controller.connect("midi", src_index, None, self._selected_output())
        self._save_config()

    def on_disconnect(self):
        self.controller.disconnect()

    def on_panic(self):
        self.controller.panic()

    def on_load_midi(self):
        path = filedialog.askopenfilename(
            title="Choose a MIDI file",
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")])
        if not path:
            return
        try:
            info = self.controller.load_midi(path)
        except Exception as e:
            messagebox.showerror("Could not load MIDI", str(e))
            self._append_log(f"MIDI load failed: {e}")
            return
        self.file_lbl.configure(
            text=f"{info['name']}  -  {info['notes']} notes, {info['length']:.0f}s")
        self._midi_len = info['length']
        self.time_lbl.configure(text=f"0:00 / {self._fmt_time(self._midi_len)}")
        self.play_btn.configure(state="normal")
        self._append_log(f"Loaded {info['name']}")

    def on_play(self):
        self.controller.play()

    def on_pause(self):
        paused = self.controller.pause_toggle()
        self.pause_btn.configure(text="Resume" if paused else "Pause")

    def on_stop_play(self):
        self.controller.stop_play()

    def on_record(self):
        if not self._recording:
            self.controller.record_start()
            self._recording = True
            self._rec_started = time.monotonic()
            self.record_btn.configure(text="■ Stop")
            self.record_lbl.configure(text="recording... 0s")
            return
        # Stop and offer to save.
        n = self.controller.record_stop()
        self._recording = False
        self.record_btn.configure(text="● Record")
        self.record_lbl.configure(text=f"{n} events captured")
        if n == 0:
            self._append_log("Nothing was recorded.")
            return
        path = filedialog.asksaveasfilename(
            title="Save recording", defaultextension=".mid",
            initialfile="recording.mid",
            filetypes=[("MIDI files", "*.mid"), ("All files", "*.*")])
        if not path:
            self._append_log("Recording discarded (no file chosen).")
            return
        try:
            self.controller.save_recording(path)
            self._append_log(f"Saved recording: {Path(path).name}")
            self.record_lbl.configure(text=f"saved {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Could not save recording", str(e))
            self._append_log(f"Save failed: {e}")

    def _raise_timer_resolution(self):
        """Windows defaults to ~15 ms timer granularity, which makes playback
        scheduling choppy. Request 1 ms while the app runs."""
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
            self._timer_raised = True
        except Exception:
            self._timer_raised = False

    def _start_hotkey(self):
        """Global F8 stops playback even while Roblox is focused, so the
        note-off keystrokes land in Roblox and release the held keys."""
        try:
            from pynput import keyboard as pk
        except Exception as e:
            self._append_log(f"Global F8 hotkey unavailable "
                             f"(pip install pynput): {e}")
            return

        def on_press(key):
            if key == pk.Key.f8:
                self.controller.stop_play()

        try:
            self._hk_listener = pk.Listener(on_press=on_press)
            self._hk_listener.daemon = True
            self._hk_listener.start()
        except Exception as e:
            self._append_log(f"Could not start F8 hotkey: {e}")

    def _on_tempo(self, _=None):
        pct = self.tempo_var.get()
        self.controller.play_tempo = pct / 100.0
        self.tempo_lbl.configure(text=f"{pct}%")

    def _auto_connect(self):
        # Auto-connect only the saved Bluetooth piano (USB ports may move around).
        if not self._source_is_ble():
            return
        addr = self.cfg.get("last_address")
        if addr:
            self.controller.connect("ble", -1, addr, self.port_cb.current())

    def bump_transpose(self, delta):
        self.set_transpose(clamp(self.controller.transpose + delta, -36, 36))

    def set_transpose(self, value):
        self.controller.transpose = value
        sign = "+" if value > 0 else ""
        self.transpose_lbl.configure(text=f"{sign}{value} st")

    def _on_vel(self, _=None):
        pct = self.vel_var.get()
        self.controller.vel_scale = pct / 100.0
        self.vel_lbl.configure(text=f"{pct}%")

    def _sync_settings(self):
        self.controller.auto_reconnect = self.autorecon_var.get()
        self.controller.remap_ch1 = self.ch1_var.get()
        self.controller.clean_output = self.clean_var.get()
        self.controller.play_to_output = self.play_out_var.get()
        self.controller.roblox.enabled = self.roblox_var.get()
        if self.roblox_mode_var.get() == ROBLOX_MODES[1]:
            self.controller.roblox.mode = "keyboard"
            if not self.controller.roblox.kbd_map:
                self.controller.roblox.set_keyboard_map(build_keyboard_map())
        else:
            self.controller.roblox.mode = "midiconnect"
        self.controller.loop_play = self.loop_var.get()
        try:
            ms = max(5, int(self.gap_var.get()))
            self.controller._ble_interval = ms / 1000.0
        except Exception:
            pass
        try:
            buf = max(20, int(self.buffer_var.get()))
            self.controller._ble_lookahead = buf / 1000.0
        except Exception:
            pass
        self.controller._running_status = self.pack_var.get()

    def _on_voice(self, _=None):
        if self.voice_on_var.get():
            program = max(0, min(127, int(self.voice_num.get())))
            self.controller.select_voice(program)
        else:
            self.controller.select_voice(None)

    def on_test_voice(self):
        program = max(0, min(127, int(self.voice_num.get())))
        self.controller.test_voice(program)
        self._append_log(f"Testing voice #{program}")

    def on_test_roblox(self):
        if not self.roblox_var.get():
            self._append_log("Tip: tick 'Send to Roblox' first, open your piano "
                             "game, then click Test.")
        self._sync_settings()
        self.controller.test_roblox()

    def _open_help(self):
        if getattr(self, "_help_win", None) and self._help_win.winfo_exists():
            self._help_win.lift()
            return
        win = tk.Toplevel(self)
        self._help_win = win
        win.title("Shelementyev's BLE-MIDI Bridge - Help & Setup")
        win.configure(bg=BG)
        win.geometry("680x620")
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        txt = tk.Text(frame, wrap="word", bg=PANEL, fg=FG, bd=0,
                      padx=14, pady=12, font=("Segoe UI", 10),
                      insertbackground=FG, spacing1=2, spacing3=4)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)

        txt.tag_configure("h", font=("Segoe UI Semibold", 12),
                          foreground=ACCENT, spacing1=12, spacing3=4)
        txt.tag_configure("b", font=("Segoe UI Semibold", 10), foreground=FG)

        def head(s):
            txt.insert("end", s + "\n", "h")

        def line(s="", tag=None):
            txt.insert("end", s + "\n", tag)

        self._help_link_n = 0

        def link(label, url):
            self._help_link_n += 1
            tag = f"lnk{self._help_link_n}"
            start = txt.index("end-1c")
            txt.insert("end", label)
            txt.tag_add(tag, start, txt.index("end-1c"))
            txt.tag_configure(tag, foreground=ACCENT, underline=True)
            txt.tag_bind(tag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            txt.tag_bind(tag, "<Enter>", lambda e: txt.configure(cursor="hand2"))
            txt.tag_bind(tag, "<Leave>", lambda e: txt.configure(cursor=""))
            txt.insert("end", "\n")

        head("What this does")
        line("It's a reliable Bluetooth and USB MIDI bridge for your digital piano. "
             "It connects your piano to your PC and routes what you play wherever "
             "you need it - into Synthesia or a DAW, to and from MIDI files, with a "
             "live visualizer and recording. And because it works over Bluetooth, "
             "it does something no other tool does: it lets a Bluetooth piano play "
             "in Roblox piano games like Piano Rooms and Visual Pianos.")

        head("Quick start (the short version)")
        line("1) Connect your piano (Bluetooth or USB) at the top.", "b")
        line("2) Tick 'Send to Roblox' and choose a Type (explained below).", "b")
        line("3) Open your Roblox piano game and keep its window focused.", "b")
        line("4) Play. Use the F8 key any time to release stuck keys.", "b")
        line()
        line("That's all you need for Roblox - you do NOT have to pick a MIDI "
             "output. (The output box is only for sending your piano to other PC "
             "software; see the Synthesia section further down.)")

        head("1.  Connect your piano")
        line("Works with any standard Bluetooth or USB MIDI keyboard - any size (25 "
             "to 88 keys), weighted or not, with or without pedals.", "b")
        line("Bluetooth:  set Source = Bluetooth LE, click Scan, pick your piano "
             "from the list, then Connect. Tick 'Auto-connect on launch' so it "
             "reconnects by itself next time, and 'Auto-reconnect' so it recovers "
             "if the link drops. Your piano must be in Bluetooth/pairing mode.")
        line()
        line("USB:  plug the piano into the PC with a USB cable, set Source = the "
             "piano's port, then Connect. USB is the most reliable option and the "
             "best choice for very fast pieces - Bluetooth has timing limits that "
             "no software can fully remove on some pianos.")

        head("2.  Choosing the Roblox Type")
        line("There are two ways games receive notes. Pick the one your game uses "
             "with the 'Type:' dropdown next to 'Send to Roblox'.")
        line()
        line("MidiConnect", "b")
        line("For games that support the MidiConnect protocol - Piano Rooms and "
             "Visual Pianos. Open the game, click its in-game MidiConnect button "
             "so it starts listening, set Type = MidiConnect here, tick 'Send to "
             "Roblox', keep the game focused, and play. This sends every note WITH "
             "its velocity, so your dynamics (soft/loud) come through, and the "
             "sustain pedal works. It's the same data the standalone MidiConnect app "
             "sends - so anything that works with MidiConnect works here, except now "
             "you can use a Bluetooth piano too.")
        line()
        line("QWERTY output", "b")
        line("For the many games that you'd normally play by typing letters on the "
             "keyboard (the 'Virtual Piano' style used by virtualpiano.net sheets "
             "and lots of Roblox pianos). Set Type = QWERTY output, tick 'Send to "
             "Roblox', focus the game, and play. Each note taps a letter or number "
             "key, sharps (black keys) are sent while holding Shift, and the "
             "sustain pedal holds the Space bar. The standard range is C2-C7; notes "
             "above or below it fold in by octaves so every key on your piano still "
             "plays something, and Transpose shifts a whole piece up or down. Note "
             "that most of these games don't respond to how hard you play.")
        line()
        line("Which one?  Playing Piano Rooms or Visual Pianos -> MidiConnect (it's "
             "richer: velocity and pedal). Any other piano game you normally play "
             "with letter keys -> QWERTY output.", "b")

        head("3.  The Test button")
        line("Click 'Test' and the app focuses your Roblox game and plays a C-major "
             "scale through the selected Type. Use it to confirm your setup is "
             "working before you start playing for real - if you see eight notes "
             "step up the keyboard in-game, you're good. If nothing happens, check "
             "the Troubleshooting section below.")

        head("4.  Transpose, Velocity, Voice")
        line("Transpose shifts every note up or down in semitones (handy to move a "
             "song into a game's playable range, or to change key). Velocity scales "
             "how hard notes are sent. Voice (in the play row) sends a sound/program "
             "number to a piano that has multiple voices. These apply to live "
             "playing and to file playback alike.")

        head("5.  (Optional) Send your piano to Synthesia / a DAW")
        line("This is separate from Roblox and most people can ignore it. It lets "
             "other music software on your PC receive your piano.")
        if VIRTUAL_OUT_SUPPORTED:
            line("This app can publish its own MIDI port. Choose 'Built-in port' as "
                 "the output and connect, then pick 'BLE-MIDI Bridge' as the input "
                 "inside Synthesia or your DAW - nothing else to install.")
        else:
            line("On Windows an app can't create its own system MIDI port without a "
                 "driver, so install loopMIDI (it's free), add one port in it, pick "
                 "that port as the output here, and select the same port inside "
                 "Synthesia or your DAW. This is the only reason you'd ever need "
                 "loopMIDI - it is NOT required for Roblox.")

        head("6.  Play MIDI files")
        line("Click 'Load MIDI...', then Play. The file is sent to whatever you've "
             "enabled at once - your piano, Roblox, and/or the MIDI output - so you "
             "can autoplay a song into a Roblox game, or play it on your real piano. "
             "Loop repeats it, the speed slider changes tempo, and Transpose / "
             "Velocity work here too. Use the time bar to watch progress.")

        head("Stuck keys & the F8 panic")
        line("If a note ever sticks in-game, press Panic, or just hit F8 - the F8 "
             "hotkey works even when this app isn't the focused window, so you can "
             "trigger it without leaving Roblox. It releases every held key and the "
             "sustain pedal. Stopping playback does the same automatically.")

        head("Troubleshooting")
        line("Nothing happens in Roblox:  the game window must be the focused/active "
             "window while you play, 'Send to Roblox' must be ticked, and the Type "
             "must match the game. Press Test to check.")
        line()
        line("First time using Roblox shows a 'pydirectinput' message:  the keystroke "
             "library isn't installed. Run  pip install pydirectinput  and restart "
             "(if you're running the .exe build this is already included).")
        line()
        line("MidiConnect type does nothing:  make sure you clicked the MidiConnect "
             "button inside Piano Rooms or Visual Pianos so it is listening.")
        line()
        line("QWERTY output plays wrong notes:  that game may use a different key "
             "layout than the Virtual Piano standard, or a non-US keyboard layout is "
             "interfering. Set your system keyboard to US English while playing.")
        line()
        line("Fast songs bunch up over Bluetooth:  this is a hardware limit of the "
             "piano's own Bluetooth, not the app - switch to USB for those pieces.")
        line()
        line("No MIDI output ports listed:  only matters for the Synthesia/DAW "
             "feature, not Roblox. Install loopMIDI (or use the Built-in port on "
             "Mac/Linux), then click Refresh.")

        head("Credits & thanks")
        line("The MidiConnect option talks to Piano Rooms and Visual Pianos using the "
             "MidiConnect protocol created by LordHenryVonHenry. Huge thanks to "
             "them - MidiConnect is what makes that connection possible, "
             "and this app would not exist without their work.")
        line("MidiConnect on GitHub:")
        link("https://github.com/LordHenryVonHenry/RobloxMidiConnect",
             "https://github.com/LordHenryVonHenry/RobloxMidiConnect")

        head("About")
        line(f"Shelementyev's BLE-MIDI Bridge  v{APP_VERSION}")
        line("Plays Bluetooth and USB pianos into Roblox and other music software.")
        line("Free software under the GNU General Public License v3 (GPLv3). You can "
             "use, study, share, and modify it; see the LICENSE file for the full "
             "terms.")
        line("Built on the MidiConnect protocol by LordHenryVonHenry (credited above) "
             "- this program contains none of its source.")

        txt.configure(state="disabled")
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 12))

    # -- config -------------------------------------------------------------
    def _load_config(self):
        self.cfg = {}
        try:
            if CONFIG_PATH.exists():
                self.cfg = json.loads(CONFIG_PATH.read_text())
        except Exception:
            self.cfg = {}
        self.set_transpose(int(self.cfg.get("transpose", 0)))
        self.vel_var.set(int(self.cfg.get("vel_scale", 100)))
        self._on_vel()
        self.tempo_var.set(int(self.cfg.get("tempo", 100)))
        self._on_tempo()
        self.ch1_var.set(bool(self.cfg.get("remap_ch1", True)))
        self.play_out_var.set(bool(self.cfg.get("play_to_output", True)))
        self.loop_var.set(bool(self.cfg.get("loop", False)))
        vsel = self.cfg.get("piano_voice", -1)
        if vsel is None:
            vsel = -1
        self.voice_on_var.set(vsel >= 0)
        self.voice_num.set(vsel if vsel >= 0 else 0)
        self.controller.piano_voice = vsel if vsel >= 0 else None
        self.clean_var.set(bool(self.cfg.get("clean_output", True)))
        self.gap_var.set(int(self.cfg.get("ble_interval_ms", 15)))
        self.buffer_var.set(int(self.cfg.get("ble_buffer_ms", 30)))
        self.pack_var.set(bool(self.cfg.get("running_status", True)))
        self.roblox_var.set(bool(self.cfg.get("roblox", False)))
        rmode = self.cfg.get("roblox_mode", ROBLOX_MODES[0])
        rmode = {"Piano Rooms (MIDI mod)": "MidiConnect",
                 "Virtual Piano / keyboard": "QWERTY output"}.get(rmode, rmode)
        self.roblox_mode_var.set(rmode if rmode in ROBLOX_MODES else ROBLOX_MODES[0])
        self.autorecon_var.set(bool(self.cfg.get("auto_reconnect", True)))
        self.autoconn_var.set(bool(self.cfg.get("auto_connect", False)))
        self._saved_source = self.cfg.get("source_name")  # restored in refresh_ports
        self._sync_settings()
        last = self.cfg.get("last_address")
        name = self.cfg.get("last_name")
        if last:
            self.devices = [(name or last, last)]
            self.device_cb.configure(values=[f"{name or last}   ({last})"])
            self.device_cb.current(0)

    def _save_config(self):
        i = self.device_cb.current()
        if 0 <= i < len(self.devices):
            name, addr = self.devices[i]
        else:
            name, addr = self.cfg.get("last_name"), self.cfg.get("last_address")
        port = self.port_cb.get()
        self.cfg = {
            "last_address": addr,
            "last_name": name,
            "last_port": port,
            "transpose": self.controller.transpose,
            "vel_scale": self.vel_var.get(),
            "tempo": self.tempo_var.get(),
            "remap_ch1": self.ch1_var.get(),
            "play_to_output": self.play_out_var.get(),
            "loop": self.loop_var.get(),
            "piano_voice": (int(self.voice_num.get())
                            if self.voice_on_var.get() else -1),
            "clean_output": self.clean_var.get(),
            "ble_interval_ms": int(self.gap_var.get()),
            "ble_buffer_ms": int(self.buffer_var.get()),
            "running_status": self.pack_var.get(),
            "roblox": self.roblox_var.get(),
            "roblox_mode": self.roblox_mode_var.get(),
            "auto_reconnect": self.autorecon_var.get(),
            "auto_connect": self.autoconn_var.get(),
            "source_name": self.source_cb.get(),
        }
        try:
            CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2))
        except Exception:
            pass

    def _on_close(self):
        try:
            if getattr(self, "_timer_raised", False):
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass
        try:
            if self._hk_listener:
                self._hk_listener.stop()
        except Exception:
            pass
        try:
            self.controller.stop_play()
            self.controller.disconnect()
        except Exception:
            pass
        self._save_config()
        self.after(150, self.destroy)


def main():
    try:
        App().mainloop()
    except Exception:
        err = traceback.format_exc()
        try:
            (Path.home() / "ble_midi_bridge_error.log").write_text(err)
        except Exception:
            pass
        try:
            import tkinter.messagebox as mb
            mb.showerror("Shelementyev's BLE-MIDI Bridge crashed", err)
        except Exception:
            print(err)


if __name__ == "__main__":
    main()
