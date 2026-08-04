"""开关控制器。python cli/ctrl.py [all|start|stop|replay|status]"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser

# 修复 Windows GBK 终端 emoji 编码问题
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PID_FILE = os.path.join(BASE_DIR, "data", "simulator.pid")
GATEWAY_PID_FILE = os.path.join(BASE_DIR, "data", "gateway.pid")
BRIDGE_PID_FILE = os.path.join(BASE_DIR, "data", "bridge.pid")
REPLAY_DIR = os.path.join(os.path.dirname(__file__), "..", "replay")


def _is_running(pid: int) -> bool:
    """检查进程是否存活（Windows 兼容）。"""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True,
            )
            return f'"{pid}"' in result.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_start(config: str = "config.yaml") -> None:
    """启动仿真器（后台）"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            if _is_running(pid):
                print(f"⚠️  仿真器已在运行 (PID: {pid})")
                return
            else:
                os.remove(PID_FILE)
        except (OSError, ValueError):
            os.remove(PID_FILE)

    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, "-m", "simulator.main", "--config", config],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    time.sleep(2)
    if proc.poll() is None:
        cfg = load_config(config)
        n = cfg["simulator"]["device_count"]
        print(f"✅ 仿真器已启动 — {n} 台设备，PID: {proc.pid}")
    else:
        print(f"❌ 仿真器启动失败，退出码: {proc.returncode}")
        os.remove(PID_FILE)


def cmd_stop() -> None:
    """停止仿真器"""
    if not os.path.exists(PID_FILE):
        print("⚠️  仿真器未运行（无 PID 文件）")
        return

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, 9)
        print(f"🛑 仿真器已停止 (PID: {pid})")
    except Exception:
        print(f"⚠️  无法停止 PID {pid}，可能已退出")

    os.remove(PID_FILE)


def cmd_replay(scenario: str) -> None:
    """前台运行回放场景（Ctrl+C 可中断）。先停后台仿真器避免冲突。"""
    path = os.path.join(REPLAY_DIR, f"scenario_{scenario}.json")
    if not os.path.exists(path):
        print(f"❌ 场景文件不存在: {path}")
        print(f"   可用场景: {_list_scenarios()}")
        return

    # 先停后台仿真器，避免两个同时发数据
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            if _is_running(pid):
                print(f"🛑 先停止后台仿真器 (PID: {pid})…")
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    os.kill(pid, 9)
            os.remove(PID_FILE)
        except Exception:
            pass

    print(f"▶️  回放: {scenario}（按 Ctrl+C 停止）")
    subprocess.run([sys.executable, "-m", "simulator.main", "--replay", path])


def cmd_status() -> None:
    """查看仿真器状态"""
    if not os.path.exists(PID_FILE):
        print("⚪ 仿真器未运行")
        return

    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if _is_running(pid):
            print(f"🟢 仿真器运行中 — PID: {pid}")
        else:
            print("🔴 PID 文件存在但进程已死 — 清理中")
            os.remove(PID_FILE)
    except (OSError, ValueError):
        print("🔴 PID 文件异常 — 清理中")
        os.remove(PID_FILE)


def _start_service(name: str, pid_file: str, module: str, cwd: str | None = None) -> bool:
    """启动后台服务，返回是否成功。"""
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            if _is_running(pid):
                print(f"  ⏭  {name} 已在运行 (PID: {pid})")
                return True
            os.remove(pid_file)
        except (OSError, ValueError):
            os.remove(pid_file)

    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [sys.executable, "-m", module],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=cwd or BASE_DIR,
        creationflags=creationflags,
    )
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))
    time.sleep(2)
    if proc.poll() is None:
        print(f"  ✅ {name} 已启动 (PID: {proc.pid})")
        return True
    else:
        print(f"  ❌ {name} 启动失败")
        os.remove(pid_file)
        return False


def cmd_all() -> None:
    """一键启动所有服务并打开 Dashboard。"""
    print("🚀 启动 iot-sim-gateway…\n")

    # 1. Gateway
    print("[1/3] Gateway")
    if not _start_service("Gateway", GATEWAY_PID_FILE, "gateway.main"):
        return

    # 2. Dashboard Bridge
    print("[2/3] Dashboard")
    bridge_cwd = os.path.join(BASE_DIR, "dashboard")
    if not _start_service("Bridge", BRIDGE_PID_FILE, "server", cwd=bridge_cwd):
        # server.py 不是 package module，需要特殊处理
        # 重置，用直接执行脚本的方式
        os.remove(BRIDGE_PID_FILE)
        if os.path.exists(BRIDGE_PID_FILE):
            pass
        if not _start_bridge_fallback():
            return

    # 3. Simulator
    print("[3/3] 仿真器")
    cmd_start()

    # 打开浏览器
    print()
    webbrowser.open("http://localhost:8080/index.html")
    print("🌐 Dashboard → http://localhost:8080/index.html")
    print("📋 python cli/ctrl.py status  # 查看状态")


def _start_bridge_fallback() -> bool:
    """备用方式启动 bridge（直接执行 server.py）。"""
    pid_file = BRIDGE_PID_FILE
    bridge_script = os.path.join(BASE_DIR, "dashboard", "server.py")
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [sys.executable, bridge_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.path.join(BASE_DIR, "dashboard"),
        creationflags=creationflags,
    )
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))
    time.sleep(2)
    if proc.poll() is None:
        print(f"  ✅ Bridge 已启动 (PID: {proc.pid})")
        return True
    else:
        print(f"  ❌ Bridge 启动失败")
        os.remove(pid_file)
        return False


def _list_scenarios() -> str:
    import glob
    files = glob.glob(os.path.join(REPLAY_DIR, "scenario_*.json"))
    names = [os.path.splitext(os.path.basename(f))[0].replace("scenario_", "") for f in files]
    return ", ".join(names)


def main():
    parser = argparse.ArgumentParser(description="iot-sim-gateway 开关控制器")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("all", help="一键启动所有服务 + 打开 Dashboard")
    sub.add_parser("start", help="启动仿真器（后台）")
    sub.add_parser("stop", help="停止仿真器")
    sub.add_parser("status", help="查看服务运行状态")

    replay = sub.add_parser("replay", help="前台运行回放场景")
    replay.add_argument("scenario", help=f"场景名: {_list_scenarios()}")

    args = parser.parse_args()

    if args.command == "all":
        cmd_all()
    elif args.command == "start":
        cmd_start()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "replay":
        cmd_replay(args.scenario)
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
