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
from collections import deque
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
APP_VERSION = "1.1"

# Embedded app icon (128px PNG, base64) for the window/taskbar icon at runtime.
ICON_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAX7klEQVR4nO2deZRc1X3nP797X1VX9SJ1a22NNmuBGDBaECDGTiw7ycR4kxhDgxmYMUvG44xjBzDEB+wJYOwIMCGxfM6MF3wSG+IklrHj8fFg7GSMJjEggUDgACYGWXtraXX1Vt1Vb7m/+eNV9aLeqrpb2FG9zzl1pKp+9/3uffd77/3d9QnTx0CbwPao/MPClWsWSNFsUKMbRc06RFcp2opKowh1gMyA3TMRRWQAMTkROSjIS8amnjZ1mScPvvLEy6qudFmbhe0KuIluVgnTyYgRGT9v2YZFKaL3KmxG2SgiCxADqoDG/6DTje8ZiYgBEdRFuChAXQA6lLfOuQFgD/A9Q+bREydeeS3+yxXTFsJUBCDQZsoZv2jZBRtU3X8H+YAxplkBVQeqGqdCynbKn4QSIgaA0M/jogCvroHsrMVkm5dopnGh2vQsFRGJgn7j95+k0HOIfOeBQrHv6Hd6Og9/IYRdiIG3/5bHjh3hlOJQ5fWGktpal68/B8enRfSDItY45wBXagbETOHetYMIgiEs9oIYmhevY+HZv8fc5ZdQ37KSVKaOUqUAgCqqikYBbqBrv9d95HmOvvq4dvzyyW8eO/ziXcBrqioiIlRZG1SRSZs82BHCuenWZZnbwf2xEVvvXARoCGKru19tIsbiwiJRUGDeyrezYuONzF3+Vrw0uDAuQs65UtM5PKAgYjAWtSmcizC9x34h+3Y/3HPw+W/e3XH89QfjJvdyO9wfmzQ+lV0WZ/6CJeefb8R7yBh7sXMhoFEp4xMqQIxHWOwm3bCQN7/zNhafvxkRCH1QF5UyeaKWUgerA0Tw6kxoDN7Jfc/z6hMP/uhfn33kv4IcYNPbK24SKhBAnPkLl665yoj9KiJN6qKkxFeJGI9gIEfL0o2s3Xw/jXMX4w84UBBjpnTPsq+VqrdRVAy8V/7hviN7Hvsf10bwEzZtqkgEk2RgnPmtS9bdKsZ8HhyqSamvFjEe/kAnC8++lPWX/TnGSxP5EWJm5jGqizCeDb003s//cVvwsx/dcX0+n//roWZ7griN/6fBzP8TY+3dzkURsROYlPoqEGMJCt3Me9PbufCqLwMeLnRTLvXjooqKunTWyMuP/5m8/OO7PtI30Pdl2JCC3cF4wcaJxVDJjzM/DEkyv2pEDFHQT8OcVay77EFETlPmx8YQFRP0R5zzu5+I3nThdV9qapp9Q5z5m7zxgo0RkzYLO8LWZevaxJrPu6S9nzKKAsJbLv1T6hpnEwVRVZkvUuVDF0ERcRHmvHfdEzW3rvva3Lkr3h83A21jtjenxsbA9qh12bpzReUvVZ0jKflTQowlGOhm6dqrmb/qAoKB6tp8AfwAIh0aD6gonBiiIJJsS7Os/s2bFSvfXLrqneeVuoaj1Df8B4E2Offcc9MojyDSEPc3xmsmEsZHcFFAXeN8Vmz8MFGgpe5d5YQOli2AbBqCEEw1IjCWYMCZxedvcXOWXNhY6Duyfc2aaxvgzjhywxiWufHwbmdP+nZjvPWqg1V/QpWIMYTFPhad8z4a5y0gClxpcHRijMSl3Rgo+HDtO+COK8Ea8KPqRKBO8dLYpWv/U4joOR3dP/8C3O3ifB5mc+jf7W7x4nVnIXK7c2HS1ZsGqg6byrDonM24Cutwp5AvQDEYEkJfAVa1xiJI2epEIMYQ+jBv9Tu9usaFoYuCG1uXX/juuCkY8gdKAmgTQCPhs8aYutKsXdLuTwUxuKBAw9zVzGo9lyiQwUmfiTACH3kPXPIb0J2PS71nIYzgvGXw6avAM1AIKvUJBBc5sk2zmLP0YhMF/SrwxUWLNtSXZhAF4ildC9uj+YvXrUXkcucil5T+qSMiRFGR5kVrSWW8eIh3ouuJS38mBRtWw81b4KKzYxFk09CVh23fh9WL4FNXQUsjRK5CEagiRmlZcpFxLoyMsaucF/0RMNgUDErTCjcZY+yIieiEqaFK04I3V5RJSlzaewfg9q/D0RzcfgVcsDpuEkTgX/bHgviNxTB/VlwrVIQILhIa55+N9TLWRYETuHXRog3zYLsjdje2RwtXrlmAcLlzTpPSP01UMcYjO3tJPKFXiQgU6tLQ2Qt3/y0c64J7roGVrZD2YOuHoKkePvM38PLBuLY4dbJwLARBHWQaF2LTjeJc6Izx5qiN/gBQ2BSPSpiibDHGayrN5ydt/zRQFLEpUplZpbq0ssfpHNTXwckeuOdv4Vg3LGyGpmzcFNy7HV74ZfzdVbGwShVsugGbyoI6o+pUhQ/HvsCO0ACokS1asV4TJkTjwRgxqaqDhi7O4P0n4KHH4+8A33kS/unlofa/Ykq5KcZi4kEoo+qcNXaJGncpgFm0aMM8RS9RdVJRZzVhYoTBtX3V4hno6Y+r/j94T/wdoO034bfXQGdf7C9UTKmmUBfhhpzReNWeuKsBjJroYiNmbmnUL6kBpokgOBcSFrpLxamy+toY6C9Cawv8yQdhVj20d8aCyPXBbR+Ai1bHzmJVo4ICYbGPKOhHYvfOOnUCbFqy5JI5Ro1ujGOaeP8zggjqQvq7D8a9gAry30g88jd/Ntx5NTQ3wqcfhn3HIYjgjm/E3cFPXRWPCQwElYkg9keg2HeMyM+X5yIEVTXGzA+k+DaDsjZp/mcWEaH3+CsVeupxt25WPdz7obid/9zfwc/2Q0MmduIuPjv+/cV9cTcxZSvrBcQ9EqX3xKtEYWHY4IE6xCDob3kismpYXBKmiarDeHV0t79IMBAi1puwFlCGxv7/6SX4lwOwZy/MroeBIjQ3wEfeHY8F3Pvt2AlMexUKQAR1Qu7QM6eMRoqgCsoGo2hr3PwnApgRVDFehr6Tr9N99GfYlKIVtK6q8LUfw3OvweyGOKMjFw8H79kLW7eXxgsqzXwUYw0DPd3kDj6DTdUTz+4DsasKsNKg0pSM/c8sIgYXFml/6XsYIxXlmAg0ZiCdivv5qpCtg1cPw32Pxr+lbOVjAOocXhqO/+LHDPQcwXhphlVFEq8sZp60Ll3nSDJ/hpG4mbVp3nrd96hvbiUKtaJJoTJOobU57gEM+HG1X/kAkJY+jqcfvpLe4z/HprJj1UQuWe1zWlDEevgDJ9n79JewqcpqgeEYgcOd4IeQqirz49KfyhgOvfhduo68gE3Xj9cMnY7ViQkQD76kM7M59OK3OPavO0ll7aQzg6eS9mIhVKOdeC2CJX/yOK/981/gpRsm9EESAZxWBBHLS4/fQaG7E5uywx2xSYkd9SpQRURBlJ89dgfF/Im47Z9AQYkATiPllUEDXQd5/u//CBcVMSlTlQgqtxVnvJexvPT4Zznx+v8llZk9aa2TCOA0oy7Cy8ym88BT7P72R3FBP16dQd2UdnOPa8NYwUsbXnrsXvbv/ivS9XMqspEI4A1AXUgq20LH3ifY+c0P0XdyH+n6uENfrV8w4r7qUBeRylqioJfnvnMLv9z1FdLZlorvK61L1yXHdrxBxLuDe0llmjl70y0sXXclxoOwWPnu4PjcDQUxeGlBDBz/xT/zyj9upe/Eq6SyzVWJKhHAG4yIxTmf0O9n7rJLWLHxBuat2EQqY+OzAcJ4SbeWtoLHgUAwiBGMBeNBFELX4T3se+brHP35DxEjpdG+6mqURAC/CkqHPYTFPlSV2a3nseCs32Xum95K49xVpDJNmFM247kIwmKRga79dB7cxfFf/AOdB5/FhUVSmVkAFQ05j4pKIoBfHeWRwSgYIAoL2FSWTFMr2dmLqWtYgFfXBAhRkKeY76DQc4RCTztBsRdjPWyqATFmWn5EIoBfAwZPCVMXHwQU+aiLSmt04ullEYtYD2PT8by+VjbJNBnjbhtOeOOIT/qI/y82hWfToxf+65BfMJ0SfyqJAH7dGMzoN8ZcMg5Q4yQCqHESAdQ4iQBqnEQANU4igBonEUCNkwigxkkEUOMkAqhxEgHUOIkAapxEADVOIoAaJxFAjZMIoMZJBFDjJAKocRIB1DiJAGqcRAA1TiKAGicRQI2TCKDGSQRQ4yQCqHESAdQ4iQBqnEQANc6UdwdbW9m7paJooq3MijF2zNeqOudK+9/HOi8nPt5+sjjE94hf22oqOBPTORcf4Tbm674mtjmtdE7R5oh7VHkSaZkpCUBE6O7uIYqiUqJGG1cFYwxNTU3jvjdXRMjn+/D9YNh9BFUlm82QyWTHFIGIEIYh3T25cY5Tiu/R0FBPOp3G933y+f5x41q+PpPNkB3XJoRRRHdupM04nUJT06xJ0pnH9/1R6cxkMmSz49uMoohcLjfmfUFwqjQ21JNKpaYkgqoFICIUi0WuuOIy3rHpEoJQkVMiroARIQwDtm3bxv59+/GGRdCIoIBnLTff9DFWrlxGsRiLyTlHfTbFT5/cxV8//A1sKlU6NCl+PMZaioUBLt54Cddd91/w/XDEg1cUayzd3Tke+tojHD50mMVLFnPDDdfQ0txC5Nyo+JZtPvnUMzzy8Nex3lg2C1x08UVcf/11I21KHP6L277IL/fuHZVOBIwYPv6xj3LWWStGpfPpnbv5xtf/Cms9VEfb3HDhBm648XoCPxojnYae3h4eeuhh2tuPkk6nqxZBVQIwxpDP57lk40V89Sv3Y2AwwiMeaOnGew8c57ZbbyIIfJwrjoic53l0dXSwqHUe//nqyyhG8XHooYO0gV3P7KKnq52m5vmE4dCBhyKGQmGA9iP7ufLKLdR5sb3hcYgUUgKrV5/F5Zdfw9133cHlW36HQMGOUUiDCOos7H5uNz25sWwKhUKBI4f3c8UVW8imY5taSueBI5188rabCfx+nLOj0tnbdYIF85tHpLNsc88LL9CTOzKmzWKxyJHD+7n8A5fRmIFT3+lXTufZZ53NNdfeWGEujqQqAYgIvh+wfPkyVJXjJ/vxvNG3cM6RrU/T2ZkrVZF2VPUbH5Bk6e7uJowicrkCnucRRREtzXXk8/2AF7+Cbdgx6yKCsR5BENLR0UN9fXZYUzRkP5NJs2LFcubMncPixf+OfDEin/fH9AXCMGRuS2Zim6Zss4vGxgaiKCo1VUPpFGNL4U5Np0d3d8+IdA7ZzFeQzk6C2bMIw1NqO1XS6RQrViynqamJQqGAtbaqWmBKTUA5Ip7njemgiMSOy9DfxnsnkQ5eN/x6z9pSRo2TkJJj53lDYYY/mPLfgiBEVQnDcPDasQSgqpPbZLRNVR0jnWOHPTWdFdk8JZ1lh3ZEvD1LGIZTdgKn1A0cz9n5daMcz38r8Z0q00lfMg5Q4yQCqHESAdQ4iQBqnEQANU4igBonEUCNkwigxkkEUOMkAqhxEgHUOIkAapxEADVOIoAaJxFAjZMIoMZJBFDjJAKocRIB1DiJAGqcRAA1jke8x+G0CWH4su0wDLHWDi4pH2tPQZnh15T33ZXDRlFU0V6/qhlhM976UYlN1ThunudhjKkqnRPZdM6dnnQOi7oH9AONM3/reCdRd3c3GvYDabKNDfR29QARSAq0P17rPjxY6XsYhoRhP50nOvDqUogIQSFPrNUifX1zMGbmlnsL4Ca12TzKZpz5hp6eboJCD1BXSmcvEA6m0zk3amfE2DYNQaFvmM0mjDHx62RnGFWKHkoHRhpLOwtm5IkaYygWQ5YtW8LnH3iAQwf309s3wKOP/j1XXvlBFiyYhx+EpKzl3e95D30FN1hTGGMYKDp+/8YbaazP0tCQ5bEf/gQ/8Nn8vt+j6EcEvs+6Cy6gvj6Df8qeuanGt7/ouP6GG8jU1dHQkOGHP3qCQqHA5ve/C993BH6RtevX09hQjx9EpTd6C74fsnjxIu6//wH27dvLwECRb23/LpdfcSWLFi0g8EOMMbx/8+ZR6cwXHddddx2plEdDfYYf/XgH+f5+tmy+FD9wBMUia9aupampgSCYfjqHoSCCuF4P2CvIm5SZE0AZEcvHP/5hUgKv7+/gB//nCW697ZO85c1LiAAL9BUYsdnSGEOh6Fi77nwuvngrFjh+skBvby9bP3cnIXG7FQK9veGMPJSyzTVrzuOiC/8UC3R2BZw82cm9FdhUNXz0D28kJXDgSBff/8FPuOWWT7D+/JUTprNYdLzl/HN58MHYZnfvXbQfbefez905GG4m0zk8yiIIKkc9FX1ORH47rgFmdgeNqpLLDZDNpsjlcqg6urpy9BVaB/fpldu74YjAwIBPT0/AvOY6isUCvl8kCENOdhUHw1R6RkEljLY5gO8X8cOQzi4fa80ENpVcrkAm4w1LZxf5YkhfXzXpHMD3ffwwJNcdh5vpdJbiq2BA3V4D5v8R700/Ld5G2TkqJ6L8vfwZT9nGmBHXDHeoxtuTOF1G2jRV2ZyZdFZnc1qIoMIeYyPvSefciQlOT0g44xCDOsTJTnPkyDMngR1GjIJOdM5JwpmBIiJOXYc4+4wBEDV/Q+wAnNnbaBMAdUaMCrKzvX13RywAZ34YueiwiDHEA0MJZzQionwXwMAmr719d78oXxYxQuwRJpyZKBjjXNjrAvd9AAM7HCAS2f/lXNQJEx6TkfBvGo2MMYLy6LFjLx6HNluq8ttMe/vuDoUHjDEmcQbPVMQ45yKn8uflX0p9/+0OMCnN/IWLotdFrCXxBc4wNDLGGlS/ffzw8y9Cm4XtUXnwR6FNDh16egDlY/EYVeILnEEoCM5FBQ/5NCCwXWHENPD2CNrs0cN7HtMofMiYlAcajnm3KZxIVQ4ztbCJzUpsTnBFZIxnUbYeOvT8a9A22Ns7ZaJ6u4M7jYbfvSky4duM2HNUowhkcDxSNT78UNWNOp9vlFlAnRucSy+PiUdRFJ9vy8QDD+XrrDW/Ipvx0WyxzfHDxDZ1BtOpk5w9XPLSdcjm+M9EIxHrRVH43JKFduvRQ2221OQDo88JVLhbjh0jv3Dp2jZUnxYxDRofZGtUlVTKcqS9HU8MLS31E0YyThxkU9DXl6crl+PkyU4a6izGWCYb5lZNYwzkOnPkurowYpjTUj9pF6VsM5/P05XroqPjJPVpi0jlNjs7cxw/fgIrwpw5WSYrZEM2++nK5eg42Vm9zVyOY8eOY0RoaZncpnOQ8eJn29/fj+eNOi/YISKo5sXKtbt37w5g94he3lhLVRy02WMHt7+0cNmaqw3e90v+gDrnpKGhgSef3MUnP3U/l77rHfi+m7BExjNeeb6w7StYa7nr7q309/8hs2c349z4ZUNR0inDT598lp27niUIAm674z7efek7J7dpoDDQz7ZtX8Vay2fuuY9CoZ/mlmZcNJlNy1NPPctTT++i6Pt84pNbee97f6eidBaL/Wz74kMYY/nsZ+/DLw7QMmcOLhrv1PMhm0/vfI6f/vRpCoUCt/zx53j/+/4DfjD6XONTbfr+AF/Y9lXCMCKdTpeeaenW4ATjqXPXHT2455Wy4zfiHuPenU0e7AgXLllzg7Gpr6mLImKfQSBWXXmKdDxUS6dshxGplEc2m6VQKOD7Qal6HeeU9GHhwzCksbEBEanapud51NdnKRSK+L4/ZZvGmvjg5yptFn2fVJU2jTH09vaVmpLKbWazmeGlX0vtvuei6Najh/b8WTk/T73PJGP/caDWpWv/m4j9kqpTyqfiVnEmrUgcKl7jJqVaqaKgg+vxgKrOwR1uMz7r98y3WUIBZ4y1LoruPHpoz2fGy3yoaPInDrxgydprrMhfIpJSdSHIlF82kXC60EjEWBDUuduOHtrzwESZDxXP/pWag8Vr3yHWPGLELHYuDEu9g2QG8VePgkZirIdqr1P3+8cOvvCtyTIfKl4OviOETd6xwy88YUL/3zsXPW6M5wEy3lhBwhuFRoAYk/Jwuity4dsqzXyouvQOeZGtS9ffDNxljJnlXKRxT0EGncSE00pp8Y54xlicRv3A/UcP+FvhZb/SzIepZVa5H6nzl563yiN1JyLXiBjjXERcIwwKIRHDzKFDw/PGGmNQjZyq/B2Ge47uf/6V0nVVremYRgYN1QYLl6y9WMTcBPofjfEyquU3fuGGOiyJIKpAhz4KxKtFRUy8mcS5LtDviJj/2X7gud1xkMERvqrGkqebIQbapCyE+Us3rDLiLhdli6LrjZgsUk5GqQeZUAFSGjeQwXk5VT2OsFPgfwfYH3Qc2N0eX9tmSxM7U5q8m6kSOUIIAK3L158jqm9TlY2g5wHLFG0RJEOyKXU8VJUior2CHAVeV/QFMbJTC253vIijzPQyvsz/B3JE+qrNi34nAAAAAElFTkSuQmCC"

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
                    if len(self.sysex_buffer) < 4096:  # cap: a lost EOX can't grow it forever
                        self.sysex_buffer.append(byte)
                    pos += 1
                continue
            if not (byte & 0x80):
                # Running-status data with the timestamp byte omitted - the
                # spec allows this for messages sharing the previous message's
                # timestamp, and many pianos pack chords this way. Without
                # this branch, every note after the first in such a packet
                # would be silently dropped.
                if self.running_status:
                    k = _channel_data_bytes(self.running_status)
                    messages.append([self.running_status] + list(data[pos:pos + k]))
                    pos += k or 1
                else:
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


