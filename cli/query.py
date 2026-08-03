"""CLI 查询统计工具。python cli/query.py <command>"""
from __future__ import annotations

import argparse
import os
import sys
import time

import yaml

# 修复 Windows GBK 终端 emoji 编码问题
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 确保能 import gateway 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gateway.storage import SensorDB  # noqa: E402


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_stats(db: SensorDB):
    s = db.stats()
    print("📊 Gateway 统计")
    print(f"  总数据量:   {s['total_readings']}")
    print(f"  设备数:     {s['device_count']}")
    print(f"  异常数据:   {s['anomaly_count']}")
    print(f"  告警总数:   {s['alert_count']}")
    if s["alerts_by_severity"]:
        print("  告警分级:")
        for sev, cnt in sorted(s["alerts_by_severity"].items()):
            emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "⚪")
            print(f"    {emoji} {sev}: {cnt}")


def cmd_device(db: SensorDB, device_id: str, limit: int):
    rows = db.device_history(device_id, limit)
    if not rows:
        print(f"设备 {device_id} 无数据")
        return
    print(f"📡 {device_id} — 最近 {len(rows)} 条")
    for r in reversed(rows):
        state_mark = "⚠" if r["is_anomaly"] else " "
        ts = time.strftime("%H:%M:%S", time.localtime(r["timestamp"]))
        print(f"  {state_mark} {ts}  {r['temperature']:5.1f}°C  {r['humidity']:5.1f}%  [{r['state']}]")


def cmd_alerts(db: SensorDB, limit: int):
    rows = db.recent_alerts(limit)
    if not rows:
        print("无告警记录")
        return
    print(f"🚨 最近 {len(rows)} 条告警")
    for r in rows:
        ts = time.strftime("%m-%d %H:%M:%S", time.localtime(r["timestamp"]))
        emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(r["severity"], "⚪")
        print(f"  {emoji} {ts} [{r['device_id']}] {r['message']}")
        if r.get("ai_diagnosis"):
            print(f"     🤖 {r['ai_diagnosis'][:100]}")


def main():
    parser = argparse.ArgumentParser(description="IoT Gateway CLI")
    parser.add_argument("--config", default="config.yaml")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("stats", help="Overall statistics")

    dev = sub.add_parser("device", help="Device history")
    dev.add_argument("device_id")
    dev.add_argument("--limit", type=int, default=50)

    alt = sub.add_parser("alerts", help="Recent alerts")
    alt.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cfg = load_config(args.config)
    db = SensorDB(cfg["gateway"]["db_path"])

    if args.command == "stats":
        cmd_stats(db)
    elif args.command == "device":
        cmd_device(db, args.device_id, args.limit)
    elif args.command == "alerts":
        cmd_alerts(db, args.limit)


if __name__ == "__main__":
    main()
