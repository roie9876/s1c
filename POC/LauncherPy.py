import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import ctypes
from ctypes import wintypes


DEFAULT_API_BASE_URL = "https://s1c-function-11729.azurewebsites.net/api"
DEFAULT_SMARTCONSOLE_PATH = r"C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM\SmartConsole.exe"
DEFAULT_SMARTCONSOLE_DIR = r"C:\Program Files (x86)\CheckPoint\SmartConsole\R82\PROGRAM"


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def ensure_dir(path: str, log) -> None:
    if not path:
        return
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as exc:
        log(f"Ensure-Dir failed path='{path}' err='{exc}'")


def bootstrap_user_profile(log) -> None:
    # One-time bootstrap for RemoteApp-only users.
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local")
    sentinel_dir = os.path.join(local_appdata, "s1c")
    sentinel_file = os.path.join(sentinel_dir, "profile_bootstrap_v1.done")

    if os.path.exists(sentinel_file):
        log(f"Bootstrap already done: {sentinel_file}")
        return

    ensure_dir(sentinel_dir, log)

    # Touch common folders
    candidates = [
        os.environ.get("USERPROFILE"),
        os.environ.get("APPDATA"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("TEMP"),
        os.environ.get("TMP"),
        os.path.join(os.environ.get("USERPROFILE", ""), "Documents"),
    ]
    for p in [c for c in candidates if c and c.strip()]:
        ensure_dir(p, log)

    # Best-effort: common Check Point folders
    for p in [
        os.path.join(os.environ.get("APPDATA", ""), "Check Point"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Check Point"),
        os.path.join(os.environ.get("APPDATA", ""), "CheckPoint"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "CheckPoint"),
    ]:
        if p and p.strip():
            ensure_dir(p, log)

    try:
        with open(sentinel_file, "w", encoding="utf-8") as f:
            f.write(_now_iso())
        log(f"Bootstrap complete: {sentinel_file}")
    except Exception as exc:
        log(f"Failed writing sentinel: {exc}")


def detect_user_id(log) -> str:
    try:
        completed = subprocess.run(
            ["whoami", "/upn"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        upn = (completed.stdout or "").strip()
        if upn:
            log(f"Detected userId via whoami /upn: {upn}")
            return upn
    except Exception as exc:
        log(f"whoami /upn failed: {exc}")

    fallback = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    log(f"Detected userId via fallback: {fallback}")
    return fallback


def http_get_json(url: str, timeout_s: int, log):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc)
        return exc.code, body
    except Exception as exc:
        log(f"HTTP request failed: {exc}")
        raise


def is_image_running(image_name: str) -> bool:
    """Best-effort process check without external deps (uses tasklist)."""
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        out = (completed.stdout or "") + "\n" + (completed.stderr or "")
        return image_name.lower() in out.lower()
    except Exception:
        return False


def try_find_window_handle_by_title(substr: str) -> int:
    """Finds the first visible top-level window whose title contains substr (case-insensitive)."""
    user32 = ctypes.windll.user32

    EnumWindows = user32.EnumWindows
    EnumWindows.argtypes = [wintypes.WNDPROC, wintypes.LPARAM]
    EnumWindows.restype = wintypes.BOOL

    IsWindowVisible = user32.IsWindowVisible
    IsWindowVisible.argtypes = [wintypes.HWND]
    IsWindowVisible.restype = wintypes.BOOL

    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetWindowTextLengthW.argtypes = [wintypes.HWND]
    GetWindowTextLengthW.restype = ctypes.c_int

    GetWindowTextW = user32.GetWindowTextW
    GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    GetWindowTextW.restype = ctypes.c_int

    target = (substr or "").lower()
    found = {"hwnd": 0}

    @wintypes.WNDPROC
    def enum_proc(hwnd, lparam):
        try:
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, len(buf))
            title = (buf.value or "").strip()
            if title and target in title.lower():
                found["hwnd"] = int(hwnd)
                return False
        except Exception:
            return True
        return True

    EnumWindows(enum_proc, 0)
    return int(found["hwnd"]) if found["hwnd"] else 0


def bring_window_to_foreground(hwnd: int) -> None:
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    try:
        # SW_RESTORE=9
        user32.ShowWindowAsync(wintypes.HWND(hwnd), 9)
    except Exception:
        pass
    try:
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
    except Exception:
        pass


def send_vk(vk: int) -> None:
    user32 = ctypes.windll.user32

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.ULONG_PTR),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]

    down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0))
    up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0))
    user32.SendInput(2, ctypes.byref((down, up)), ctypes.sizeof(INPUT))


def send_text_unicode(text: str) -> None:
    user32 = ctypes.windll.user32

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.ULONG_PTR),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]

    inputs = []
    for ch in text or "":
        code = ord(ch)
        inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)))
        inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)))

    if not inputs:
        return
    arr_type = INPUT * len(inputs)
    arr = arr_type(*inputs)
    user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))