def pick_hand_tracks(tracks):
    """Given load_midi's track dicts, guess (right_idx, left_idx) when a file
    has exactly two note tracks - the standard piano layout. Higher average
    pitch = right hand. Returns None when the guess doesn't apply."""
    if len(tracks) != 2:
        return None
    a, b = tracks
    return ((a["index"], b["index"]) if a["avg"] >= b["avg"]
            else (b["index"], a["index"]))


class RobloxKeySender:
    """
    Sends MIDI notes/sustain into a Roblox piano on a private worker thread.
    Two output modes:
      - "midiconnect": Piano Rooms numpad protocol (note + velocity + sustain).
      - "keyboard":    Virtual Piano style, where each note holds a letter/number
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
        self._kbd_held = {}           # (channel, MIDI note) -> (key, sharp)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- public API (called from other threads) -----------------------------
    def send(self, msg, force=False):
        if (not self.enabled and not force) or self._failed:
            return
        high = msg[0] & 0xF0
        if high not in (0x80, 0x90, 0xB0):
            return  # only notes + pedal matter; skip bend/aftertouch/etc early
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
        self._q.put(("release_all", self.mode))

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
    def _key_hold(self, key, shift, down):
        # Shift selects a sharp at the key event; release Shift immediately so
        # a held black key does not turn subsequent white keys into sharps.
        try:
            if shift:
                self._pdi.keyDown("shiftleft")
            if down:
                self._pdi.keyDown(key)
            else:
                self._pdi.keyUp(key)
            return True
        except Exception as e:
            self._log(f"QWERTY key event failed: {e}")
            return False
        finally:
            if shift:
                try:
                    self._pdi.keyUp("shiftleft")
                except Exception:
                    pass

    def _release_keyboard_notes(self):
        keys = dict(self._kbd_held.values())
        for key, shift in keys.items():
            if self._key_hold(key, shift, False):
                self._kbd_held = {note: km for note, km in self._kbd_held.items()
                                  if km[0] != key}

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
        identity = (msg[0] & 0x0F, msg[1]) if len(msg) >= 2 else None
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
                # A repeated note-on is a new strike, but octave-folded notes
                # sharing a PC key must not release each other prematurely.
                if identity in self._kbd_held:
                    old = self._kbd_held.pop(identity)
                    if not any(v[0] == old[0] for v in self._kbd_held.values()):
                        self._key_hold(old[0], old[1], False)
                if self._key_hold(km[0], km[1], True):
                    self._kbd_held[identity] = km
        elif high in (0x80, 0x90) and len(msg) >= 3:
            km = self._kbd_held.pop(identity, None)
            if km and not any(v[0] == km[0] for v in self._kbd_held.values()):
                if not self._key_hold(km[0], km[1], False):
                    self._kbd_held[identity] = km  # allow panic to retry
        elif high == 0xB0 and len(msg) >= 3 and msg[1] == 64:
            self._set_space(msg[2] >= 64)

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
                    self._release_keyboard_notes()
                    self._set_space(False)
                    try:
                        self._pdi.keyUp("shiftleft")
                    except Exception:
                        pass
                    for note in sorted(self._held):
                        self._press_keys(bytes([0x80, note, 0]))
                    if item[1] == "midiconnect" or self._held:
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
        self._timeline = []       # [(abs_seconds, track_idx, message_bytes)]
        self.track_info = []      # note-bearing tracks (dicts from load_midi)
        self.track_filter = None  # None = play all tracks; else set of indices
        self.wait_mode = False    # practice: pause until the user plays the notes
        self._wait_pending = None # set of note numbers currently being waited on
        self._tick_events = []    # (abs_tick, track_idx, bytes) for sheet export
        self._ppq = 480
        self._timesigs = []       # (abs_tick, numerator, denominator)
        self._tempo_bpm = 120.0
        self._key_fifths = None   # from the file's key_signature meta, if any
        self._keysigs = []        # every key change: (abs_tick, fifths)
        self._markers = []        # rehearsal marks: (abs_tick, text)
        self._tempos = []         # tempo map: (abs_tick, bpm)
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
                            raise RuntimeError(
                                "No BLE-MIDI notify characteristic.") from None
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

        # Wait-for-notes practice: a live Note-On satisfies a waited note.
        wp = self._wait_pending
        if wp is not None and high == 0x90 and len(msg) >= 3 and msg[2] > 0:
            wp.discard(msg[1])

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
            for (ch, _note), out_note in list(self.active_map.items()):
                self._safe_send([0x80 | ch, out_note, 0])
            for ch in range(16):
                self._safe_send([0xB0 | ch, 123, 0])  # all notes off
                self._safe_send([0xB0 | ch, 64, 0])    # sustain off
        self.active_map.clear()
        self._last_cc.clear()
        self.emit("clear")

    # -- MIDI file playback (PC -> piano) -----------------------------------
    def load_midi_async(self, path):
        """Parse the file on a worker thread and report back via the event
        queue ('midi_loaded' / 'midi_load_failed'), so a large file can't
        freeze the UI."""
        def work():
            try:
                if str(path).lower().endswith((".musicxml", ".mxl", ".xml")):
                    info = self.load_score(path)
                else:
                    info = self.load_midi(path)
            except Exception as e:
                self.emit("midi_load_failed", str(e))
                return
            self.emit("midi_loaded", info)
        threading.Thread(target=work, daemon=True).start()

    def load_score(self, path):
        """Convert a MusicXML/.mxl score to MIDI and load it for playback.
        Returns (info, mido_file) so the caller can offer to save the .mid."""
        import tempfile
        mid = musicxml_to_midi(path)
        tmp = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
        tmp.close()
        mid.save(tmp.name)
        info = self.load_midi(tmp.name)
        info["name"] = Path(path).name
        info["converted_from_score"] = True
        info["temp_mid"] = tmp.name
        return info

    def load_midi(self, path):
        """Parse a MIDI file into an absolute-time timeline that keeps each
        event's track, applying the file's tempo map manually (mido's merged
        iteration is equivalent but discards track identity, which the
        track/hand filter needs)."""
        import mido
        mid = mido.MidiFile(path)
        ppq = mid.ticks_per_beat or 480
        raw = []                       # (abs_tick, arrival_seq, track_idx, msg)
        seq = 0
        for ti, track in enumerate(mid.tracks):
            t = 0
            for m in track:
                t += m.time
                raw.append((t, seq, ti, m))
                seq += 1
        raw.sort(key=lambda e: (e[0], e[1]))

        timeline = []                  # (abs_seconds, track_idx, bytes)
        tick_events = []               # (abs_tick, track_idx, bytes) - for sheet export
        timesigs = []                  # (abs_tick, numerator, denominator)
        stats = {}
        tempo, cur_tick, cur_s = 500000, 0, 0.0
        first_tempo = None
        key_meta = None
        keysigs = []
        markers = []
        tempos = []
        for tick, _seq, ti, m in raw:
            cur_s += (tick - cur_tick) * tempo / (1_000_000.0 * ppq)
            cur_tick = tick
            if m.is_meta:
                if m.type == "set_tempo":
                    tempo = m.tempo
                    tempos.append((tick, 60_000_000.0 / m.tempo))
                    if first_tempo is None:
                        first_tempo = m.tempo
                elif m.type == "time_signature":
                    timesigs.append((tick, m.numerator, m.denominator))
                elif m.type == "marker" and getattr(m, "text", ""):
                    markers.append((tick, m.text.strip()))
                elif m.type == "key_signature":
                    keysigs.append((tick, m.key))
                    if key_meta is None:
                        key_meta = m.key
                elif m.type == "track_name":
                    stats.setdefault(ti, {"name": None, "notes": 0, "lo": 128,
                                          "hi": -1, "sum": 0})["name"] = m.name
                continue
            data = bytes(m.bytes())
            timeline.append((cur_s, ti, data))
            tick_events.append((tick, ti, data))
            if (data[0] & 0xF0) == 0x90 and len(data) >= 3 and data[2] > 0:
                st = stats.setdefault(ti, {"name": None, "notes": 0, "lo": 128,
                                           "hi": -1, "sum": 0})
                st["notes"] += 1
                st["lo"] = min(st["lo"], data[1])
                st["hi"] = max(st["hi"], data[1])
                st["sum"] += data[1]
        self._timeline = timeline
        self._tick_events = tick_events
        self._ppq = ppq
        self._timesigs = timesigs
        self._tempo_bpm = 60_000_000.0 / (first_tempo or 500000)
        self._key_fifths = _KEY_FIFTHS.get(key_meta)
        self._keysigs = [(t, _KEY_FIFTHS[k]) for t, k in keysigs
                         if k in _KEY_FIFTHS]
        self._markers = markers
        self._tempos = tempos
        self.track_filter = None       # a new file resets the track selection
        tracks = []
        for ti in sorted(stats):
            st = stats[ti]
            if st["notes"]:
                tracks.append({"index": ti,
                               "name": st["name"] or f"Track {ti + 1}",
                               "notes": st["notes"], "lo": st["lo"],
                               "hi": st["hi"], "avg": st["sum"] / st["notes"]})
        self.track_info = tracks
        return {"length": timeline[-1][0] if timeline else 0.0,
                "notes": sum(t["notes"] for t in tracks),
                "name": Path(path).name, "tracks": tracks}

    def export_musicxml(self, title):
        """Quantize the loaded file (respecting the track filter) and return
        MusicXML: one staff per selected note track (treble/bass by register,
        right hand first, braced), with triplet detection, two voices for
        sustained notes, tempo, dynamics from velocity, and pedal marks."""
        sel = [t for t in self.track_info if self._track_passes(t["index"])]
        if not sel:
            return None
        sel.sort(key=lambda t: t["avg"], reverse=True)
        # unnamed exporter tracks ("Track N") get proper hand names
        if len(sel) == 2 and (
                all(t["name"].startswith("Track ") for t in sel)
                or sel[0]["name"] == sel[1]["name"]):
            sel[0]["name"], sel[1]["name"] = "Right Hand", "Left Hand"
        timesigs = [(tick / self._ppq, n, d)
                    for tick, n, d in self._timesigs] or [(0, 4, 4)]
        parts = []
        part_gliss = {}
        self._sheet_gliss_dropped = 0

        def gather_raw(ti):
            open_, raw = {}, []
            for tick, eti, data in self._tick_events:
                if eti != ti:
                    continue
                hi = data[0] & 0xF0
                if hi == 0x90 and len(data) >= 3 and data[2] > 0:
                    open_.setdefault((data[0] & 0x0F, data[1]),
                                     []).append((tick, data[2]))
                elif hi in (0x80, 0x90) and len(data) >= 3:
                    lst = open_.get((data[0] & 0x0F, data[1]))
                    if lst:
                        s, vel = lst.pop(0)
                        raw.append((s / self._ppq,
                                    max(0.125, (tick - s) / self._ppq),
                                    data[1], vel))
            for (_ch, note), lst in open_.items():
                for s, vel in lst:
                    raw.append((s / self._ppq, 0.5, note, vel))
            raw.sort()
            return raw

        # a lone track that clearly spans both hands (a bare piano MIDI)
        # is register-split so the sheet still gets a grand staff
        split_jobs = []
        if len(sel) == 1:
            raw0 = gather_raw(sel[0]["index"])
            pitches = [n for _s, _d, n, _v in raw0]
            if (pitches and min(pitches) <= 55 and max(pitches) >= 67
                    and max(pitches) - min(pitches) >= 30):
                split_jobs = [
                    ("Right Hand", [e for e in raw0 if e[2] >= 60]),
                    ("Left Hand", [e for e in raw0 if e[2] < 60])]
                split_jobs = [(n, r) for n, r in split_jobs if r]
            if len(split_jobs) < 2:
                split_jobs = [(sel[0]["name"], raw0)]
        else:
            split_jobs = [(t["name"], gather_raw(t["index"])) for t in sel]

        for pname, raw in split_jobs:
            raw, glisses, dropped = strip_glissandi(raw)
            self._sheet_gliss_dropped += dropped
            part_gliss[len(parts) + 1] = [
                (int(round(a * _DIV)), int(round(b * _DIV)))
                for a, b in glisses]
            groups = {}
            for beat, dur, note, vel in raw:
                groups.setdefault(round(beat * 24) / 24.0,
                                  []).append((dur, note, vel))
            evs = []
            for beat in sorted(groups):
                # Same-onset notes only become one chord when their durations
                # are similar; a note held much longer (a pedal-point bass
                # under a chord) stays its own event so the voice-splitter
                # can keep it whole instead of clipping it to the chord.
                members = sorted(groups[beat])
                clusters = [[members[0]]]
                for d, n, v in members[1:]:
                    d0 = clusters[-1][0][0]
                    if d - d0 <= max(0.3, d0 * 0.35):
                        clusters[-1].append((d, n, v))
                    else:
                        clusters.append([(d, n, v)])
                for cl in clusters:
                    dur = min(d for d, _n, _v in cl)
                    avg = sum(v for _d, _n, v in cl) / len(cl)
                    evs.append((beat, dur, [n for _d, n, _v in cl], avg))
            avg = (sum(n for _b, _d, ns, _v in evs for n in ns)
                   / max(1, sum(len(ns) for _b, _d, ns, _v in evs)))
            clef = "treble" if avg >= 60 else "bass"
            parts.append([pname, clef, evs])

        if len(parts) > 2:
            # engrave on a grand staff: keep the two densest parts as the
            # hands, fold every other track's events in by register
            order = sorted(range(len(parts)), key=lambda i: -len(parts[i][2]))
            keep = sorted(order[:2],
                          key=lambda i: -(sum(max(e[2]) for e in parts[i][2])
                                          / max(1, len(parts[i][2]))))
            rh, lh = parts[keep[0]], parts[keep[1]]
            for i, p in enumerate(parts):
                if i in keep:
                    continue
                for ev in p[2]:
                    (rh if (sum(ev[2]) / len(ev[2])) >= 60 else lh)[2].append(ev)
            rh[2].sort(key=lambda e: e[0])
            lh[2].sort(key=lambda e: e[0])
            rh[1], lh[1] = "treble", "bass"
            if rh[0].startswith("Track ") and lh[0].startswith("Track "):
                rh[0], lh[0] = "Right Hand", "Left Hand"
            parts = [rh, lh]
        parts = [tuple(p) for p in parts]

        # the "melody" for slurs and dynamics = the densest part (a sparse
        # extra staff above the real melody would otherwise hijack them)
        mel = max(range(len(parts)), key=lambda i: len(parts[i][2])) \
            if parts else 0
        slurs = []
        if parts:
            evs0 = parts[mel][2]
            for i, j in detect_slurs(evs0):
                slurs.append((int(round(evs0[i][0] * _DIV)),
                              int(round(evs0[j][0] * _DIV))))

        # dynamics from the melody part's velocities (smoothed)
        dynamics = []
        if parts and parts[mel][2]:
            recent, last = [], None
            for beat, _d, _n, vel in parts[mel][2]:
                recent.append(vel)
                if len(recent) > 4:
                    recent.pop(0)
                mark = _dyn_for(sum(recent) / len(recent))
                if mark != last:
                    last = mark
                    dynamics.append((int(round(beat * _DIV)), mark))

        # pedal marks from CC64 anywhere in the file
        pedals, down = [], None
        for tick, _ti, data in self._tick_events:
            if (data[0] & 0xF0) == 0xB0 and len(data) >= 3 and data[1] == 64:
                on = data[2] >= 64
                if on is not down:
                    down = on
                    pedals.append((int(round(tick / self._ppq * _DIV)),
                                   "start" if on else "stop"))
        if down:
            pedals.append((pedals[-1][0] + _DIV, "stop"))

        keysigs = [(t / self._ppq, f) for t, f in self._keysigs]
        rehearsals = [(int(round(t / self._ppq * _DIV)), txt)
                      for t, txt in self._markers]
        # tempo marks: collapse rit./accel. gradients (events < 1 beat apart
        # keep only the last), then keep sustained changes of >= 6%
        raw_t = sorted(self._tempos)
        clustered = []
        cluster_start = None
        for t, bpm in raw_t:
            if clustered and cluster_start is not None \
                    and (t - cluster_start) < self._ppq:
                clustered[-1] = (t, bpm)   # refine within the same beat only
            else:
                clustered.append((t, bpm))
                cluster_start = t
        tempo_marks, last_bpm = [], None
        for t, bpm in clustered:
            if last_bpm is None or abs(bpm - last_bpm) / last_bpm >= 0.06:
                if t > 0:
                    tempo_marks.append((int(round(t / self._ppq * _DIV)), bpm))
                last_bpm = bpm
        # full playback tempo map as invisible sound elements (the printed
        # marks stay debounced; rubato survives the round trip)
        tempo_sounds = [(int(round(t / self._ppq * _DIV)), bpm)
                        for t, bpm in clustered if t > 0]
        return build_musicxml(parts, title, timesigs=timesigs,
                              tempo_bpm=self._tempo_bpm,
                              dynamics=dynamics, pedals=pedals,
                              key_fifths=self._key_fifths, slurs=slurs,
                              melody_part=mel + 1, keysigs=keysigs,
                              rehearsals=rehearsals,
                              tempo_marks=tempo_marks[:48],
                              glissandi=part_gliss,
                              tempo_sounds=tempo_sounds)

    def _track_passes(self, ti):
        f = self.track_filter
        return f is None or ti in f

    def note_spans(self):
        """[(start_s, end_s, note, track_idx)] under the current track filter -
        the falling-notes view's data. Overlapping repeats pair first-in-first-out;
        notes the file never releases get a short default length."""
        spans, open_ = [], {}
        for t, ti, data in self._timeline:
            if not self._track_passes(ti):
                continue
            hi = data[0] & 0xF0
            if hi == 0x90 and len(data) >= 3 and data[2] > 0:
                open_.setdefault((data[0] & 0x0F, data[1]), []).append((t, ti))
            elif hi in (0x80, 0x90) and len(data) >= 3:
                lst = open_.get((data[0] & 0x0F, data[1]))
                if lst:
                    s, sti = lst.pop(0)
                    spans.append((s, max(t, s + 0.06), data[1], sti))
        for (_ch, note), lst in open_.items():
            for s, sti in lst:
                spans.append((s, s + 0.5, note, sti))
        spans.sort(key=lambda x: x[0])
        return spans

    def _can_play(self):
        """A file can be played if there is at least one destination: the piano,
        Roblox keystrokes, or a virtual output port."""
        return (self._piano_ready() or self.roblox.enabled
                or self.midiout is not None)

    def play(self):
        if not self._timeline:
            self.emit("log", "Load a MIDI file first.")
            return
        if self.wait_mode and not self._active:
            self.emit("log", "Wait-for-notes needs your piano connected - "
                             "it listens for what you play.")
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
        """Absolute-time [(seconds, message_bytes)] honoring the track filter.
        Notes (and per-note aftertouch) from unselected tracks are dropped;
        pedal/program/bend always pass so the piece still sounds right with
        one hand muted."""
        sched = []
        for t, ti, data in self._timeline:
            if (data[0] & 0xF0) in (0x80, 0x90, 0xA0) and not self._track_passes(ti):
                continue
            sched.append((t, data))
        return sched

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
                self.emit("play_clock", 0.0, True)
                if self.wait_mode:
                    await self._run_playback_wait(sched)
                elif self.source_mode == "ble" and self._client is not None:
                    await self._run_playback_ble(sched, held)
                else:
                    await self._run_playback_wired(sched, held)
                if self.wait_mode:
                    # Nothing was sent anywhere in wait mode; a backstop would
                    # only cut the user's own sustain pedal.
                    self.emit("clear")
                else:
                    await self._finish_playback(held)
                if self._play_stop or not self.loop_play or not self._can_play():
                    break
                await asyncio.sleep(0.15)  # brief gap before the file repeats
        except Exception as e:
            self.emit("log", f"Playback error: {e}")
        self.emit("play_progress", total_s, total_s)
        self.emit("play_state", "stopped")

    async def _run_playback_wait(self, sched):
        """Practice mode: step through the file and, at every Note-On group,
        freeze until the user plays those notes on the connected piano. Nothing
        is auto-played - the sound is the user's own playing; the app supplies
        the score (lit keys + falling notes)."""
        n = len(sched)
        total_s = sched[-1][0] if sched else 0.0
        i = 0
        music = 0.0
        prev = self.loop.time()
        last_emit = -1.0
        while i < n:
            if self._play_stop or not self._active:
                break
            if self._play_pause:
                self.emit("play_clock", music, False)
                while self._play_pause and not self._play_stop:
                    await asyncio.sleep(0.03)
                prev = self.loop.time()
                self.emit("play_clock", music, True)
                continue
            now = self.loop.time()
            tempo = max(0.1, self.play_tempo)
            music += (now - prev) * tempo
            prev = now
            group_t = sched[i][0]
            if music < group_t:
                await asyncio.sleep(min(0.03, (group_t - music) / tempo))
                continue
            music = group_t
            group = []
            while i < n and sched[i][0] == group_t:
                group.append(sched[i][1])
                i += 1
            pending = set()
            for d in group:
                hi = d[0] & 0xF0
                if hi == 0x90 and len(d) >= 3 and d[2] > 0:
                    pending.add(d[1])
                    self.emit("wait_on", d[1])
                elif hi in (0x80, 0x90) and len(d) >= 3:
                    self.emit("note_off", d[1])
                elif hi == 0xB0 and len(d) >= 3:
                    self.emit("cc", d[1], d[2])
            if pending:
                self.emit("play_clock", music, False)
                shown = set(pending)
                self._wait_pending = pending
                while self._wait_pending and not self._play_stop and self._active:
                    await asyncio.sleep(0.02)
                self._wait_pending = None
                for note in shown:
                    self.emit("wait_off", note)
                prev = self.loop.time()
                self.emit("play_clock", music, True)
            if music - last_emit >= 0.2:
                last_emit = music
                self.emit("play_progress", min(music, total_s), total_s)
        self._wait_pending = None

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
# Sheet music export: quantize the loaded file and write MusicXML.
# Aimed at clean, sequenced piano MIDIs (the usual case in piano communities);
# free-time live recordings will quantize roughly - that's inherent.
# ---------------------------------------------------------------------------
_SHARP_SPELL = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0),
                5: ("F", 0), 6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0),
                10: ("A", 1), 11: ("B", 0)}
_FLAT_SPELL = {0: ("C", 0), 1: ("D", -1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0),
               5: ("F", 0), 6: ("G", -1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0),
               10: ("B", -1), 11: ("B", 0)}
# MIDI key_signature meta names -> circle-of-fifths position.
_KEY_FIFTHS = {}
for _i, _k in enumerate(["C", "G", "D", "A", "E", "B", "F#", "C#"]):
    _KEY_FIFTHS[_k] = _i
for _i, _k in enumerate(["F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"], 1):
    _KEY_FIFTHS[_k] = -_i
for _i, _k in enumerate(["Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m"]):
    _KEY_FIFTHS[_k] = _i
for _i, _k in enumerate(["Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm", "Abm"], 1):
    _KEY_FIFTHS[_k] = -_i

# Krumhansl-Schmuckler key profiles.
_KS_MAJ = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_KS_MIN = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_MAJ_FIFTHS = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 1: -5, 5: -1, 10: -2,
               3: -3, 8: -4}
# divisions = 24 per quarter, so 16ths (6), 32nds (3) and triplet 8ths (8)
# are all integers.
_DIV = 24
_UNIT_TYPES = [(96, "whole", 0), (72, "half", 1), (48, "half", 0),
               (36, "quarter", 1), (24, "quarter", 0), (18, "eighth", 1),
               (12, "eighth", 0), (9, "16th", 1), (6, "16th", 0), (3, "32nd", 0)]
_TUPLET_TYPES = {4: ("16th", 0), 8: ("eighth", 0), 16: ("quarter", 0)}
_DYN_BANDS = [(45, "pp"), (58, "p"), (72, "mp"), (86, "mf"), (102, "f"),
              (128, "ff")]


def detect_key(pc_weights):
    """Krumhansl-Schmuckler: correlate duration-weighted pitch classes against
    all 24 keys. Returns (fifths_for_key_signature, use_flats)."""
    total = sum(pc_weights)
    if total <= 0:
        return 0, False
    def corr(profile, rot):
        return sum(pc_weights[(i + rot) % 12] * profile[i] for i in range(12))
    best, best_fifths = None, 0
    for tonic in range(12):
        for profile, fifths in ((_KS_MAJ, _MAJ_FIFTHS[tonic]),
                                (_KS_MIN, _MAJ_FIFTHS[(tonic + 3) % 12])):
            s = corr(profile, tonic)
            if best is None or s > best:
                best, best_fifths = s, fifths
    return best_fifths, best_fifths < 0


def _diatonic(fifths):
    tonic = (fifths * 7) % 12
    return {(tonic + iv) % 12 for iv in (0, 2, 4, 5, 7, 9, 11)}


def _spell(midi, fifths, pref):
    """Spell a pitch: diatonic notes follow the key signature; chromatic
    notes spell sharp when the line ascends and flat when it descends."""
    pc = midi % 12
    if pc in _diatonic(fifths) or pref is None:
        table = _FLAT_SPELL if fifths < 0 else _SHARP_SPELL
    else:
        table = _SHARP_SPELL if pref == "up" else _FLAT_SPELL
    step, alter = table[pc]
    return step, alter, midi // 12 - 1


def _dyn_for(vel):
    for hi, name in _DYN_BANDS:
        if vel < hi:
            return name
    return "ff"


def detect_triplet_beats(starts):
    """Given raw (unquantized) onset beats, return {beat_index: grid_units}
    for beats better served by a ternary grid: 8 units = eighth-note
    triplets, 4 units = sixteenth-note triplets / sextuplets."""
    from collections import defaultdict
    per_beat = defaultdict(list)
    for s in starts:
        per_beat[int(s)].append(s - int(s))
    out = {}
    for beat, offs in per_beat.items():
        if len(offs) < 2:
            continue
        def err(grid):
            return sum(min(abs(o - g) for g in grid) for o in offs) / len(offs)
        e_bin = err((0, 0.25, 0.5, 0.75, 1.0))
        e_t8 = err((0, 1 / 3, 2 / 3, 1.0))
        e_t16 = err((0, 1 / 6, 1 / 3, 1 / 2, 2 / 3, 5 / 6, 1.0))
        if (len(offs) >= 4 and e_t16 < 0.04 and e_t16 + 0.02 < e_bin
                and e_t16 + 0.02 < e_t8):
            out[beat] = 4
        elif e_t8 < 0.055 and e_t8 + 0.02 < e_bin:
            out[beat] = 8
    return out


def strip_glissandi(raw):
    """raw: sorted [(beat, dur, note, vel)]. A glissando arrives from
    notation software as a blur of ultra-fast strictly-monotonic notes; the
    printed page shows two noteheads and a wavy line. Collapse such runs
    (IOI < 0.035 beat, >= 10 notes, span >= an octave) to their endpoints
    and return (filtered_raw, [(start_beat, stop_beat)], dropped_count)."""
    keep, glisses, dropped = [], [], 0
    i, n = 0, len(raw)
    while i < n:
        j = i
        while (j + 1 < n
               and 0 < raw[j + 1][0] - raw[j][0] < 0.035
               and (raw[j + 1][2] - raw[j][2]) * (raw[min(j + 1, i + 1)][2]
                                                  - raw[i][2]) > 0):
            j += 1
        if j - i + 1 >= 10 and abs(raw[j][2] - raw[i][2]) >= 12:
            a = list(raw[i]); b = list(raw[j])
            a[1] = max(0.25, min(a[1], raw[j][0] - raw[i][0]))
            b[1] = max(0.25, b[1])
            keep.append(tuple(a)); keep.append(tuple(b))
            glisses.append((raw[i][0], raw[j][0]))
            dropped += j - i - 1
        else:
            keep.extend(raw[i:j + 1])
        i = j + 1
    return keep, glisses, dropped


def detect_slurs(evs, max_span_beats=8.0, gap_tol=0.08):
    """Infer legato phrase slurs from a melody event stream
    [(start_beat, dur_beats, notes, ...)]. MIDI has no slur marking, so this
    is heuristic: a phrase is a run of notes whose release touches the next
    onset; it ends at a real gap, at a phrase-ending long note (>= 2 beats or
    twice the previous note), or at the span cap. Returns [(i_first, i_last)]
    event-index pairs; single notes and two-note same-pitch pairs (which read
    as ties) are skipped."""
    spans = []
    i, n = 0, len(evs)
    while i < n:
        j = i
        while j + 1 < n:
            s, d = evs[j][0], evs[j][1]
            if (evs[j + 1][0] - (s + d)) > gap_tol:
                break
            if evs[j + 1][0] - evs[i][0] >= max_span_beats:
                break
            j += 1
            if evs[j][1] >= 2.0 or evs[j][1] >= 1.99 * evs[j - 1][1]:
                break
        if j > i:
            tops = {max(evs[k][2]) for k in range(i, j + 1)}
            if not (j - i == 1 and len(tops) == 1):
                spans.append((i, j))
        i = j + 1
    return spans


def _units_to_chunks(units):
    """Split a binary duration in 24ths-of-a-quarter into standard values.
    Lossless by contract: a residue smaller than a 32nd (1-2 units, produced
    when triplet- and binary-grid events clip each other) is absorbed into
    the final chunk's duration, so measures always sum exactly."""
    out = []
    while units > 0:
        for u, typ, dots in _UNIT_TYPES:
            if u <= units:
                out.append([u, typ, dots])
                units -= u
                break
        else:
            if out:
                out[-1][0] += units
            else:
                out.append([units, "32nd", 0])
            units = 0
    return [tuple(c) for c in out]


