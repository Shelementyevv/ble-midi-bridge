"""Regression tests without a GUI, Roblox, or injected keyboard input."""

import queue
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ble_midi_bridge_gui import App, RobloxKeySender, build_keyboard_map


class FakeKeys:
    def __init__(self):
        self.events = []

    def keyDown(self, key):
        self.events.append(("down", key))

    def keyUp(self, key):
        self.events.append(("up", key))


class RobloxKeySenderTests(unittest.TestCase):
    def setUp(self):
        # Exercise the real initializer without starting its infinite worker.
        self.logs = []
        with patch("ble_midi_bridge_gui.threading.Thread"):
            self.sender = RobloxKeySender(self.logs.append)
        self.sender._pdi = FakeKeys()
        self.sender.mode = "keyboard"
        self.sender.enabled = True
        self.sender.set_keyboard_map(build_keyboard_map())

    def send_note(self, note, velocity=100, channel=0):
        self.sender._kbd_message(bytes([0x90 | channel, note, velocity]))

    def release_note(self, note, channel=0):
        self.sender._kbd_message(bytes([0x80 | channel, note, 0]))

    def drain_worker(self):
        # End deterministically once the actual worker has drained its queue.
        original_get = self.sender._q.get
        def get():
            try:
                return original_get(block=False)
            except queue.Empty:
                raise StopIteration
        with patch.object(self.sender._q, "get", side_effect=get), \
                patch.object(self.sender, "_focus_roblox"):
            with self.assertRaises(StopIteration):
                self.sender._run()

    def test_key_stays_down_until_note_off(self):
        key, _ = self.sender.kbd_map[60]
        self.send_note(60)
        self.assertEqual(self.sender._pdi.events, [("down", key)])
        self.release_note(60)
        self.assertEqual(self.sender._pdi.events,
                         [("down", key), ("up", key)])

    def test_zero_velocity_note_on_releases_key(self):
        self.send_note(60)
        self.send_note(60, velocity=0)
        self.assertEqual(self.sender._pdi.events[-1],
                         ("up", self.sender.kbd_map[60][0]))
        self.assertFalse(self.sender._kbd_held)

    def test_sharp_does_not_leave_shift_down_or_release_other_chord_note(self):
        sharp_key, _ = self.sender.kbd_map[61]
        white_key, _ = self.sender.kbd_map[64]
        self.send_note(61)
        self.assertEqual(self.sender._pdi.events,
                         [("down", "shiftleft"), ("down", sharp_key),
                          ("up", "shiftleft")])
        self.send_note(64)
        self.assertEqual(self.sender._pdi.events[-1], ("down", white_key))
        self.release_note(61)
        self.assertIn((0, 64), self.sender._kbd_held)
        self.assertNotIn(("up", white_key), self.sender._pdi.events)
        self.release_note(64)
        self.assertFalse(self.sender._kbd_held)

    def test_shared_physical_key_waits_for_last_channel(self):
        self.send_note(60)
        self.send_note(60, channel=1)
        before = list(self.sender._pdi.events)
        self.release_note(60)
        self.assertEqual(self.sender._pdi.events, before)
        self.release_note(60, channel=1)
        self.assertEqual(self.sender._pdi.events[-1],
                         ("up", self.sender.kbd_map[60][0]))

    def test_octave_folded_notes_wait_for_last_release(self):
        # MIDI 24 is folded into the bottom of the default layout (MIDI 36).
        self.send_note(24)
        self.send_note(36)
        before = list(self.sender._pdi.events)
        self.release_note(24)
        self.assertEqual(self.sender._pdi.events, before)
        self.release_note(36)
        self.assertEqual(self.sender._pdi.events[-1],
                         ("up", self.sender.kbd_map[36][0]))

    def test_note_off_uses_original_key_after_mapping_change(self):
        key, _ = self.sender.kbd_map[60]
        self.send_note(60)
        self.sender.set_keyboard_map({60: ("z", False)})
        self.release_note(60)
        self.assertEqual(self.sender._pdi.events[-1], ("up", key))

    def test_repeated_note_on_restrikes_key(self):
        key, _ = self.sender.kbd_map[60]
        self.send_note(60)
        self.send_note(60)
        self.assertEqual(self.sender._pdi.events,
                         [("down", key), ("up", key), ("down", key)])

    def test_unknown_note_off_does_not_release_a_key(self):
        self.release_note(60)
        self.assertEqual(self.sender._pdi.events, [])

    def test_pedal_still_holds_space(self):
        self.sender._kbd_message(bytes([0xB0, 64, 127]))
        self.sender._kbd_message(bytes([0xB0, 64, 0]))
        self.assertEqual(self.sender._pdi.events,
                         [("down", "space"), ("up", "space")])

    def test_panic_releases_keyboard_notes_even_after_mode_change(self):
        self.send_note(60)
        self.sender._kbd_message(bytes([0xB0, 64, 127]))
        self.sender.release_all()
        self.sender.mode = "midiconnect"
        self.drain_worker()
        self.assertIn(("up", self.sender.kbd_map[60][0]),
                      self.sender._pdi.events)
        self.assertIn(("up", "space"), self.sender._pdi.events)
        self.assertFalse(self.sender._kbd_held)
        self.assertFalse(self.sender._space_down)

    def test_midiconnect_panic_sends_pedal_off_with_no_held_notes(self):
        self.sender.mode = "midiconnect"
        self.sender.release_all()
        self.sender.mode = "keyboard"
        with patch.object(self.sender, "_press_keys") as press_keys:
            self.drain_worker()
        press_keys.assert_called_once_with(bytes([0xB0, 64, 0]))

    def test_failed_sharp_press_releases_shift_and_is_not_tracked(self):
        original_down = self.sender._pdi.keyDown
        def down(key):
            if key != "shiftleft":
                raise OSError("simulated input failure")
            original_down(key)
        self.sender._pdi.keyDown = down
        self.send_note(61)
        self.assertEqual(self.sender._pdi.events[-1], ("up", "shiftleft"))
        self.assertFalse(self.sender._kbd_held)
        self.assertEqual(len(self.logs), 1)

    def test_failed_note_off_remains_tracked_for_panic_retry(self):
        self.send_note(60)
        original_up = self.sender._pdi.keyUp
        self.sender._pdi.keyUp = lambda key: (_ for _ in ()).throw(OSError("failed"))
        self.release_note(60)
        self.assertIn((0, 60), self.sender._kbd_held)
        self.sender._pdi.keyUp = original_up
        self.sender.release_all()
        self.drain_worker()
        self.assertFalse(self.sender._kbd_held)

    def test_failed_panic_release_remains_tracked_for_next_panic(self):
        self.send_note(60)
        original_up = self.sender._pdi.keyUp
        self.sender._pdi.keyUp = lambda key: (_ for _ in ()).throw(OSError("failed"))
        self.sender.release_all()
        self.drain_worker()
        self.assertIn((0, 60), self.sender._kbd_held)
        self.sender._pdi.keyUp = original_up
        self.sender.release_all()
        self.drain_worker()
        self.assertFalse(self.sender._kbd_held)

    def settings(self, enabled, mode):
        def var(value):
            return SimpleNamespace(get=lambda: value)
        app = SimpleNamespace(controller=SimpleNamespace(roblox=self.sender))
        for name in ("autorecon_var", "ch1_var", "clean_var", "play_out_var",
                     "loop_var", "wait_var", "pack_var"):
            setattr(app, name, var(False))
        app.roblox_var = var(enabled)
        app.roblox_mode_var = var(mode)
        app.gap_var = var(15)
        app.buffer_var = var(30)
        App._sync_settings(app)

    def test_disabling_output_queues_key_cleanup(self):
        self.send_note(60)
        self.settings(False, "QWERTY output")
        self.assertFalse(self.sender.enabled)
        self.drain_worker()
        self.assertFalse(self.sender._kbd_held)

    def test_changing_mode_queues_key_cleanup(self):
        self.send_note(60)
        self.settings(True, "MidiConnect")
        self.drain_worker()
        self.assertFalse(self.sender._kbd_held)

    def test_initial_settings_do_not_queue_panic_or_focus_roblox(self):
        self.sender.enabled = False
        self.sender.mode = "midiconnect"
        self.settings(True, "QWERTY output")
        self.assertTrue(self.sender._q.empty())


if __name__ == "__main__":
    unittest.main()