def try_autofill_smartconsole(username: str | None, target_ip: str | None, log) -> bool:
    """Best-effort: focus SmartConsole window and type Username + Server/IP (leave password blank)."""
    if not username and not target_ip:
        return False

    # Heuristic: locate the SmartConsole login window by title.
    for _ in range(60):
        hwnd = try_find_window_handle_by_title("SmartConsole")
        if hwnd:
            bring_window_to_foreground(hwnd)
            time.sleep(0.75)

            # Type username, then tab to password, tab to server field, then type server.
            # This matches typical SmartConsole login tab order.
            try:
                if username:
                    send_text_unicode(str(username))
                time.sleep(0.1)
                send_vk(0x09)  # VK_TAB
                time.sleep(0.1)
                send_vk(0x09)  # VK_TAB
                time.sleep(0.1)
                if target_ip:
                    send_text_unicode(str(target_ip))
                log("Autofill attempted via SendInput")
                return True
            except Exception as exc:
                log(f"Autofill failed: {exc}")
                return False

        time.sleep(0.5)

    log("Autofill skipped: SmartConsole window not found")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="S1C Python launcher (PowerShell-free).")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--override-user", default="")
    parser.add_argument("--smartconsole-path", default=DEFAULT_SMARTCONSOLE_PATH)
    parser.add_argument("--smartconsole-dir", default=DEFAULT_SMARTCONSOLE_DIR)
    parser.add_argument("--http-timeout", type=int, default=15)
    parser.add_argument(
        "--with-args",
        action="store_true",
        help="Pass best-effort -u/-s args to SmartConsole (some builds may exit immediately)",
    )
    parser.add_argument(
        "--no-autofill",
        action="store_true",
        help="Disable UI autofill (username + server/IP) via SendInput",
    )
    parser.add_argument("--wait-seconds-if-no-request", type=int, default=0, help="If >0, wait before exit when no request found")
    args = parser.parse_args()

    temp_dir = os.path.join(os.environ.get("TEMP", os.getcwd()), "s1c-launcher")
    ensure_dir(temp_dir, lambda _: None)
    log_path = os.path.join(temp_dir, "LauncherPy.log")

    def log(msg: str) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{_now_iso()}] {msg}\n")
        except Exception:
            pass

    log("LauncherPy started")
    log(f"host={os.environ.get('COMPUTERNAME','')} session={os.environ.get('SESSIONNAME','')} user={os.environ.get('USERNAME','')}")

    bootstrap_user_profile(log)

    if args.override_user and args.override_user.strip():
        user_id = args.override_user.strip()
        log(f"Using overridden userId: {user_id}")
    else:
        user_id = detect_user_id(log)

    fetch_url = f"{args.api_base_url.rstrip('/')}/fetch_connection?{urllib.parse.urlencode({'userId': user_id})}"
    print(f"[INFO] Polling API: {fetch_url}")
    log(f"Polling API: {fetch_url}")

    status, body = http_get_json(fetch_url, timeout_s=args.http_timeout, log=log)
    if status == 404:
        print(f"[INFO] No pending connection requests for user {user_id}.")
        log("No pending request (404)")
        if args.wait_seconds_if_no_request > 0:
            time.sleep(args.wait_seconds_if_no_request)
        return 0

    if status != 200:
        print(f"[ERROR] API returned status {status}: {body}")
        log(f"API error status={status} body={body}")
        time.sleep(5)
        return 1

    try:
        payload = json.loads(body)
    except Exception as exc:
        print(f"[ERROR] Failed to parse API response as JSON: {exc}")
        log(f"JSON parse failed: {exc} body={body}")
        time.sleep(5)
        return 1

    target_ip = payload.get("targetIp")
    username = payload.get("username")

    print("[SUCCESS] Connection Request Found!")
    print(f"    Target: {target_ip}")
    print(f"    User:   {username}")
    log(f"Connection found. targetIp={target_ip} username={username}")

    if not os.path.exists(args.smartconsole_path):
        print(f"[ERROR] SmartConsole not found at: {args.smartconsole_path}")
        log(f"SmartConsole not found at: {args.smartconsole_path}")
        time.sleep(10)
        return 1

    # Default: start SmartConsole with no args (most compatible).
    # Some SmartConsole builds exit immediately if passed unsupported args.
    cmd = [args.smartconsole_path]
    if args.with_args:
        # Best-effort prefill without password.
        if username:
            cmd += ["-u", str(username)]
        if target_ip:
            cmd += ["-s", str(target_ip)]

    log(f"Launching SmartConsole: {cmd}")
    try:
        proc = subprocess.Popen(cmd, cwd=args.smartconsole_dir or None)
    except Exception as exc:
        print(f"[ERROR] Failed to start SmartConsole: {exc}")
        log(f"Failed to start SmartConsole: {exc}")
        time.sleep(10)
        return 1

    # Best-effort autofill (username + server/IP). Leave password blank.
    if not args.no_autofill:
        try:
            did = try_autofill_smartconsole(username=username, target_ip=target_ip, log=log)
            if did:
                print("[INFO] Prefilled username/server; please type password and click Login.")
            else:
                print("[WARN] Could not prefill fields; enter username/server manually.")
        except Exception as exc:
            log(f"Autofill exception: {exc}")

    # SmartConsole sometimes spawns a child process then the parent exits quickly.
    # For RemoteApp, we must keep this launcher process alive while SmartConsole is open.
    time.sleep(5)
    if proc.poll() is not None:
        rc = proc.returncode
        log(f"SmartConsole parent exited quickly rc={rc}")

        # If SmartConsole UI is still running under a different process, wait on it.
        if is_image_running("SmartConsole.exe"):
            print("[INFO] SmartConsole is running (child process); keeping launcher alive...")
            log("Detected SmartConsole.exe still running; entering wait loop")
            while is_image_running("SmartConsole.exe"):
                time.sleep(2)
            log("SmartConsole.exe no longer running")
            return 0

        print(f"[WARN] SmartConsole exited quickly (rc={rc}).")
        print("       Check %TEMP%\\s1c-launcher\\LauncherPy.log and Windows Event Viewer (Application).")
        return 1

    print("[INFO] Waiting for SmartConsole to exit...")
    rc = proc.wait()
    log(f"SmartConsole exited rc={rc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
