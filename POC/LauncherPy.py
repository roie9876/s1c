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


def main() -> int:
    parser = argparse.ArgumentParser(description="S1C Python launcher (PowerShell-free).")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--override-user", default="")
    parser.add_argument("--smartconsole-path", default=DEFAULT_SMARTCONSOLE_PATH)
    parser.add_argument("--smartconsole-dir", default=DEFAULT_SMARTCONSOLE_DIR)
    parser.add_argument("--http-timeout", type=int, default=15)
    parser.add_argument("--no-smartconsole-args", action="store_true", help="Do not pass -u/-s args to SmartConsole")
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

    cmd = [args.smartconsole_path]
    if not args.no_smartconsole_args:
        # Try to prefill without passing password.
        # If SmartConsole ignores these flags, user can still type manually.
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

    print("[INFO] Waiting for SmartConsole to exit...")
    rc = proc.wait()
    log(f"SmartConsole exited rc={rc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
