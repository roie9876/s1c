<#
.SYNOPSIS
  Resets Windows Console (conhost) input mode when typing doesn't work.

.DESCRIPTION
  Some apps can accidentally disable console input flags (e.g., echo/proc input),
  causing symptoms like: Enter works, but letters don't appear; Ctrl+C prints ^C.

  Run this in the affected console, or right-click the file and choose
  "Run with PowerShell" to reset the console input mode.
#>

$ErrorActionPreference = 'SilentlyContinue'

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ConsoleModeNative {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern IntPtr GetStdHandle(int nStdHandle);

  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);

  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
}
"@

$STD_INPUT_HANDLE = -10
$hIn = [ConsoleModeNative]::GetStdHandle($STD_INPUT_HANDLE)

$mode = 0
if (-not [ConsoleModeNative]::GetConsoleMode($hIn, [ref]$mode)) {
  Write-Host "[WARN] Not attached to a console (or cannot read mode)." -ForegroundColor Yellow
  exit 0
}

# Input mode flags (Windows Console API)
$ENABLE_PROCESSED_INPUT   = 0x0001
$ENABLE_LINE_INPUT        = 0x0002
$ENABLE_ECHO_INPUT        = 0x0004
$ENABLE_WINDOW_INPUT      = 0x0008
$ENABLE_MOUSE_INPUT       = 0x0010
$ENABLE_INSERT_MODE       = 0x0020
$ENABLE_QUICK_EDIT_MODE   = 0x0040
$ENABLE_EXTENDED_FLAGS    = 0x0080
$ENABLE_AUTO_POSITION     = 0x0100

# Ensure Extended flags is set before enabling QuickEdit.
$desired = $mode
$desired = $desired -bor $ENABLE_EXTENDED_FLAGS
$desired = $desired -bor $ENABLE_PROCESSED_INPUT
$desired = $desired -bor $ENABLE_LINE_INPUT
$desired = $desired -bor $ENABLE_ECHO_INPUT
$desired = $desired -bor $ENABLE_WINDOW_INPUT
$desired = $desired -bor $ENABLE_MOUSE_INPUT
$desired = $desired -bor $ENABLE_INSERT_MODE
$desired = $desired -bor $ENABLE_QUICK_EDIT_MODE
$desired = $desired -bor $ENABLE_AUTO_POSITION

[ConsoleModeNative]::SetConsoleMode($hIn, [uint32]$desired) | Out-Null

try { [Console]::TreatControlCAsInput = $false } catch {}

Write-Host "[OK] Console input mode reset." -ForegroundColor Green
Write-Host "     oldMode=$mode newMode=$desired" -ForegroundColor DarkGray
