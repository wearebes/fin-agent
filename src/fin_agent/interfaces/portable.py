"""Windows portable entry point. Uses only the bundled runtime and local data."""

import argparse
import ctypes
import json
import os
import secrets
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "var"
STATE = DATA / "portable.json"


def read_state() -> dict:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if (
            type(state.get("port")) is int
            and 1024 <= state["port"] <= 65535
            and isinstance(state.get("token"), str)
            and len(state["token"]) == 64
        ):
            return state
    except (OSError, ValueError, AttributeError):
        pass
    return {}


def control(state: dict, action: str) -> bool:
    if not state:
        return False
    request = Request(
        f"http://127.0.0.1:{state['port']}/_portable/{action}",
        headers={"Authorization": f"Bearer {state['token']}"},
        method="POST" if action == "stop" else "GET",
    )
    try:
        # Local control must not go through a system proxy.
        with build_opener(ProxyHandler({})).open(request, timeout=2) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def notify(message: str, *, quiet: bool) -> None:
    if quiet:
        if sys.stdout and not sys.stdout.closed:
            print(message, flush=True)
    else:
        ctypes.windll.user32.MessageBoxW(None, message, "FinAgent", 0x40)


def serve(*, no_browser: bool) -> None:
    import msvcrt

    DATA.mkdir(exist_ok=True)
    with (DATA / "portable.lock").open("a+b") as lock:
        if lock.seek(0, 2) == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            for _ in range(60):
                state = read_state()
                if control(state, "status"):
                    if not no_browser:
                        webbrowser.open(f"http://127.0.0.1:{state['port']}/")
                    return
                time.sleep(0.5)
            raise RuntimeError(
                "已有 FinAgent 正在启动。请查看 var/portable.log，或稍后重试。"
            ) from None
        try:
            run_server(no_browser=no_browser)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def run_server(*, no_browser: bool) -> None:
    # Do not inherit another installation's provider credentials or settings.
    for key in list(os.environ):
        if key.startswith("FIN_AGENT__"):
            del os.environ[key]
    os.environ["FIN_AGENT__RUNTIME__ALLOW_SYSTEM_MODEL"] = "false"
    os.environ["FIN_AGENT__CODEX__ENABLED"] = "false"
    os.chdir(ROOT)

    import uvicorn
    from fastapi import HTTPException, Request
    from fastapi.routing import APIRoute

    from fin_agent.bootstrap.app import create_app
    from fin_agent.bootstrap.settings import AppSettings

    secret_path = DATA / "auth-secret.txt"
    try:
        with secret_path.open("x", encoding="utf-8") as handle:
            handle.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    secret = secret_path.read_text(encoding="utf-8").strip()
    if len(secret) < 32:
        raise RuntimeError("var/auth-secret.txt 不完整，请从备份恢复该文件。")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise RuntimeError("缺少网页文件，请完整解压 FinAgent 压缩包后再启动。")
    settings = AppSettings(_env_file=None, auth={"secret_key": secret})
    app = create_app(settings)
    token = secrets.token_hex(32)

    def authorize(request: Request) -> None:
        if not secrets.compare_digest(
            request.headers.get("authorization", ""), f"Bearer {token}"
        ):
            raise HTTPException(status_code=403, detail="Local launcher only")

    # Register before the SPA mount, so it cannot swallow these two routes.
    def status(request: Request):
        authorize(request)
        return {"app": "FinAgent"}

    def stop(request: Request):
        authorize(request)
        server.should_exit = True
        return {"stopping": True}

    app.router.routes[0:0] = [
        APIRoute("/_portable/status", status, methods=["GET"], include_in_schema=False),
        APIRoute("/_portable/stop", stop, methods=["POST"], include_in_schema=False),
    ]
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(("127.0.0.1", 8765))
        except OSError:
            # Keep existing local applications untouched if the usual port is busy.
            listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=port, timeout_graceful_shutdown=5,
        ))
        STATE.write_text(json.dumps({"port": port, "token": token}), encoding="utf-8")

        def open_when_ready():
            while not server.started and not server.should_exit:
                time.sleep(0.1)
            if server.started and not no_browser:
                webbrowser.open(f"http://127.0.0.1:{port}/")

        threading.Thread(target=open_when_ready, daemon=True).start()
        try:
            server.run(sockets=[listener])
        finally:
            if read_state().get("token") == token:
                STATE.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-browser", action="store_true", help="For automated checks")
    args = parser.parse_args()
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        DATA.mkdir(exist_ok=True)
        with (DATA / "portable.log").open("a", encoding="utf-8", buffering=1) as log:
            sys.stdout = sys.stderr = log
            if args.stop:
                state = read_state()
                if control(state, "stop"):
                    for _ in range(100):
                        if not control(state, "status"):
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("服务仍在关闭，请稍后重试。")
                    notify("FinAgent 已关闭。下次双击启动文件即可使用。", quiet=args.no_browser)
                elif control(state, "status"):
                    raise RuntimeError("暂时无法关闭 FinAgent，请稍后重试。")
                else:
                    notify("FinAgent 当前没有运行。", quiet=args.no_browser)
            else:
                serve(no_browser=args.no_browser)
    except Exception:
        try:
            with (DATA / "portable.log").open("a", encoding="utf-8") as log:
                traceback.print_exc(file=log)
        except OSError:
            pass
        notify(
            "FinAgent 启动或关闭失败。\n请先完整解压到有写入权限的文件夹；"
            "\n详细原因见 var/portable.log。",
            quiet=args.no_browser,
        )
        raise SystemExit(1) from None
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr


if __name__ == "__main__":
    main()
