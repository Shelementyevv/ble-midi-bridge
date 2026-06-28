@echo off
REM ===================================================================
REM  Build Shelementyev's BLE-MIDI Bridge into a standalone Windows .exe
REM  Just double-click this file (or run it in PowerShell).
REM ===================================================================

echo Installing build dependencies...
pip install --upgrade bleak python-rtmidi mido pydirectinput pynput pyinstaller

echo.
echo Building the executable (this can take a minute or two)...
pyinstaller --onefile --windowed --clean ^
  --name "Shelementyevs-BLE-MIDI-Bridge" ^
  --collect-all bleak ^
  --collect-all winrt ^
  --copy-metadata mido ^
  --collect-all pynput ^
  ble_midi_bridge_gui.py

echo.
echo ===================================================================
echo  Done. Your app is here:   dist\Shelementyevs-BLE-MIDI-Bridge.exe
echo  You can move that single .exe anywhere and double-click it.
echo ===================================================================
pause
