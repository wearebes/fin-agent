"""Build a clean Windows x64 ZIP; never copy the developer's environment/data."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.13.15"
PYTHON_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
# https://www.python.org/downloads/release/python-31315/
PYTHON_SHA256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"


def run(*command: str | Path, cwd: Path = ROOT) -> None:
    subprocess.run([str(item) for item in command], cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13):
        raise SystemExit("Build with 64-bit Python 3.13 on Windows.")
    if sys.maxsize <= 2**32:
        raise SystemExit("A 64-bit Python interpreter is required.")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / "FinAgent-Windows-x64.zip"
    if archive.exists():
        raise SystemExit(f"Refusing to overwrite an existing release: {archive}")
    work = Path(tempfile.mkdtemp(prefix="portable-", dir=dist))
    package = work / "FinAgent-Windows-x64"
    runtime = package / "runtime"
    runtime.mkdir(parents=True)
    download = work / "python.zip"
    urllib.request.urlretrieve(PYTHON_URL, download)
    with download.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != PYTHON_SHA256:
            raise SystemExit("Python archive checksum mismatch.")
    with zipfile.ZipFile(download) as embedded:
        embedded.extractall(runtime)
    # Python's isolated path file ignores the host's PYTHONPATH and site-packages.
    (runtime / "python313._pth").write_text(
        "python313.zip\n.\nLib/site-packages\n../src\n", encoding="utf-8",
    )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = work / "requirements.txt"
    locked = ROOT / "scripts" / "requirements-windows.txt"
    requirements.write_text(
        locked.read_text(encoding="utf-8") if locked.exists()
        else "\n".join(project["project"]["dependencies"]) + "\n",
        encoding="utf-8",
    )
    # All runtime dependencies are installed at build time; users never run pip.
    run(
        sys.executable, "-m", "pip", "--isolated", "install",
        "--only-binary=:all:", "--no-binary=jsonpath", "--no-compile", "--ignore-installed",
        "--target", runtime / "Lib/site-packages",
        "-r", requirements,
    )
    frontend = ROOT / "frontend"
    run(args.node, frontend / "node_modules/typescript/bin/tsc", "--noEmit", cwd=frontend)
    run(args.node, frontend / "node_modules/vite/bin/vite.js", "build", cwd=frontend)
    # Explicit allowlist. No .env, user databases, model keys, logs or Codex files.
    files = subprocess.check_output(
        ["git", "ls-files", "src", "configs", "docs", "LICENSE", "pyproject.toml", "README.md"],
        cwd=ROOT, text=True,
    ).splitlines()
    launcher = "src/fin_agent/interfaces/portable.py"
    if launcher not in files:
        files.append(launcher)
    for name in files:
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copytree(frontend / "dist", package / "frontend/dist")
    for filename, option in [("Start FinAgent.cmd", ""), ("Stop FinAgent.cmd", " --stop")]:
        (package / filename).write_text(
            '@echo off\ncd /d "%~dp0"\n'
            'if not exist "%~dp0runtime\\pythonw.exe" (\n'
            '  echo Please extract the complete ZIP before starting FinAgent.\n'
            '  pause\n  exit /b 1\n)\n'
            f'start "" "%~dp0runtime\\pythonw.exe" -B -m fin_agent.interfaces.portable{option}\n',
            encoding="ascii", newline="\r\n",
        )
    (package / "使用说明.txt").write_text(
        "FinAgent Windows 免安装版（Windows 10/11，64 位）\n\n"
        "1. 先解压整个压缩包，再双击 Start FinAgent.cmd，浏览器会自动打开。\n"
        "2. 第一次在页面注册本地账户，然后到“模型连接设置”填写自己的模型 API Key。\n"
        "3. 关闭网页不会关闭服务。用完后双击 Stop FinAgent.cmd；未完成的任务会中断。\n"
        "4. 账户和报告保存在 var 文件夹。升级时先关闭旧版，解压新版，再复制整个 var 文件夹。\n"
        "5. API Key 仅在运行期间保存在内存中，重启后需要重新填写。\n\n"
        "无需安装 Python、Node.js 或其他开发工具。获取行情和使用 AI 研究仍需联网。\n"
        "模型 API 可能收费；本软件不提供模型额度，也不包含开发者的账户或数据。\n"
        "如果打不开，请查看 var/portable.log，或在 GitHub Issues 提供去除隐私后的报错。\n"
        "请放到有写入权限的普通文件夹。首次启动可能需要稍等片刻。\n"
        "若常用端口被其他软件占用，程序会自动改用空闲端口。\n\n"
        "源码及问题反馈：https://github.com/wearebes/fin-agent\n"
        "第三方依赖许可证保留在 runtime/Lib/site-packages 的各 .dist-info 目录中。\n"
        "历史分析不代表未来收益，结果仅供学习与研究参考。\n",
        encoding="utf-8-sig",
    )
    executable = runtime / "python.exe"
    resolved = subprocess.check_output([
        str(executable), "-c",
        "import importlib.metadata as m; "
        "print('\\n'.join(sorted(d.metadata['Name']+'=='+d.version for d in m.distributions())))",
    ], text=True)
    (package / "requirements-windows.txt").write_text(resolved, encoding="utf-8")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    (package / "build-info.json").write_text(json.dumps({
        "python": PYTHON_VERSION, "python_sha256": PYTHON_SHA256,
        "source_base_commit": commit, "version": project["project"]["version"],
        "platform": "Windows x64",
    }, indent=2) + "\n", encoding="utf-8")
    # Keep unpacked build for inspection. ZIP gets only the allowlisted distribution.
    pending_archive = work / archive.name
    with zipfile.ZipFile(pending_archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for item in sorted(package.rglob("*")):
            if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc":
                bundle.write(item, item.relative_to(work))
    pending_archive.replace(archive)
    with archive.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    (dist / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Package: {package}\nZIP: {archive}\nSHA256: {digest}", flush=True)


if __name__ == "__main__":
    main()
