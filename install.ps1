# Dikte installer for Windows: dependency check, launcher, shortcuts.
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 "Ctrl+Alt+Space"
#
# There is no shortcut registry to write to here, the way there is on KDE: the
# combination is registered with Windows by Dikte itself while it runs. So the
# shortcut argument is written into the settings rather than into the system,
# and it takes effect the next time Dikte starts.

param([string]$Shortcut = "")

$ErrorActionPreference = "Stop"

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BinDir = Join-Path $env:LOCALAPPDATA "Programs\dikte"
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$Startup = Join-Path $StartMenu "Startup"

function Say  { param($m) Write-Host "  $m" }
function Ok   { param($m) Write-Host "  " -NoNewline; Write-Host "OK" -ForegroundColor Green -NoNewline; Write-Host " $m" }
function Warn { param($m) Write-Host "  " -NoNewline; Write-Host "!" -ForegroundColor Yellow -NoNewline; Write-Host "  $m" }

Write-Host ""
Write-Host "Installing Dikte"
Write-Host "----------------"

# 1. Python and PyQt6 ------------------------------------------------------
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Warn "python.exe is not on PATH. Install Python 3.11 or newer from python.org"
    Say  "or the Microsoft Store, then run this again."
    exit 1
}
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }
Ok "Python: $python"

& $python -c "import PyQt6.QtWidgets" 2>$null
if ($LASTEXITCODE -ne 0) {
    Warn "PyQt6 is missing. Installing it now."
    & $python -m pip install --user PyQt6
    if ($LASTEXITCODE -ne 0) { Warn "pip install PyQt6 failed; install it by hand."; exit 1 }
}
Ok "PyQt6 present"

# 2. ffmpeg ----------------------------------------------------------------
# It is not optional here the way it is on Linux: ffmpeg is what records the
# microphone on Windows, not only what reads audio files.
if (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) {
    Ok "ffmpeg present (recording, and audio files)"
} else {
    Warn "ffmpeg not found. Dikte records through it, so nothing will record."
    Say  "  winget install Gyan.FFmpeg"
    Say  "Then open a new terminal so PATH is picked up."
}

# 3. whisper.cpp -----------------------------------------------------------
# Its own step because a setup that transcribes through OpenAI or OpenRouter
# does not need it at all.
if (Get-Command whisper-server.exe -ErrorAction SilentlyContinue) {
    Ok "whisper.cpp present (local speech to text)"
    Say "Download a model in Settings -> API and models."
} else {
    Warn "whisper-server.exe not found: local speech to text will not run"
    Say  "Download a whisper.cpp release from"
    Say  "  https://github.com/ggml-org/whisper.cpp/releases"
    Say  "and either put its folder on PATH or point Settings -> Local whisper"
    Say  "at whisper-server.exe. Or pick OpenAI/OpenRouter under Settings."
}

# 4. Recording what the speakers play --------------------------------------
# Only meetings need this, and only Windows makes it a question: there is no
# monitor source here the way there is on PipeWire.
$loopback = & $python -c "import sys; sys.path.insert(0, r'$Dir'); import audio; print(audio.default_monitor())" 2>$null
if ($loopback) {
    Ok "A loopback device is available (meeting recording)"
} else {
    Warn "No loopback device: a meeting cannot record the other participants."
    Say  "Turn on 'Stereo Mix' under Sound -> Recording (right click ->"
    Say  "Show disabled devices), or install a virtual cable such as VB-CABLE."
    Say  "Dictation does not need this."
}

# 5. The dikte command -----------------------------------------------------
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$launcher = Join-Path $BinDir "dikte.cmd"
# Bare `dikte` starts the tray application and lets the terminal go; `dikte
# quit` and the rest are one-shot commands, and stay attached so they can print.
@"
@echo off
if "%~1"=="" (
  start "" "$pythonw" "$Dir\dikte.py"
) else (
  "$python" "$Dir\dikte.py" %*
)
"@ | Set-Content -Path $launcher -Encoding ASCII
Ok "Command installed: $launcher"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$BinDir", "User")
    Ok "Added to your PATH (open a new terminal for it to take)"
}

# 6. Start menu and autostart ----------------------------------------------
function New-Shortcut {
    param($Path, $Target, $Arguments, $WorkingDir)
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Path)
    $link.TargetPath = $Target
    $link.Arguments = $Arguments
    $link.WorkingDirectory = $WorkingDir
    $link.Description = "Voice dictation: record, transcribe, clean up, paste"
    $link.Save()
}

New-Shortcut -Path (Join-Path $StartMenu "Dikte.lnk") `
             -Target $pythonw -Arguments "`"$Dir\dikte.py`"" -WorkingDir $Dir
Ok "Start menu entry added"

New-Shortcut -Path (Join-Path $Startup "Dikte.lnk") `
             -Target $pythonw -Arguments "`"$Dir\dikte.py`"" -WorkingDir $Dir
Ok "Will start automatically on login"

# 7. The shortcut ----------------------------------------------------------
if ($Shortcut) {
    & $python -c @"
import sys
sys.path.insert(0, r'$Dir')
import config
conf = config.Config()
conf['shortcut'] = '$Shortcut'
conf['evdev_hotkey'] = True
conf.save()
"@
    if ($LASTEXITCODE -eq 0) { Ok "Shortcut saved: $Shortcut" }
    else { Warn "Could not write the shortcut; set it under Settings -> Shortcut." }
} else {
    Ok "Shortcut: Ctrl+Space, changed under Settings -> Shortcut"
}
Say "Dikte registers the combination with Windows while it runs, so it works"
Say "as soon as it starts. No logout, and nothing else on the desktop sees the"
Say "key while Dikte holds it."

Write-Host ""
Ok "Done. Start it with:  dikte"
Say "The settings window opens on first run: download a whisper.cpp model for"
Say "speech to text, and add an OpenRouter or DeepSeek key for the cleanup step."
Write-Host ""
