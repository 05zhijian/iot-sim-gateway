"""网关服务入口。python -m gateway.main"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from threading import Lock

import yaml

from .alert_engine import AlertEngine, AlertRule
from .diagnoser import diagnose
from .storage import SensorDB
from .subscriber import MQTTSubscriber
from .webhook import send_alert

logger = logging.getLogger("gateway")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_alert_rules(cfg: dict) -> list[AlertRule]:
    return [
        AlertRule(
            name=r["name"],
            field=r["field"],
            upper=r.get("upper"),
            lower=r.get("lower"),
            debounce_count=r.get("debounce_count", 1),
            cooldown_sec=r.get("cooldown_sec", 60),
            severity=r.get("severity", "warning"),
            trend_watch=r.get("trend_watch", False),
        )
        for r in cfg["alerts"]["rules"]
    ]


# ── 全局状态（由 subscriber 回调写入） ──
_heartbeats: dict[str, float] = {}
_hb_lock = Lock()


def run_gateway(cfg: dict) -> None:
    mqtt_cfg = cfg["mqtt"]
    gw_cfg = cfg["gateway"]
    feishu_cfg = cfg.get("feishu", {})
    webhook_url = feishu_cfg.get("webhook_url", "")
    enable_ai = feishu_cfg.get("enable_ai_diagnosis", False)
    history_sec = gw_cfg.get("alert_history_sec", 60)

    db = SensorDB(gw_cfg["db_path"])
    alert_engine = AlertEngine(build_alert_rules(cfg))

    def handle_message(topic: str, payload: dict):
        device_id = payload.get("device_id", "unknown")

        if "heartbeat" in topic:
            with _hb_lock:
                _heartbeats[device_id] = time.time()
            return

        # 数据消息
        db.insert(payload)
        alerts = alert_engine.evaluate(device_id, payload)

        for alert in alerts:
            ai_diag = None
            if enable_ai:
                recent = db.recent_data(device_id, history_sec)
                ai_diag = diagnose(alert.message, recent)

            db.insert_alert({
                "device_id": alert.device_id,
                "timestamp": alert.timestamp,
                "severity": alert.severity,
                "message": alert.message,
                "ai_diagnosis": ai_diag,
            })

            send_alert(webhook_url, {
                "device_id": alert.device_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(alert.timestamp)),
                "severity": alert.severity,
                "message": alert.message,
                "current_value": alert.current_value,
                "threshold": alert.threshold,
            }, ai_diag)

            logger.info(f"ALERT [{alert.severity}]: {alert.message}")

    subscriber = MQTTSubscriber(
        broker=mqtt_cfg["broker"],
        port=mqtt_cfg["port"],
        on_data=handle_message,
    )

    if not subscriber.start():
        sys.exit(1)

    # ── 心跳检测（后台定时检查） ──
    running = True

    def _sig(signum, frame):
        nonlocal running
        running = False
        logger.info("Gateway shutting down...")

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    logger.info("Gateway running. Press Ctrl+C to stop.")

    try:
        while running:
            time.sleep(10)
            now = time.time()
            with _hb_lock:
                stale = [
                    did for did, last in _heartbeats.items()
                    if now - last > 30  # 30 秒无心跳视为离线
                ]
                for did in stale:
                    logger.warning(f"Device OFFLINE: {did}")
                    msg = f"设备 {did} 心跳超时，可能掉线"
                    db.insert_alert({
                        "device_id": did,
                        "timestamp": now,
                        "severity": "warning",
                        "message": msg,
                        "ai_diagnosis": None,
                    })
                    send_alert(webhook_url, {
                        "device_id": did,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                        "severity": "warning",
                        "message": msg,
                        "current_value": "N/A",
                        "threshold": "30s no heartbeat",
                    }, None)
                    del _heartbeats[did]
    finally:
        subscriber.stop()
        logger.info("Gateway stopped")


def main():
    parser = argparse.ArgumentParser(description="IoT Gateway Service")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config(args.config)
    run_gateway(cfg)


if __name__ == "__main__":
    main()