_BEAM_COUNT = {"eighth": 1, "16th": 2, "32nd": 3}


def _note_xml(pitch, units, typ, dots, chord, tie, voice=1,
              tmod=False, tuplet=None, stem=None, beams=None, slur=None,
              cue=False, gliss=None):
    step, alter, octave = pitch
    x = ["<note>"]
    if cue:
        x.append("<cue/>")
    if chord:
        x.append("<chord/>")
    x.append(f"<pitch><step>{step}</step>"
             + (f"<alter>{alter}</alter>" if alter else "")
             + f"<octave>{octave}</octave></pitch>")
    x.append(f"<duration>{units}</duration>")
    for t in tie:
        x.append(f'<tie type="{t}"/>')
    x.append(f"<voice>{voice}</voice>")
    x.append(f"<type>{typ}</type>")
    x.extend("<dot/>" for _ in range(dots))
    if tmod:
        x.append("<time-modification><actual-notes>3</actual-notes>"
                 "<normal-notes>2</normal-notes></time-modification>")
    if stem:
        x.append(f"<stem>{stem}</stem>")
    for k, val in (beams or []):
        x.append(f'<beam number="{k}">{val}</beam>')
    nots = "".join(f'<tied type="{t}"/>' for t in tie)
    if tuplet:
        nots += f'<tuplet type="{tuplet}" bracket="yes"/>'
    for sl in (slur or ()):
        nots += f'<slur type="{sl}" number="1"/>'
    for gt in (gliss or ()):
        nots += f'<glissando type="{gt}" line-type="wavy" number="1"/>'
    if nots:
        x.append(f"<notations>{nots}</notations>")
    x.append("</note>")
    return "".join(x)


