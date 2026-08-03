"""传感器仿真器入口。python -m simulator.main [--replay <file>]"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

import yaml

from .device import Device, DeviceConfig
from .publisher import MQTTPublisher

logger = logging.getLogger("simulator")


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_devices(cfg: dict) -> list[Device]:
    sim = cfg["simulator"]
    devices = []
    for i in range(sim["device_count"]):
        base_t = sim["base_temp_range"][0] + i * 1.5  # 每台基准温度不同
        base_h = sim["base_humidity_range"][0] + i * 3
        config = DeviceConfig(
            device_id=f"sensor-{i + 1:02d}",
            base_temperature=round(base_t, 1),
            base_humidity=round(base_h, 1),
        )
        anomaly = sim["anomaly"]
        device = Device(
            config=config,
            drift_rate_range=tuple(anomaly["drift_rate_range"]),
            spike_probability=anomaly["spike_probability"],
            dropout_probability=anomaly["dropout_probability"],
            stuck_duration_range=tuple(anomaly["stuck_duration_range"]),
        )
        devices.append(device)
    return devices


# ── 回放模式 ──
def run_replay(filepath: str, mqtt_cfg: dict) -> None:
    import json

    with open(filepath, encoding="utf-8") as f:
        scenario = json.load(f)

    logger.info(f"Replaying: {scenario.get('description', filepath)}")
    pub = MQTTPublisher(broker=mqtt_cfg["broker"], port=mqtt_cfg["port"])
    if not pub.connect():
        sys.exit(1)

    running = True

    def _sig(signum, frame):
        nonlocal running
        running = False
        logger.info("Shutting down...")

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    base_ts = time.time()
    for i, item in enumerate(scenario["data"]):
        if not running:
            break
        device_id = item.get("device_id", "sensor-replay")
        # 用真实时间戳替换相对时间，确保数据库排序正确
        item["timestamp"] = base_ts + item.get("timestamp", i)
        pub.publish_data(device_id, item)
        pub.publish_heartbeat(device_id)
        time.sleep(1)

    pub.disconnect()
    logger.info("Replay finished")


# ── 正常仿真模式 ──
def run_simulation(cfg: dict) -> None:
    sim = cfg["simulator"]
    mqtt_cfg = cfg["mqtt"]
    interval = sim["report_interval_sec"]
    heartbeat_int = sim["heartbeat_interval_sec"]

    devices = build_devices(cfg)
    pub = MQTTPublisher(broker=mqtt_cfg["broker"], port=mqtt_cfg["port"])

    if not pub.connect():
        sys.exit(1)

    logger.info(f"Starting {len(devices)} virtual sensors")
    for d in devices:
        logger.info(f"  {d.config.device_id}: base_temp={d.config.base_temperature}°C, base_hum={d.config.base_humidity}%")

    running = True
    last_heartbeat = time.time()

    def _sig(signum, frame):
        nonlocal running
        running = False
        logger.info("Shutting down...")

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    logger.info("Simulation running. Press Ctrl+C to stop.")

    try:
        while running:
            now = time.time()

            for device in devices:
                data = device.tick(interval)
                if data is not None:
                    pub.publish_data(device.config.device_id, data)

            # 心跳
            if now - last_heartbeat >= heartbeat_int:
                for device in devices:
                    pub.publish_heartbeat(device.config.device_id)
                last_heartbeat = now

            time.sleep(interval)
    finally:
        pub.disconnect()
        logger.info("Simulation stopped")


# ── CLI ──
def main():
    parser = argparse.ArgumentParser(description="IoT Sensor Simulator")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--replay", default=None, help="Replay a scenario JSON file")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = load_config(args.config)

    if args.replay:
        run_replay(args.replay, cfg["mqtt"])
    else:
        run_simulation(cfg)


if __name__ == "__main__":
    main()
