"""Exercise the shipped ZIP with developer runtimes removed from PATH."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    archive = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist/FinAgent-Windows-x64.zip")
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="portable-smoke-", dir=scratch)) / "中文 空格"
    with zipfile.ZipFile(archive) as bundle:
        names = [Path(name) for name in bundle.namelist()]
        assert all(not path.is_absolute() and ".." not in path.parts for path in names)
        assert all(not {"var", ".git", ".venv", "node_modules"} & set(p.parts) for p in names)
        assert all(p.name not in {".env", "codex-owner.txt", "auth-secret.txt"} for p in names)
        assert all(p.suffix not in {".db", ".sqlite", ".sqlite3", ".log"} for p in names)
        bundle.extractall(destination)
    package = destination / "FinAgent-Windows-x64"
    executable = package / "runtime/python.exe"
    windowless = package / "runtime/pythonw.exe"
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PATHEXT",
    }}
    env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
    # These must not affect the portable app or redirect its data to another install.
    env["PYTHONPATH"] = str(ROOT / "src")
    env["FIN_AGENT__DATABASE__URL"] = "invalid-inherited-setting"
    env["FIN_AGENT__CODEX__ENABLED"] = "true"
    common = {
        "cwd": str(destination), "env": env, "creationflags": subprocess.CREATE_NO_WINDOW,
    }
    subprocess.run([str(executable), "-B", "-c", (
        "import sys; from pathlib import Path; "
        "root=Path(sys.executable).resolve().parent.parent; "
        "assert all(Path(p).is_relative_to(root) for p in sys.path); "
        "import numpy, pandas, bcrypt, curl_cffi, akshare, yfinance; "
        "from py_mini_racer import MiniRacer; "
        "assert MiniRacer().eval('1+1')==2; "
        "print('Bundled Python, imports and native DLLs: PASS')"
    )], check=True, **common)
    opener = build_opener(ProxyHandler({}))
    state_path = package / "var/portable.json"
    processes = []

    def start():
        process = subprocess.Popen([
            str(windowless), "-B", "-m", "fin_agent.interfaces.portable", "--no-browser",
        ], **common)
        processes.append(process)
        return process

    def request(state, path, *, method="GET", body=None, token=None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            f"http://127.0.0.1:{state['port']}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers, method=method,
        )
        with opener.open(req, timeout=5) as response:
            return response.read().decode("utf-8")

    def ready(process):
        for _ in range(120):
            assert process.poll() is None, (
                "Portable startup failed:\n" + (package / "var/portable.log").read_text("utf-8")
            )
            try:
                state = json.loads(state_path.read_text("utf-8"))
                request(state, "/_portable/status", token=state["token"])
                return state
            except (OSError, URLError, ValueError):
                time.sleep(0.5)
        raise AssertionError("Portable startup timed out")

    def stop(process):
        subprocess.run([
            str(windowless), "-B", "-m", "fin_agent.interfaces.portable",
            "--stop", "--no-browser",
        ], check=True, timeout=20, **common)
        assert process.wait(timeout=20) == 0
        assert not state_path.exists()

    port_guard = socket.socket()
    try:
        # Exercise the fallback without stopping any application on this computer.
        try:
            port_guard.bind(("127.0.0.1", 8765))
            port_guard.listen()
        except OSError:
            pass  # The port is already occupied, which exercises the same branch.
        first = start()
        state = ready(first)
        assert state["port"] != 8765
        request(state, "/healthz")
        assert json.loads(request(state, "/v1/local/setup/status"))["configured"]
        try:
            request(state, "/v1/local/setup", method="POST",
                    body={"api_key": "offline-test-not-a-real-key"})
        except HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("Portable app accepted a system key")
        assert not (package / ".env").exists()
        page = request(state, "/")
        asset = re.search(r'src="(/assets/[^"]+\.js)"', page)
        assert asset and request(state, asset[1])
        try:
            request(state, "/_portable/stop", method="POST")
        except HTTPError as exc:
            assert exc.code == 403
        else:
            raise AssertionError("Unauthenticated shutdown was accepted")
        account = json.loads(request(state, "/v1/auth/register", method="POST", body={
            "username": "portable_test", "email": "portable@example.com",
            "password": "portable-test-only-2026",
        }))
        request(state, "/v1/auth/me", token=account["access_token"])
        request(state, "/v1/research/jobs", token=account["access_token"])
        secret = (package / "var/auth-secret.txt").read_text("utf-8")
        assert len(secret) == 64
        duplicate = start()
        assert duplicate.wait(timeout=15) == 0
        assert json.loads(state_path.read_text("utf-8")) == state
        stop(first)
        second = start()
        restarted = ready(second)
        assert restarted["token"] != state["token"]
        assert (package / "var/auth-secret.txt").read_text("utf-8") == secret
        request(restarted, "/v1/auth/login", method="POST", body={
            "login_name": "portable_test", "password": "portable-test-only-2026",
        })
        request(restarted, "/v1/auth/me", token=account["access_token"])
        stop(second)
        print("Portable ZIP: PASS (isolated runtime, Chinese/space path, assets, account, "
              "restart, duplicate launch, busy port, authorized stop)", flush=True)
        print(f"Inspection directory: {package}", flush=True)
    finally:
        port_guard.close()
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