def _stem_for(notes, clef, voice, two_voices):
    """Engraving stem rule: with two voices, voice 1 stems up and voice 2
    down; otherwise the note (or the chord note farthest from the middle
    staff line) decides - below the line stems up, above stems down."""
    if two_voices:
        return "up" if voice == 1 else "down"
    mid = 71 if clef == "treble" else 50        # B4 / D3
    hi, lo = max(notes), min(notes)
    far = hi if (hi - mid) >= (mid - lo) else lo
    return "down" if far >= mid else "up"


def _assign_beams(items):
    """items: measure-ordered dicts. Groups consecutive beamable notes of the
    same voice within one beat (or one tuplet) and writes MusicXML beam
    values: begin / continue / end, with hooks for mixed values. Flags stay
    on notes left un-beamed."""
    def key(it):
        if it["kind"] != "note" or it.get("tie_mid"):
            return None
        n = _BEAM_COUNT.get(it["typ"], 0)
        if not n:
            return None
        return (it["start"] // _DIV, bool(it.get("tmod")))
    groups, cur, cur_key = [], [], None
    for it in items:
        k = key(it)
        if k is not None and k == cur_key:
            cur.append(it)
        else:
            if len(cur) > 1:
                groups.append(cur)
            cur, cur_key = ([it], k) if k is not None else ([], None)
    if len(cur) > 1:
        groups.append(cur)
    for gid, g in enumerate(groups):
        counts = [_BEAM_COUNT[it["typ"]] for it in g]
        for i, it in enumerate(g):
            it["beam_group"] = gid
            prev_c = counts[i - 1] if i else 0
            next_c = counts[i + 1] if i + 1 < len(g) else 0
            beams = []
            for k in range(1, counts[i] + 1):
                if prev_c >= k and next_c >= k:
                    beams.append((k, "continue"))
                elif next_c >= k:
                    beams.append((k, "begin"))
                elif prev_c >= k:
                    beams.append((k, "end"))
                else:
                    beams.append((k, "backward hook" if prev_c else
                                  "forward hook"))
            it["beams"] = beams


def _rest_xml(units, typ, dots, voice=1, tmod=False, hidden=False):
    po = ' print-object="no"' if hidden else ""
    tm = ("<time-modification><actual-notes>3</actual-notes>"
          "<normal-notes>2</normal-notes></time-modification>") if tmod else ""
    return (f"<note{po}><rest/><duration>{units}</duration>"
            f"<voice>{voice}</voice><type>{typ}</type>"
            + "<dot/>" * dots + tm + "</note>")


def _split_voices(q):
    """q: [[start, dur, notes]] sorted. When a new attack overlaps a note that
    still has more than a 16th left, keep the sustained note whole in voice 2
    instead of clipping it (classic held-bass-under-melody writing). Returns
    (voice1_events, voice2_events); residual overlaps within a voice clip."""
    v = ([], [])
    end = [0, 0]
    for ev in q:
        s = ev[0]
        if s >= end[0]:
            v[0].append(ev); end[0] = s + ev[1]
        elif end[0] - s > 6 and s >= end[1] and v[0]:
            v[1].append(v[0].pop())           # demote the sustained event
            end[1] = end[0]
            v[0].append(ev); end[0] = s + ev[1]
        else:
            tgt = 0 if end[0] <= end[1] else 1
            v[tgt].append(ev); end[tgt] = s + ev[1]
    for stream in v:
        stream.sort(key=lambda e: e[0])
        merged = []
        for ev in stream:
            if merged and ev[0] == merged[-1][0]:
                # a third simultaneous layer landed here: fold it into a
                # chord rather than letting equal starts corrupt the bar
                merged[-1][2] = sorted(set(merged[-1][2]) | set(ev[2]),
                                       reverse=True)
                merged[-1][1] = max(merged[-1][1], ev[1])
            else:
                merged.append(ev)
        stream[:] = merged
        for i in range(len(stream) - 1):
            if stream[i][0] + stream[i][1] > stream[i + 1][0]:
                stream[i][1] = max(1, stream[i + 1][0] - stream[i][0])
    return v


def _quantize_part(evs, triplet_beats, base_unit):
    """(beat, dur, notes[, vel]) -> [[start_u, dur_u, notes]] on the 24-grid.
    Onsets in triplet beats snap to thirds; elsewhere to base_unit."""
    q = []
    for ev in evs:
        s, d, notes = ev[0], ev[1], ev[2]
        beat = int(s)
        if beat in triplet_beats:
            g = triplet_beats[beat]
            n = _DIV // g
            su = beat * _DIV + int(round((s - beat) * n)) * g
            du = max(g, int(round(d * n)) * g)
            du = min(du, (beat + 1) * _DIV - su) or g
        else:
            su = int(round(s * _DIV / base_unit)) * base_unit
            du = max(base_unit, int(round(d * _DIV / base_unit)) * base_unit)
        q.append([su, du, sorted(set(notes), reverse=True)])
    # longest-first at equal onsets, so a sustained note is already placed
    # when the shorter attack arrives and can be demoted to voice 2 whole
    q.sort(key=lambda e: (e[0], -e[1]))
    return q


def _bar_map(timesigs, total_units):
    """Normalize [(start_beat, num, den)] into a bar list covering
    total_units: [(start_u, end_u, show_ts_or_None, implicit)]. A new
    signature takes effect at the next barline of the one before it. A first
    signature that lasts exactly one of its own (shorter) bars is a pickup:
    the bar is kept short + implicit but displays the main signature."""
    sigs = sorted(timesigs or [(0, 4, 4)])
    norm = [(0, sigs[0][1], sigs[0][2])]
    for su, num, den in sigs[1:]:
        ps, pn, pd = norm[-1]
        pbar = max(1, int(round(pn * (4.0 / pd) * _DIV)))
        k = max(1, round((su * _DIV - ps) / pbar))
        eff = ps + k * pbar
        if (num, den) != (pn, pd):
            norm.append((eff, num, den))
    pickup = None
    if len(norm) >= 2:
        s0, n0, d0 = norm[0]
        bar0 = int(round(n0 * (4.0 / d0) * _DIV))
        bar1 = int(round(norm[1][1] * (4.0 / norm[1][2]) * _DIV))
        if norm[1][0] - s0 == bar0 and bar0 < bar1:
            pickup = (0, bar0, (norm[1][1], norm[1][2]), True)
            norm = norm[1:]
    bars = [pickup] if pickup else []
    for i, (s, num, den) in enumerate(norm):
        bar = max(1, int(round(num * (4.0 / den) * _DIV)))
        end_at = norm[i + 1][0] if i + 1 < len(norm) else max(total_units, s + bar)
        pos = s
        # the pickup bar already displays this signature - don't print it twice
        first = not (pickup and i == 0)
        # a "cadenza bar" (one giant irregular measure, how MIDI encodes free
        # runs) reads better without its bizarre signature printed
        cadenza = num > 12 or den > 8
        while pos < end_at:
            show = (num, den) if first and not cadenza else None
            bars.append((pos, pos + bar, show, cadenza))
            pos += bar
            first = False
    while bars[-1][1] < total_units:
        s, e, _sh, _im = bars[-1]
        bars.append((e, e + (e - s), None, False))
    return bars


def build_musicxml(parts, title, timesigs=None, tempo_bpm=None,
                   dynamics=None, pedals=None, key_fifths=None, slurs=None,
                   melody_part=1, keysigs=None, rehearsals=None,
                   tempo_marks=None, glissandi=None, tempo_sounds=None):
    """parts: [(name, clef, [(start_beat, dur_beats, [notes], avg_vel)...])].
    timesigs: [(start_beat, num, den)] incl. mid-piece changes and pickups.
    dynamics: [(unit, mark)] for the first part; pedals: [(unit, 'start'|
    'stop')] for the last part. key_fifths overrides key detection (use the
    file's own key signature when it has one)."""
    dynamics = list(dynamics or [])
    pedals = list(pedals or [])
    slur_pairs = list(slurs or [])

    if key_fifths is None:
        pc = [0.0] * 12
        for _n, _c, evs in parts:
            for ev in evs:
                for n in ev[2]:
                    pc[n % 12] += ev[1]
        fifths, _uf = detect_key(pc)
    else:
        fifths = key_fifths
    keymap = sorted((int(round(b * _DIV)), f) for b, f in (keysigs or []))
    if not keymap:
        keymap = [(0, fifths)]

    # quantize + voice-split first (bar map needs the total length)
    quantized = []
    total_units = _DIV
    for pname, clef, evs in parts:
        starts = [ev[0] for ev in evs]
        trip = detect_triplet_beats(starts)
        iois = sorted(b - a for a, b in zip(starts, starts[1:]) if b > a)
        base = 3 if (iois and iois[0] < 0.2) else 6
        voices = _split_voices(_quantize_part(evs, trip, base))
        prefs = []
        for stream in voices:
            tops = [max(n) for _s, _d, n in stream]
            p = []
            for k in range(len(stream)):
                nxt = tops[k + 1] if k + 1 < len(tops) else None
                prv = tops[k - 1] if k else None
                if nxt is not None and nxt != tops[k]:
                    p.append("up" if nxt > tops[k] else "down")
                elif prv is not None and prv != tops[k]:
                    p.append("up" if tops[k] > prv else "down")
                else:
                    p.append(None)
            prefs.append(p)
            for s, d, _n in stream:
                total_units = max(total_units, s + d)
        quantized.append((pname, clef, voices, trip, prefs))

    bars = _bar_map(timesigs, total_units)
    import bisect
    ends = [b[1] for b in bars]

    # slur endpoints must land on notes that actually exist in the melody's
    # voice 1 after voice-splitting - snap them there, drop any slur whose
    # endpoints didn't survive (e.g. its last note was demoted to voice 2)
    slur_start, slur_stop = set(), set()
    mi = melody_part - 1
    if slur_pairs and 0 <= mi < len(quantized):
        v1 = sorted(s for s, _d, _n in quantized[mi][2][0])
        def snap(u):
            if not v1:
                return None
            i = bisect.bisect_left(v1, u)
            best = min([x for x in (v1[i - 1] if i else None,
                                    v1[i] if i < len(v1) else None)
                        if x is not None], key=lambda x: abs(x - u))
            return best if abs(best - u) <= 12 else None
        snapped, prev_end = [], -1
        for a, b in sorted(slur_pairs):
            sa, sb = snap(a), snap(b)
            if sa is not None and sb is not None and prev_end < sa < sb:
                snapped.append((sa, sb))
                prev_end = sb
        slur_start = {a for a, _b in snapped}
        slur_stop = {b for _a, b in snapped}

    # glissando endpoints likewise snap to surviving quantized starts
    # (either voice of their own part)
    gliss_map = {}
    for pno, pairs in (glissandi or {}).items():
        if not pairs or not (1 <= pno <= len(quantized)):
            continue
        va = sorted(s for stream in quantized[pno - 1][2]
                    for s, _d, _n in stream)
        def gsnap(u):
            if not va:
                return None
            i = bisect.bisect_left(va, u)
            cand = [x for x in (va[i - 1] if i else None,
                                va[i] if i < len(va) else None)
                    if x is not None]
            best = min(cand, key=lambda x: abs(x - u))
            return best if abs(best - u) <= 6 else None
        out = []
        for a, b in pairs:
            sa, sb = gsnap(a), gsnap(b)
            if sa is not None and sb is not None and sa != sb:
                out.append((sa, sb))
        gliss_map[pno] = out
    glissandi = gliss_map

    prepared = []
    for pname, clef, voices, trip, prefs in quantized:
        segs = [[], []]
        for vi, stream in enumerate(voices):
            for ei, (s, d, notes) in enumerate(stream):
                pref = prefs[vi][ei]
                e, a, first = s + d, s, True
                while a < e:
                    b = min(e, ends[min(len(ends) - 1,
                                        bisect.bisect_right(ends, a))])
                    if b <= a:
                        b = e
                    tie = ([] if first else ["stop"]) + (["start"] if b < e else [])
                    segs[vi].append((a, b - a, notes, tie, s, pref))
                    a, first = b, False
        prepared.append((pname, clef, segs, trip))

    body = []
    plist = ['<part-list><part-group type="start" number="1">'
             '<group-symbol>brace</group-symbol></part-group>']
    for pi, (pname, clef, segs, trip) in enumerate(prepared, 1):
        plist.append(f'<score-part id="P{pi}"><part-name>{pname}</part-name>'
                     "</score-part>")
        marks = sorted(dynamics) if pi == melody_part else []
        peds = sorted(pedals) if pi == len(prepared) else []
        rehs = sorted(rehearsals or []) if pi == 1 else []
        tmarks = sorted(tempo_marks or []) if pi == 1 else []
        tsounds = sorted(tempo_sounds or []) if pi == 1 else []
        gl = (glissandi or {}).get(pi, [])
        gl_a = {a for a, _b in gl}
        gl_b = {b for _a, b in gl}
        mx = [f'<part id="P{pi}">']

        first_num = next((b[2] for b in bars if b[2]), (4, 4))
        prev_f = None
        for bar, (bar_start, bar_end, show_ts, implicit) in enumerate(bars):
            imp = ' implicit="yes"' if implicit else ""
            n0 = 0 if bars[0][3] else 1
            mx.append(f'<measure number="{bar + n0}"{imp}>')
            ki = bisect.bisect_right([u for u, _f in keymap], bar_start) - 1
            cur_f = keymap[max(0, ki)][1]
            attrs = []
            if bar == 0:
                attrs.append(f"<divisions>{_DIV}</divisions>")
            if cur_f != prev_f:
                attrs.append(f"<key><fifths>{cur_f}</fifths></key>")
                prev_f = cur_f
            if bar == 0:
                num, den = show_ts or first_num
                attrs.append(f"<time><beats>{num}</beats>"
                             f"<beat-type>{den}</beat-type></time>")
                sign, line = ("G", 2) if clef == "treble" else ("F", 4)
                attrs.append(f"<clef><sign>{sign}</sign>"
                             f"<line>{line}</line></clef>")
            elif show_ts:
                attrs.append(f"<time><beats>{show_ts[0]}</beats>"
                             f"<beat-type>{show_ts[1]}</beat-type></time>")
            if attrs:
                mx.append("<attributes>" + "".join(attrs) + "</attributes>")
            if bar == 0 and pi == 1 and tempo_bpm:
                bpm = int(round(tempo_bpm))
                mx.append("<direction placement=\"above\"><direction-type>"
                          "<metronome><beat-unit>quarter</beat-unit>"
                          f"<per-minute>{bpm}</per-minute></metronome>"
                          f'</direction-type><sound tempo="{bpm}"/>'
                          "</direction>")
            # cadenza bars print their runs in small cue-size notes,
            # like engraved editions do
            cue_bar = implicit and show_ts is None
            two = any(bar_start <= t[0] < bar_end for t in segs[1])
            for vi in (0, 1):
                vsegs = [t for t in segs[vi]
                         if bar_start <= t[0] < bar_end]
                if vi == 1:
                    if not vsegs:
                        continue
                    mx.append(f"<backup><duration>{bar_end - bar_start}"
                              "</duration></backup>")
                items = []

                def gap_items(a, b, voice):
                    while a < b:
                        beat = a // _DIV
                        beat_end = (beat + 1) * _DIV
                        seg_end = min(b, beat_end)
                        if beat in trip and (a % _DIV or seg_end % _DIV):
                            g = trip[beat]
                            while a < seg_end:
                                u = min(g, seg_end - a)
                                items.append({"kind": "rest", "start": a,
                                              "units": u,
                                              "typ": "16th" if g == 4
                                              else "eighth",
                                              "dots": 0, "tmod": True,
                                              "voice": voice})
                                a += u
                        else:
                            for u, typ, dots in _units_to_chunks(seg_end - a):
                                items.append({"kind": "rest", "start": a,
                                              "units": u, "typ": typ,
                                              "dots": dots, "tmod": False,
                                              "voice": voice})
                                a += u

                def mark_items(upto):
                    while tsounds and tsounds[0][0] <= upto:
                        _u, bpm = tsounds.pop(0)
                        items.append({"kind": "raw", "xml":
                            f'<sound tempo="{bpm:.2f}"/>'})
                    while rehs and rehs[0][0] <= upto:
                        _u, txt = rehs.pop(0)
                        safe = (txt.replace("&", "&amp;").replace("<", "&lt;")
                                .replace(">", "&gt;"))
                        items.append({"kind": "raw", "xml":
                            '<direction placement="above"><direction-type>'
                            f'<rehearsal enclosure="square">{safe}'
                            "</rehearsal></direction-type></direction>"})
                    while tmarks and tmarks[0][0] <= upto:
                        _u, bpm = tmarks.pop(0)
                        b = int(round(bpm))
                        items.append({"kind": "raw", "xml":
                            '<direction placement="above"><direction-type>'
                            "<metronome><beat-unit>quarter</beat-unit>"
                            f"<per-minute>{b}</per-minute></metronome>"
                            f'</direction-type><sound tempo="{b}"/>'
                            "</direction>"})
                    while marks and marks[0][0] <= upto:
                        _u, mark = marks.pop(0)
                        items.append({"kind": "raw", "xml":
                            '<direction placement="below"><direction-type>'
                            f"<dynamics><{mark}/></dynamics>"
                            "</direction-type></direction>"})
                    while peds and peds[0][0] <= upto:
                        _u, kindp = peds.pop(0)
                        items.append({"kind": "raw", "xml":
                            '<direction placement="below"><direction-type>'
                            f'<pedal type="{kindp}" line="yes"/>'
                            "</direction-type></direction>"})

                cursor = bar_start
                for s, d, notes, tie, ev_start, pref in vsegs:
                    # safety net: never let content walk backwards or spill
                    # past the barline, whatever upstream produced
                    if s < cursor:
                        d = max(1, d - (cursor - s))
                        s = cursor
                    if s >= bar_end:
                        continue
                    d = min(d, bar_end - s)
                    slur_a = (pi == melody_part and vi == 0
                              and ev_start in slur_start
                              and "stop" not in tie)
                    slur_b = (pi == melody_part and vi == 0
                              and ev_start in slur_stop
                              and "start" not in tie)
                    gls_a = ev_start in gl_a and "stop" not in tie
                    gls_b = ev_start in gl_b and "stop" not in tie
                    if gls_a:
                        gl_a.discard(ev_start)   # attach each endpoint once
                    if gls_b:
                        gl_b.discard(ev_start)
                    if vi == 0:
                        mark_items(s)
                    if s > cursor:
                        gap_items(cursor, s, vi + 1)
                    beat = s // _DIV
                    if beat in trip and d in _TUPLET_TYPES:
                        typ, dots = _TUPLET_TYPES[d]
                        first_in_beat = s % _DIV == 0
                        last_in_beat = (s + d) % _DIV == 0
                        tup = ("start" if first_in_beat else
                               ("stop" if last_in_beat else None))
                        items.append({"kind": "note", "start": s, "units": d,
                                      "typ": typ, "dots": dots, "notes": notes,
                                      "tie": tie, "tmod": True, "tuplet": tup,
                                      "voice": vi + 1, "pref": pref,
                                      "gliss": (["stop"] if gls_b else []) +
                                               (["start"] if gls_a else []),
                                      "slur": (["stop"] if slur_b else []) +
                                              (["start"] if slur_a else [])})
                    else:
                        pos = s
                        chunks = _units_to_chunks(d)
                        for ci, (u, typ, dots) in enumerate(chunks):
                            ctie = list(tie)
                            if len(chunks) > 1:
                                if ci > 0 and "stop" not in ctie:
                                    ctie.insert(0, "stop")
                                if ci < len(chunks) - 1 and "start" not in ctie:
                                    ctie.append("start")
                            items.append({"kind": "note", "start": pos,
                                          "units": u, "typ": typ, "dots": dots,
                                          "notes": notes, "tie": ctie,
                                          "tmod": False, "tuplet": None,
                                          "voice": vi + 1, "pref": pref,
                                          "gliss": (
                                              (["stop"] if gls_b and ci == 0
                                               else []) +
                                              (["start"] if gls_a and ci == 0
                                               else []))
                                          if ci == 0 else [],
                                          "slur": (
                                              (["stop"] if slur_b and ci == 0
                                               else []) +
                                              (["start"] if slur_a and ci == 0
                                               else []))})
                            pos += u
                    cursor = s + d
                if cursor < bar_end:
                    if vi == 0:
                        mark_items(bar_end - 1)
                    gap_items(cursor, bar_end, vi + 1)

                _assign_beams(items)
                for it in items:
                    if it["kind"] == "note":
                        it["stem"] = None if it["typ"] == "whole" else \
                            _stem_for(it["notes"], clef, it["voice"], two)
                # engraving rule: one stem direction per beam group, decided
                # by the note farthest from the middle staff line (unless the
                # two-voice rule already fixed it)
                if not two:
                    from collections import defaultdict
                    gmap = defaultdict(list)
                    for it in items:
                        if it.get("beam_group") is not None:
                            gmap[it["beam_group"]].append(it)
                    mid = 71 if clef == "treble" else 50
                    for g in gmap.values():
                        pitches = [n for it in g for n in it["notes"]]
                        hi, lo = max(pitches), min(pitches)
                        d = "down" if (hi - mid) >= (mid - lo) else "up"
                        for it in g:
                            it["stem"] = d
                for it in items:
                    if it["kind"] == "raw":
                        mx.append(it["xml"])
                    elif it["kind"] == "rest":
                        mx.append(_rest_xml(it["units"], it["typ"], it["dots"],
                                            it["voice"], tmod=it["tmod"],
                                            hidden=it["voice"] > 1))
                    else:
                        stem = it["stem"]
                        for ni, note in enumerate(it["notes"]):
                            mx.append(_note_xml(
                                _spell(note, cur_f, it.get("pref")),
                                it["units"], it["typ"], it["dots"],
                                cue=cue_bar, chord=ni > 0, tie=it["tie"],
                                voice=it["voice"], tmod=it["tmod"],
                                tuplet=it["tuplet"] if ni == 0 else None,
                                stem=stem,
                                beams=it.get("beams") if ni == 0 else None,
                                slur=it.get("slur") if ni == 0 else None,
                                gliss=it.get("gliss") if ni == 0 else None))
            mx.append("</measure>")
        mx.append("</part>")
        body.append("".join(mx))
    plist.append('<part-group type="stop" number="1"/></part-list>')
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<score-partwise version="3.1">'
            f"<work><work-title>{title}</work-title></work>"
            + "".join(plist) + "".join(body) + "</score-partwise>")


# ---------------------------------------------------------------------------
# Sheet music import: MusicXML (.musicxml/.xml, or compressed .mxl) -> MIDI.
# Together with the exporter this makes sheet music playable on the piano,
# in Roblox, and saveable as a .mid.
# ---------------------------------------------------------------------------
_STEP_SEMIS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_DYN_VEL = {"ppp": 24, "pp": 33, "p": 49, "mp": 64, "mf": 80, "f": 96,
            "ff": 112, "fff": 120, "sf": 100, "sfz": 100, "fp": 85}


def _mxl_root(path):
    """Parse .musicxml/.xml, or a compressed .mxl (a zip whose META-INF
    container points at the score). Returns the ElementTree root."""
    import xml.etree.ElementTree as ET
    import zipfile
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            target = None
            try:
                cont = ET.fromstring(z.read("META-INF/container.xml"))
                rf = cont.find(".//rootfile")
                if rf is not None:
                    target = rf.get("full-path")
            except Exception:
                pass
            if not target:
                target = next(n for n in z.namelist()
                              if n.endswith((".musicxml", ".xml"))
                              and not n.startswith("META-INF"))
            return ET.fromstring(z.read(target))
    return ET.parse(path).getroot()


def musicxml_to_midi(path, ppq=480):
    """Convert a (score-partwise) MusicXML file to a mido.MidiFile.
    Handles pitches, chords, rests, ties, dots via durations, multiple voices
    through <backup>/<forward>, per-part divisions, tempo, and dynamics."""
    import mido
    root = _mxl_root(path)
    if root.tag != "score-partwise":
        raise ValueError("Only score-partwise MusicXML is supported "
                         f"(got <{root.tag}>).")
    names = {}
    for sp in root.findall(".//score-part"):
        nm = sp.findtext("part-name") or sp.get("id")
        names[sp.get("id")] = (nm or "").strip() or sp.get("id")

    mid = mido.MidiFile(ticks_per_beat=ppq)
    conductor = mido.MidiTrack()
    mid.tracks.append(conductor)
    tempo_events = []      # (beat_position, bpm) - a real tempo MAP
    _MET_FACTOR = {"quarter": 1.0, "half": 2.0, "whole": 4.0, "eighth": 0.5,
                   "16th": 0.25}

    for part in root.findall("part"):
        divisions = 1
        cursor = 0.0          # absolute position in beats
        vel = 80
        gliss_open = None     # (pitch, start_beat, vel, staff) awaiting stop
        events = []           # (start, dur, note, vel, tie_start, tie_stop, staff)
        for meas in part.findall("measure"):
            meas_start = cursor
            for el in meas:
                if el.tag == "attributes":
                    d = el.findtext("divisions")
                    if d:
                        divisions = max(1, int(d))
                elif el.tag == "direction":
                    dyn = el.find(".//dynamics")
                    if dyn is not None and len(dyn):
                        vel = _DYN_VEL.get(dyn[0].tag, vel)
                    snd = el.find("sound")
                    if snd is not None and snd.get("tempo"):
                        tempo_events.append((cursor, float(snd.get("tempo"))))
                    else:
                        met = el.find(".//metronome")
                        if met is not None and met.findtext("per-minute"):
                            bu = (met.findtext("beat-unit") or
                                  "quarter").strip()
                            fac = _MET_FACTOR.get(bu, 1.0)
                            if met.find("beat-unit-dot") is not None:
                                fac *= 1.5
                            try:
                                tempo_events.append(
                                    (cursor,
                                     float(met.findtext("per-minute")) * fac))
                            except ValueError:
                                pass
                elif el.tag == "sound" and el.get("tempo"):
                    tempo_events.append((cursor, float(el.get("tempo"))))
                elif el.tag == "backup":
                    cursor -= int(el.findtext("duration") or 0) / divisions
                elif el.tag == "forward":
                    cursor += int(el.findtext("duration") or 0) / divisions
                elif el.tag == "note":
                    dur = int(el.findtext("duration") or 0) / divisions
                    if el.find("grace") is not None:
                        dur = 0.0
                    chord = el.find("chord") is not None
                    start = cursor - (events[-1][1] if chord and events else 0) \
                        if chord else cursor
                    staff = int(el.findtext("staff") or 1)
                    if el.find("rest") is None:
                        p = el.find("pitch")
                        if p is not None:
                            step = p.findtext("step") or "C"
                            alter = int(float(p.findtext("alter") or 0))
                            octv = int(p.findtext("octave") or 4)
                            note = 12 * (octv + 1) + _STEP_SEMIS[step] + alter
                            ties = [t.get("type") for t in el.findall("tie")]
                            events.append((start, dur, note, vel,
                                           "start" in ties, "stop" in ties,
                                           staff))
                            gls = [g.get("type")
                                   for g in el.findall(".//glissando")]
                            if "stop" in gls and gliss_open:
                                p1, b1, v1, st1 = gliss_open
                                gliss_open = None
                                steps = abs(note - p1)
                                if steps >= 2 and start > b1:
                                    sgn = 1 if note > p1 else -1
                                    dt = (start - b1) / steps
                                    for k in range(1, steps):
                                        events.append((b1 + k * dt, dt * 0.9,
                                                       p1 + sgn * k, v1,
                                                       False, False, st1))
                            if "start" in gls:
                                gliss_open = (note, start, vel, staff)
                    if not chord:
                        cursor += dur
            # keep voices honest: a measure never moves the cursor backwards
            cursor = max(cursor, meas_start)

        # merge ties: a tie-stop extends the previous same-pitch note
        # (per staff, so hands can't steal each other's ties)
        merged = []
        open_by_note = {}
        for start, dur, note, v, t_start, t_stop, staff in sorted(events):
            key = (staff, note)
            if t_stop and key in open_by_note:
                i = open_by_note[key]
                s0, d0, n0, v0, st0 = merged[i]
                merged[i] = (s0, (start + dur) - s0, n0, v0, st0)
                if not t_start:
                    del open_by_note[key]
                continue
            merged.append((start, dur, note, v, staff))
            if t_start:
                open_by_note[key] = len(merged) - 1
        # a two-staff piano part becomes two tracks: one per hand
        by_staff = {}
        for s, d, n, v, staff in merged:
            by_staff.setdefault(staff, []).append((s, d, n, v))
        pname = names.get(part.get("id"), "Part")
        for staff in sorted(by_staff):
            tr = mido.MidiTrack()
            mid.tracks.append(tr)
            if len(by_staff) > 1:
                tname = {1: "Right Hand", 2: "Left Hand"}.get(
                    staff, f"Staff {staff}")
            else:
                tname = pname
            tr.append(mido.MetaMessage("track_name", name=tname, time=0))
            timed = []
            for s, d, n, v in by_staff[staff]:
                if d <= 0:
                    d = 0.05
                timed.append((int(round(s * ppq)), 1, n, v))
                timed.append((int(round((s + d) * ppq)), 0, n, 0))
            timed.sort(key=lambda e: (e[0], e[1]))
            last = 0
            for tick, on, n, v in timed:
                tr.append(mido.Message("note_on" if on else "note_off",
                                       note=n, velocity=v,
                                       time=max(0, tick - last)))
                last = tick

    # build the conductor's tempo map: dedupe, ensure a tempo at beat 0,
    # emit every change at its true position
    tmap = []
    for beat, bpm in sorted(tempo_events):
        if tmap and abs(tmap[-1][0] - beat) < 1e-6:
            tmap[-1] = (beat, bpm)
        elif not tmap or abs(tmap[-1][1] - bpm) > 1e-6:
            tmap.append((beat, bpm))
    if not tmap:
        tmap = [(0.0, 120.0)]
    if tmap[0][0] > 1e-6:
        tmap.insert(0, (0.0, tmap[0][1]))
    last_tick = 0
    for beat, bpm in tmap:
        tick = int(round(beat * ppq))
        conductor.append(mido.MetaMessage(
            "set_tempo", tempo=mido.bpm2tempo(bpm),
            time=max(0, tick - last_tick)))
        last_tick = tick
    return mid


def _sheet_html(title, musicxml):
    """A self-contained page that renders the MusicXML in the browser via
    OpenSheetMusicDisplay (loaded from a CDN; offline users still have the
    .musicxml for MuseScore)."""
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{title} - sheet music</title>"
            "<style>body{margin:0;font-family:Segoe UI,Arial,sans-serif;"
            "background:#f4f5f8}#bar{padding:10px 18px;background:#181d30;"
            "color:#e6e8ee;display:flex;align-items:center;gap:14px}"
            "#bar b{font-size:15px}#bar button{padding:6px 14px;border:0;"
            "border-radius:6px;background:#5b8cff;color:#fff;cursor:pointer}"
            "#sheet{background:#fff;max-width:1050px;margin:18px auto;"
            "padding:22px;box-shadow:0 2px 14px rgba(0,0,0,.12)}"
            "#msg{padding:26px;text-align:center;color:#555}"
            "@media print{#bar{display:none}#sheet{box-shadow:none;margin:0}}"
            "</style></head><body>"
            f"<div id='bar'><b>{title}</b>"
            "<span style='opacity:.65;font-size:12px'>made with "
            "Shelementyev's BLE-MIDI Bridge</span>"
            "<span style='flex:1'></span>"
            "<button onclick='window.print()'>Print</button></div>"
            "<div id='msg'>Loading notation renderer...</div>"
            "<div id='sheet'></div>"
            "<script type='application/vnd.recordare.musicxml+xml' id='mxl'>"
            + musicxml.replace("<script", "").replace("</script", "")
            + "</script>"
            "<script src='https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.8.4/"
            "build/opensheetmusicdisplay.min.js'></script>"
            "<script>window.addEventListener('load',async()=>{"
            "const m=document.getElementById('msg');"
            "if(!window.opensheetmusicdisplay){m.textContent="
            "'No internet connection - open the .musicxml file in MuseScore "
            "(free) to view the sheet music.';return}"
            "try{const osmd=new opensheetmusicdisplay.OpenSheetMusicDisplay("
            "'sheet',{autoResize:true,drawTitle:true});"
            "await osmd.load(document.getElementById('mxl').textContent);"
            "osmd.render();m.style.display='none';}catch(e){"
            "m.textContent='Could not render: '+e;}});</script>"
            "</body></html>")


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
class Tooltip:
    """A small hover tooltip that explains a control."""

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify="left", bg="#0c0d11",
                 fg="#e7eaf2", relief="solid", bd=1, wraplength=330,
                 padx=9, pady=7, font=("Segoe UI", 9)).pack()

    def _hide(self, _=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Shelementyev's BLE-MIDI Bridge {APP_VERSION}")
        self.configure(bg=BG)
        try:
            self._app_icon = tk.PhotoImage(data=ICON_PNG_B64)
            self.iconphoto(True, self._app_icon)
        except Exception:
            pass

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
        self._tracks_meta = []     # note-bearing tracks of the loaded file
        self._playing = False
        # Falling-notes view + the local playback clock it animates against.
        self._fall_spans = []
        self._fall_idx = 0
        self._fall_items = deque()   # (canvas_item, start_s, end_s)
        self._fall_geom = {}
        self._fall_right_track = None
        self._fall_last_music = None
        self._fall_after = None
        self._clock_music = 0.0
        self._clock_wall = None
        self._clock_run = False
        self._wait_notes = set()     # keys currently shown amber (wait mode)
        self._wait_labels = {}       # note -> canvas text id of its name label

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

        self._append_log("Tip: 'Load MIDI / Sheet...' opens .mid files AND "
                         "MusicXML scores (.musicxml/.mxl). 'Sheet music...' "
                         "turns the loaded file into printable notation.")

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
    def _tip(self, widget, text):
        Tooltip(widget, text)
        return widget

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

        self._tip(ttk.Label(conn, text="Source"),
                  "How your piano is connected: Bluetooth LE, or a wired USB/DIN "
                  "MIDI input if one is available.").grid(
                      row=0, column=0, sticky="w", padx=(0, 10))
        self.source_cb = ttk.Combobox(conn, state="readonly",
                                      values=["Bluetooth LE"])
        self.source_cb.current(0)
        self.source_cb.grid(row=0, column=1, sticky="ew")
        self.source_cb.bind("<<ComboboxSelected>>", self._on_source_change)
        self._tip(self.source_cb, "How your piano is connected: Bluetooth LE, or a "
                  "wired USB/DIN MIDI input.")
        self._tip(ttk.Button(conn, text="Refresh", command=self.refresh_ports),
                  "Re-scan for available MIDI ports and outputs.").grid(
                      row=0, column=2, padx=(8, 0))

        self.piano_lbl = ttk.Label(conn, text="Piano (BLE)")
        self.piano_lbl.grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self.device_cb = ttk.Combobox(conn, state="readonly", values=[])
        self.device_cb.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.scan_btn = ttk.Button(conn, text="Scan", command=self.on_scan)
        self.scan_btn.grid(row=1, column=2, padx=(8, 0), pady=(8, 0))
        self._tip(self.device_cb, "Pick your piano here. For Bluetooth, click Scan "
                  "first then choose it from the list; for USB, choose the detected "
                  "MIDI input.")
        self._tip(self.scan_btn, "Search for nearby Bluetooth MIDI devices.")

        self._tip(ttk.Label(conn, text="Forward to"),
                  "Optional: send your live playing to another program (Synthesia, "
                  "a DAW) through a virtual MIDI port. Not needed for Roblox.").grid(
                      row=2, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self.port_cb = ttk.Combobox(conn, state="readonly", values=[])
        self.port_cb.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        self._tip(self.port_cb, "The virtual MIDI port to forward to (the built-in "
                  "port, LoopBe, or loopMIDI). Leave blank if you only play into "
                  "Roblox.")
        ttk.Label(conn, text="(LoopBe / loopMIDI - optional)",
                  style="Muted.TLabel").grid(row=2, column=2, padx=(8, 0),
                                             pady=(8, 0), sticky="w")

        btns = ttk.Frame(conn)
        btns.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.connect_btn = ttk.Button(btns, text="Connect", style="Accent.TButton",
                                      command=self.on_connect)
        self.connect_btn.pack(side="left")
        self._tip(self.connect_btn, "Connect to the selected piano and start "
                  "bridging its MIDI.")
        self.disconnect_btn = ttk.Button(btns, text="Disconnect",
                                         command=self.on_disconnect, state="disabled")
        self.disconnect_btn.pack(side="left", padx=(8, 0))
        self.autoconn_var = tk.BooleanVar(value=False)
        self._tip(ttk.Checkbutton(btns, text="Auto-connect on launch",
                                  variable=self.autoconn_var),
                  "Reconnect to your last piano automatically when the app "
                  "opens.").pack(side="right")
        self.autorecon_var = tk.BooleanVar(value=True)
        self._tip(ttk.Checkbutton(btns, text="Auto-reconnect",
                                  variable=self.autorecon_var,
                                  command=self._sync_settings),
                  "If the connection drops, keep trying to reconnect on its "
                  "own.").pack(side="right", padx=(0, 14))

        # Controls panel (transpose / velocity / panic)
        ctrl = ttk.Frame(self, padding=12)
        ctrl.pack(fill="x", padx=16, pady=6)

        self._tip(ttk.Label(ctrl, text="Transpose"),
                  "Shift every note up or down in semitones (12 = one octave). "
                  "Useful if a song sits too high or low for the game's "
                  "range.").pack(side="left")
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
        self._tip(self.panic_btn, "Instantly release every held note and the "
                  "sustain pedal - clears anything stuck. Same as the F8 hotkey.")

        vel = ttk.Frame(self, padding=(12, 0, 12, 8))
        vel.pack(fill="x", padx=16)
        self._tip(ttk.Label(vel, text="Velocity"),
                  "Scales how hard notes play. 100% = unchanged; higher = "
                  "louder/harder, lower = softer.").pack(side="left")
        self.vel_var = tk.IntVar(value=100)
        self.vel_scale = ttk.Scale(vel, from_=25, to=200, variable=self.vel_var,
                                   command=self._on_vel, length=240)
        self.vel_scale.pack(side="left", padx=(8, 8))
        self._tip(self.vel_scale, "Scales how hard notes play. 100% = unchanged.")
        self.vel_lbl = ttk.Label(vel, text="100%", width=6)
        self.vel_lbl.pack(side="left")
        self.clean_var = tk.BooleanVar(value=True)
        self._tip(ttk.Checkbutton(vel,
                  text="Clean output (filter sensing/clock - recommended)",
                  variable=self.clean_var, command=self._sync_settings),
                  "Filters out 'active sensing' and timing-clock messages that some "
                  "pianos send constantly, which can confuse other software. Leave "
                  "on unless you have a reason not to.").pack(side="right")

        # Roblox keystroke output: Piano Rooms (MIDI mod) or Virtual Piano keys
        rbx = ttk.Frame(self, padding=(12, 0, 12, 6))
        rbx.pack(fill="x", padx=16)
        ttk.Label(rbx, text="Roblox").pack(side="left")
        self.roblox_var = tk.BooleanVar(value=False)
        self._tip(ttk.Checkbutton(rbx,
                  text="Send to Roblox  (keep the game window focused)",
                  variable=self.roblox_var, command=self._sync_settings),
                  "Turn keystroke output to Roblox on or off. The Roblox window must "
                  "stay focused while you play.").pack(side="left", padx=(8, 0))
        self._tip(ttk.Label(rbx, text="Type:", style="Muted.TLabel"),
                  "Which kind of game you're sending to (see the dropdown).").pack(
                      side="left", padx=(12, 4))
        self.roblox_mode_var = tk.StringVar(value=ROBLOX_MODES[0])
        self.roblox_mode_cb = ttk.Combobox(
            rbx, state="readonly", width=16, values=ROBLOX_MODES,
            textvariable=self.roblox_mode_var)
        self.roblox_mode_cb.pack(side="left")
        self.roblox_mode_cb.bind("<<ComboboxSelected>>", lambda _=None: self._sync_settings())
        self._tip(self.roblox_mode_cb, "MidiConnect: for Piano Rooms / Visual Pianos "
                  "- full velocity and sustain. QWERTY output: for the many "
                  "letter-key piano games - sharps on Shift, sustain on Space.")
        self._tip(ttk.Button(rbx, text="Test", width=6, command=self.on_test_roblox),
                  "Plays a C-major scale into the game so you can confirm the keys "
                  "are landing before you play.").pack(side="left", padx=(8, 0))
        self._tip(ttk.Label(rbx, text="Stop hotkey: F8", style="Muted.TLabel"),
                  "Press F8 at any time to release a stuck key or pedal without "
                  "alt-tabbing out of the game.").pack(side="right")

        # Recording (capture what you play on the piano -> .mid)
        rec = ttk.Frame(self, padding=(12, 0, 12, 6))
        rec.pack(fill="x", padx=16)
        ttk.Label(rec, text="Record").pack(side="left")
        self.record_btn = ttk.Button(rec, text="● Record", command=self.on_record)
        self.record_btn.pack(side="left", padx=(8, 0))
        self._tip(self.record_btn, "Record what you play on the piano to a .mid file "
                  "you can save and reuse.")
        self.record_lbl = ttk.Label(rec, text="idle", style="Muted.TLabel")
        self.record_lbl.pack(side="left", padx=(10, 0))

        # Play MIDI file -> piano
        play = ttk.Frame(self, padding=12)
        play.pack(fill="x", padx=16, pady=6)
        play.columnconfigure(1, weight=1)
        self._tip(ttk.Label(play, text="Play to piano"),
                  "Load a .mid file and play it back out to your piano (and "
                  "optionally to Roblox or other software).").grid(
                      row=0, column=0, sticky="w", padx=(0, 10))
        self.file_lbl = ttk.Label(play, text="No file loaded", style="Muted.TLabel")
        self.file_lbl.grid(row=0, column=1, sticky="w")
        self._tip(ttk.Button(play, text="Load MIDI / Sheet...",
                             command=self.on_load_midi),
                  "Open a .mid file - or sheet music (.musicxml/.mxl from "
                  "MuseScore or a scanning app), which is converted to MIDI "
                  "automatically.").grid(
                      row=0, column=2, padx=(8, 0))
        self.tracks_btn = self._tip(
            ttk.Button(play, text="Tracks...", command=self._open_tracks,
                       state="disabled"),
            "Choose which of the file's tracks play - e.g. practice one hand "
            "while the other is muted.")
        self.tracks_btn.grid(row=0, column=3, padx=(6, 0))
        self.sheet_btn = self._tip(
            ttk.Button(play, text="Sheet music...", command=self._open_sheet,
                       state="disabled"),
            "Transcribe the loaded file into sheet music: saves a .musicxml "
            "(opens in MuseScore) and a browser preview you can read and "
            "print. Best with cleanly sequenced MIDIs; live recordings will "
            "look rough.")
        self.sheet_btn.grid(row=0, column=4, padx=(6, 0))

        row2 = ttk.Frame(play)
        row2.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
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
        self._tip(ttk.Checkbutton(row2, text="Loop", variable=self.loop_var,
                                  command=self._sync_settings),
                  "Repeat the file from the start when it reaches the end.").pack(
                      side="left", padx=(14, 0))
        self.wait_var = tk.BooleanVar(value=False)
        self._tip(ttk.Checkbutton(row2, text="Wait for my notes",
                                  variable=self.wait_var,
                                  command=self._sync_settings),
                  "Practice mode: playback pauses at each note or chord until "
                  "you play it on the connected piano. Nothing is auto-played - "
                  "the waiting keys light amber, each labeled with the exact "
                  "note to press (C#4, A#2, ...).").pack(
                      side="left", padx=(14, 0))

        self._tip(ttk.Label(row2, text="Speed"),
                  "Play the file faster or slower without changing pitch. "
                  "100% = the file's original tempo.").pack(side="left", padx=(16, 4))
        self.tempo_var = tk.IntVar(value=100)
        self._tip(ttk.Scale(row2, from_=50, to=200, variable=self.tempo_var,
                            command=self._on_tempo, length=140),
                  "Playback speed. 100% = original tempo.").pack(side="left")
        self.tempo_lbl = ttk.Label(row2, text="100%", width=5)
        self.tempo_lbl.pack(side="left", padx=(4, 0))

        self.ch1_var = tk.BooleanVar(value=True)
        self._tip(ttk.Checkbutton(row2, text="Send on ch.1", variable=self.ch1_var,
                                  command=self._sync_settings),
                  "Force playback onto MIDI channel 1. Many pianos only respond on "
                  "channel 1, so if file playback seems silent, leave this on.").pack(
                      side="right")
        self.play_out_var = tk.BooleanVar(value=True)
        self._tip(ttk.Checkbutton(row2, text="To output (Synthesia)",
                                  variable=self.play_out_var,
                                  command=self._sync_settings),
                  "Also send the file's notes to the virtual MIDI port (for "
                  "Synthesia, a DAW, etc.), not just to the piano.").pack(
                      side="right", padx=(0, 12))

        prow = ttk.Frame(play)
        prow.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        prow.columnconfigure(0, weight=1)
        self.play_prog = ttk.Progressbar(prow, mode="determinate")
        self.play_prog.grid(row=0, column=0, sticky="ew")
        self.time_lbl = ttk.Label(prow, text="0:00 / 0:00", style="Muted.TLabel",
                                  width=12, anchor="e")
        self.time_lbl.grid(row=0, column=1, padx=(8, 0))

        # Voice finder: the piano's Program-Change->voice map isn't documented,
        # so let the user step through numbers and hear each one.
        vrow = ttk.Frame(play)
        vrow.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.voice_on_var = tk.BooleanVar(value=False)
        self._tip(ttk.Checkbutton(vrow, text="Set piano voice  #",
                                  variable=self.voice_on_var, command=self._on_voice),
                  "Send a Program Change to switch the piano's sound (voice). Use the "
                  "number box and Test voice to find the one you want.").pack(side="left")
        self.voice_num = tk.IntVar(value=0)
        self._tip(ttk.Spinbox(vrow, from_=0, to=15, width=4,
                              textvariable=self.voice_num, command=self._on_voice),
                  "Voice / program number sent to the piano (0-15).").pack(
                      side="left", padx=(4, 8))
        self._tip(ttk.Button(vrow, text="Test voice", command=self.on_test_voice),
                  "Play a short note so you can hear the currently selected "
                  "voice.").pack(side="left")
        self._tip(ttk.Label(vrow, text="BLE interval", style="Muted.TLabel"),
                  "Smallest gap (in ms) between Bluetooth messages sent to the piano. "
                  "Bluetooth can't send faster than this - raise it if a Bluetooth "
                  "piano stutters or drops notes, lower it for tighter timing. "
                  "Ignored over USB.").pack(side="left", padx=(16, 2))
        self.gap_var = tk.IntVar(value=15)
        self._tip(ttk.Spinbox(vrow, from_=5, to=30, width=4, textvariable=self.gap_var,
                              command=self._sync_settings),
                  "Minimum spacing in ms between Bluetooth messages (raise if notes "
                  "drop, lower for tighter timing).").pack(side="left")
        ttk.Label(vrow, text="ms", style="Muted.TLabel").pack(side="left", padx=(2, 0))
        self._tip(ttk.Label(vrow, text="Buffer", style="Muted.TLabel"),
                  "How far ahead (in ms) playback is scheduled. A bigger buffer "
                  "smooths out dense passages but adds a little latency; a smaller "
                  "one feels more immediate.").pack(side="left", padx=(14, 2))
        self.buffer_var = tk.IntVar(value=30)
        self._tip(ttk.Spinbox(vrow, from_=20, to=400, increment=10, width=5,
                              textvariable=self.buffer_var, command=self._sync_settings),
                  "Look-ahead scheduling window in ms (bigger = smoother dense songs "
                  "but more latency).").pack(side="left")
        ttk.Label(vrow, text="ms", style="Muted.TLabel").pack(side="left", padx=(2, 12))
        self.pack_var = tk.BooleanVar(value=True)
        self._tip(ttk.Checkbutton(vrow, text="Pack notes (faster, for dense songs)",
                                  variable=self.pack_var, command=self._sync_settings),
                  "Combines notes that happen at the same time into fewer Bluetooth "
                  "packets - faster for dense songs. Turn off if a piano mis-handles "
                  "packed messages.").pack(side="left")

        # Visualizer: falling-notes lane (during playback) + the 88-key strip
        viz = ttk.Frame(self, padding=12)
        viz.pack(fill="both", expand=True, padx=16, pady=6)
        vhead = ttk.Frame(viz)
        vhead.pack(fill="x", pady=(0, 6))
        self.fall_var = tk.BooleanVar(value=True)
        self._tip(ttk.Checkbutton(vhead, text="Falling notes",
                                  variable=self.fall_var,
                                  command=self._toggle_fall),
                  "Synthesia-style preview: during file playback, upcoming "
                  "notes scroll down to the keys they land on. Blue = right "
                  "hand, green = left (by track).").pack(side="left")
        self.fall = tk.Canvas(viz, height=190, bg="#101218", highlightthickness=0)
        self.fall.pack(fill="x")
        self.fall.bind("<Configure>", lambda e: self._fall_reset())
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

    # -- falling notes ------------------------------------------------------
    FALL_WINDOW = 3.0     # seconds of upcoming music visible in the lane

    def _music_now(self):
        """The GUI's estimate of the playback position, extrapolated between
        the controller's sync events using the wall clock and current tempo."""
        if self._clock_run and self._clock_wall is not None:
            return self._clock_music + (
                time.perf_counter() - self._clock_wall) * (self.tempo_var.get() / 100.0)
        return self._clock_music

    def _clock_set(self, music, running):
        self._clock_music = music
        self._clock_wall = time.perf_counter()
        self._clock_run = bool(running)

    def _toggle_fall(self):
        if self.fall_var.get():
            self.fall.pack(fill="x", before=self.canvas)
            self._fall_reset()
        else:
            self.fall.pack_forget()

    def _fall_reset(self):
        c = self.fall
        c.delete("all")
        self._fall_items.clear()
        self._fall_idx = 0
        self._fall_last_music = None
        self._fall_geom = {}
        w = c.winfo_width()
        if w >= 10:
            for r in piano_layout(w, 1):
                self._fall_geom[r["note"]] = (r["x"], r["w"], r["black"])

    def _fall_prepare(self):
        """Snapshot the spans for the file/filter that is about to play."""
        self._fall_spans = self.controller.note_spans()
        info = self._tracks_meta or self.controller.track_info
        self._fall_right_track = (max(info, key=lambda t: t["avg"])["index"]
                                  if info else None)
        self._fall_reset()

    def _fall_tick(self):
        if not self._playing:
            self._fall_after = None
            return
        self._fall_after = self.after(33, self._fall_tick)
        if not self.fall_var.get():
            return
        c = self.fall
        h = c.winfo_height()
        if h < 10 or not self._fall_geom:
            return
        pps = h / self.FALL_WINDOW
        now = self._music_now()
        last = self._fall_last_music
        self._fall_last_music = now
        if last is None or now < last - 0.5:     # start / loop restart
            c.delete("fall")
            self._fall_items.clear()
            self._fall_idx = 0
            last = now
        dy = (now - last) * pps
        if dy:
            c.move("fall", 0, dy)   # one call moves every falling rectangle
        spans = self._fall_spans
        i = self._fall_idx
        horizon = now + self.FALL_WINDOW + 0.2
        right = self._fall_right_track
        while i < len(spans) and spans[i][0] <= horizon:
            s, e, note, ti = spans[i]
            i += 1
            g = self._fall_geom.get(note)
            if g is None or len(self._fall_items) > 600:  # black-MIDI guard
                continue
            x, w, black = g
            bottom = h - (s - now) * pps
            top = bottom - max(4.0, (e - s) * pps)
            if ti == right or right is None:
                fill, edge = (KEY_ON_BLACK, "#27458f") if black else (ACCENT, "#3b63c4")
            else:
                fill, edge = ("#1f8f6d", "#15654d") if black else (ACCENT2, "#1d8f6d")
            item = c.create_rectangle(x + 1, top, x + w - 1, bottom,
                                      fill=fill, outline=edge, tags="fall")
            self._fall_items.append((item, s, e))
        self._fall_idx = i
        while self._fall_items and self._fall_items[0][2] < now - 0.4:
            c.delete(self._fall_items.popleft()[0])

    def _paint_wait(self, note, on):
        """Amber = 'play this now' (wait-for-notes mode). Each waiting key is
        labeled with its exact note name so sharps are unmistakable."""
        entry = self.key_items.get(note)
        if not entry:
            return
        item, black = entry
        if on:
            self.canvas.itemconfig(item, fill="#cf8f22" if black else "#e0a13c")
            self._wait_notes.add(note)
            if note not in self._wait_labels:
                x0, _y0, x1, y1 = self.canvas.coords(item)
                cx = (x0 + x1) / 2
                if black:
                    tid = self.canvas.create_text(
                        cx, y1 - 12, text=note_name(note), fill="#ffffff",
                        font=("Segoe UI Semibold", 7))
                else:
                    tid = self.canvas.create_text(
                        cx, y1 - 32, text=note_name(note), fill="#3a2c10",
                        font=("Segoe UI Semibold", 8))
                self._wait_labels[note] = tid
        else:
            self._wait_notes.discard(note)
            tid = self._wait_labels.pop(note, None)
            if tid is not None:
                self.canvas.delete(tid)
            self._paint_key(note, note in self.active_notes)

    def _offer_save_converted(self, info):
        """A loaded score was converted to MIDI; offer to keep the .mid."""
        self._append_log(f"Converted sheet music to MIDI: {info['name']} "
                         f"({info['notes']} notes). It's ready to play.")
        if messagebox.askyesno(
                "Sheet music converted",
                "The score was converted to MIDI and is ready to play.\n"
                "Save a .mid copy too?"):
            base = Path(info["name"]).stem or "song"
            path = filedialog.asksaveasfilename(
                title="Save converted MIDI", defaultextension=".mid",
                initialfile=f"{base}.mid",
                filetypes=[("MIDI files", "*.mid"), ("All files", "*.*")])
            if path:
                try:
                    import shutil
                    shutil.copyfile(info["temp_mid"], path)
                    self._append_log(f"Saved: {Path(path).name}")
                except Exception as e:
                    self._append_log(f"Could not save: {e}")

    def _open_sheet(self):
        if not self._tracks_meta:
            messagebox.showinfo("Sheet music", "Load a MIDI file first.")
            return
        base = Path(getattr(self, "_loaded_name", "song")).stem or "song"
        path = filedialog.asksaveasfilename(
            title="Save sheet music", defaultextension=".musicxml",
            initialfile=f"{base}.musicxml",
            filetypes=[("MusicXML", "*.musicxml"), ("All files", "*.*")])
        if not path:
            return
        try:
            xml = self.controller.export_musicxml(base)
            if not xml:
                self._append_log("No tracks selected - nothing to transcribe.")
                return
            Path(path).write_text(xml, encoding="utf-8")
            html_path = str(Path(path).with_suffix("")) + "-sheet.html"
            Path(html_path).write_text(_sheet_html(base, xml), encoding="utf-8")
            self._append_log(f"Sheet music saved: {Path(path).name} "
                             f"(+ browser preview). Opening preview...")
            self._append_log("Tip: open the .musicxml in MuseScore (free) to "
                             "edit or print professionally.")
            webbrowser.open(Path(html_path).as_uri())
        except Exception as e:
            messagebox.showerror("Sheet music failed", str(e))
            self._append_log(f"Sheet music failed: {e}")

    # -- track / hand filter --------------------------------------------------
    def _open_tracks(self):
        info = self._tracks_meta
        if not info:
            messagebox.showinfo("Tracks", "Load a MIDI file first.")
            return
        if getattr(self, "_trk_win", None) and self._trk_win.winfo_exists():
            self._trk_win.lift()
            return
        win = tk.Toplevel(self)
        self._trk_win = win
        win.title("Tracks - choose what plays")
        win.configure(bg=BG, highlightthickness=1,
                      highlightbackground="#3a4257")
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Tick the tracks that should play. Pedal and other "
                            "controls always play.",
                  style="Muted.TLabel", wraplength=390).pack(anchor="w", pady=(0, 6))
        cur = self.controller.track_filter
        self._trk_vars = []
        for t in info:
            v = tk.BooleanVar(value=(cur is None or t["index"] in cur))
            self._trk_vars.append((t["index"], v))
            ttk.Checkbutton(frm, variable=v, command=self._apply_tracks_from_vars,
                            text=(f"{t['name']}  -  {t['notes']} notes, "
                                  f"{note_name(t['lo'])} to {note_name(t['hi'])}")
                            ).pack(anchor="w", pady=2)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(12, 0))
        hands = pick_hand_tracks(info)
        if hands:
            r, l = hands
            self._tip(ttk.Button(btns, text="Right hand only", 
                                 command=lambda: self._apply_tracks({r})),
                      "Play just the higher-pitched track.").pack(side="left")
            self._tip(ttk.Button(btns, text="Left hand only",
                                 command=lambda: self._apply_tracks({l})),
                      "Play just the lower-pitched track.").pack(side="left",
                                                                 padx=(6, 0))
        ttk.Button(btns, text="All tracks",
                   command=lambda: self._apply_tracks(None)).pack(side="left",
                                                                  padx=(6, 0))
        ttk.Button(btns, text="Close",
                   command=win.destroy).pack(side="right")

    def _apply_tracks_from_vars(self):
        sel = {i for i, v in self._trk_vars if v.get()}
        all_idx = {t["index"] for t in self._tracks_meta}
        self._apply_tracks(None if sel == all_idx else sel, update_vars=False)

    def _apply_tracks(self, filt, update_vars=True):
        self.controller.track_filter = filt
        if update_vars:
            for i, v in getattr(self, "_trk_vars", []):
                v.set(filt is None or i in filt)
        if filt is None:
            desc = "all tracks"
        elif not filt:
            desc = "no tracks (everything muted!)"
        else:
            names = {t["index"]: t["name"] for t in self._tracks_meta}
            desc = ", ".join(names.get(i, f"Track {i + 1}") for i in sorted(filt))
        self._append_log(f"Playing: {desc}."
                         + (" Restart playback to apply." if self._playing else ""))

    # -- keyboard drawing ---------------------------------------------------
    def _draw_keyboard(self):
        c = self.canvas
        c.delete("all")
        self.key_items.clear()
        self._wait_labels.clear()   # ids died with delete("all"); repainted below
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10:
            return
        mc = None
        for r in piano_layout(w, h):
            if r["black"]:
                continue
            item = c.create_rectangle(r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"],
                                      fill=KEY_WHITE, outline=KEY_WHITE_EDGE)
            self.key_items[r["note"]] = (item, False)
            if r["note"] == 60:
                mc = r
        for r in piano_layout(w, h):
            if not r["black"]:
                continue
            item = c.create_rectangle(r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"],
                                      fill=KEY_BLACK, outline="#0c0d11")
            self.key_items[r["note"]] = (item, True)
        if mc is not None:
            # Mark middle C (C4) like the dot on many digital pianos, so the
            # middle of the keyboard is obvious at a glance.
            cx = mc["x"] + mc["w"] / 2
            c.create_text(cx, h - 20, text="C4", fill="#767c8c",
                          font=("Segoe UI", 7))
            c.create_oval(cx - 3.5, h - 13, cx + 3.5, h - 6,
                          fill=MUTED, outline="")
        for n in self.active_notes:
            self._paint_key(n, True)
        for n in list(self._wait_notes):
            self._paint_wait(n, True)

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
            for n in list(self._wait_notes):
                self._paint_wait(n, False)
        elif kind == "play_state":
            playing = ev[1] == "playing"
            self._playing = playing
            self.play_btn.configure(state="disabled" if playing else "normal")
            self.pause_btn.configure(state="normal" if playing else "disabled",
                                     text="Pause")
            self.stop_btn.configure(state="normal" if playing else "disabled")
            if playing:
                self._fall_prepare()
                self._clock_set(0.0, True)
                if self._fall_after is None:
                    self._fall_after = self.after(33, self._fall_tick)
            if ev[1] == "stopped":
                self._clock_set(0.0, False)
                self.fall.delete("fall")
                self._fall_items.clear()
                self._fall_idx = 0
                self._fall_last_music = None
                self.play_prog["value"] = 0
                self.time_lbl.configure(text=f"0:00 / {self._fmt_time(self._midi_len)}")
        elif kind == "play_clock":
            _, music, running = ev
            self._clock_set(music, running)
        elif kind == "wait_on":
            self._paint_wait(ev[1], True)
        elif kind == "wait_off":
            self._paint_wait(ev[1], False)
        elif kind == "play_progress":
            _, pos, total = ev
            self._clock_set(pos, self._clock_run)   # periodic resync
            self.play_prog["maximum"] = max(0.001, total)
            self.play_prog["value"] = min(pos, total)
            self.time_lbl.configure(
                text=f"{self._fmt_time(pos)} / {self._fmt_time(total)}")
        elif kind == "midi_loaded":
            info = ev[1]
            if info.get("converted_from_score"):
                self._offer_save_converted(info)
            self._tracks_meta = info.get("tracks", [])
            self.tracks_btn.configure(
                state="normal" if len(self._tracks_meta) > 1 else "disabled")
            self.sheet_btn.configure(
                state="normal" if self._tracks_meta else "disabled")
            self._loaded_name = info["name"]
            self.file_lbl.configure(
                text=f"{info['name']}  -  {info['notes']} notes, {info['length']:.0f}s")
            self._midi_len = info['length']
            self.time_lbl.configure(text=f"0:00 / {self._fmt_time(self._midi_len)}")
            self.play_btn.configure(state="normal")
            self._append_log(f"Loaded {info['name']}")
        elif kind == "midi_load_failed":
            self.file_lbl.configure(text="No file loaded")
            messagebox.showerror("Could not load MIDI", ev[1])
            self._append_log(f"MIDI load failed: {ev[1]}")
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
            title="Choose a MIDI file or sheet music",
            filetypes=[("MIDI & sheet music", "*.mid *.midi *.musicxml *.mxl *.xml"),
                       ("MIDI files", "*.mid *.midi"),
                       ("Sheet music (MusicXML)", "*.musicxml *.mxl *.xml"),
                       ("All files", "*.*")])
        if not path:
            return
        self.file_lbl.configure(text=f"Loading {Path(path).name}...")
        self.controller.load_midi_async(path)

    def on_play(self):
        self.controller.play()

    def on_pause(self):
        paused = self.controller.pause_toggle()
        self.pause_btn.configure(text="Resume" if paused else "Pause")
        self._clock_set(self._music_now(), not paused and self._playing)

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
        if self._clock_wall is not None:
            self._clock_set(self._music_now(), self._clock_run)

    def _auto_connect(self):
        # Auto-connect only the saved Bluetooth piano (USB ports may move around).
        if not self._source_is_ble():
            return
        addr = self.cfg.get("last_address")
        if addr:
            self._sync_settings()
            self.controller.connect("ble", -1, addr, self._selected_output())

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
        next_enabled = self.roblox_var.get()
        next_mode = ("keyboard" if self.roblox_mode_var.get() == ROBLOX_MODES[1]
                     else "midiconnect")
        if self.controller.roblox.enabled and (
                not next_enabled or self.controller.roblox.mode != next_mode):
            self.controller.roblox.release_all()
        self.controller.roblox.enabled = next_enabled
        if self.roblox_mode_var.get() == ROBLOX_MODES[1]:
            self.controller.roblox.mode = "keyboard"
            if not self.controller.roblox.kbd_map:
                self.controller.roblox.set_keyboard_map(build_keyboard_map())
        else:
            self.controller.roblox.mode = "midiconnect"
        self.controller.loop_play = self.loop_var.get()
        self.controller.wait_mode = self.wait_var.get()
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
        line("Tip: hover your mouse over any control in the app to see a short "
             "explanation of what it does.", "b")

        head("Practice features")
        line("Falling notes - during file playback, upcoming notes scroll down "
             "to the keys they land on (blue = right hand, green = left, by "
             "track). Toggle it with the checkbox above the keyboard.")
        line("Tracks... - after loading a file, choose which tracks play. For "
             "the usual two-track piano files there are one-click Right hand / "
             "Left hand buttons, so you can practice one hand while the other "
             "is muted. Pedal always plays.")
        line("Sheet music in - 'Load MIDI / Sheet...' also opens MusicXML scores "
             "(.musicxml / .mxl, what MuseScore and sheet-scanning apps "
             "produce). The score is converted to MIDI on the spot: play it "
             "on the piano or in Roblox, practice it with Wait mode, and "
             "optionally save it as a .mid. For paper sheet music, scan it "
             "with an app like Audiveris or PlayScore first - they output "
             "MusicXML this can open.")
        line("Sheet music... - transcribes the loaded file into notation: "
             "saves a .musicxml (open it in the free MuseScore to edit or "
             "print professionally) plus a browser preview you can read and "
             "print right away. Detects keys (including mid-piece "
             "changes), eighth-note triplets, "
             "dynamics, and legato phrase slurs; writes pedal marks, tempo, "
             "proper stems, beams, ties, rehearsal letters, and glissando "
             "lines, and keeps held notes as a second voice. Honors the track filter. Best with cleanly "
             "sequenced MIDIs - free-time live recordings will look rough.")
        line("Wait for my notes - playback pauses at every note or chord "
             "until you play it on your connected piano, then moves on. The "
             "waiting keys light amber and each is labeled with its exact note "
             "name, so a C#4 can never be mistaken for a C4. Nothing is "
             "auto-played: you play the piece, the app turns the pages. Works "
             "over Bluetooth or USB.")

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
             "Roblox', focus the game, and play. Each note holds a letter or number "
             "key until you release the piano key; sharps use Shift, and the "
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
