"""MQTT 发布封装。"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger("simulator.publisher")


class MQTTPublisher:
    """将传感器数据发布到 EMQX。"""

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        client_id: str | None = None,
        on_connect: Callable | None = None,
    ):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id or f"sim-{int(time.time())}",
        )
        if on_connect:
            self.client.on_connect = on_connect

    def connect(self) -> bool:
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            logger.info(f"Connected to MQTT broker {self.broker}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"MQTT connect failed: {e}")
            return False

    def publish_data(self, device_id: str, data: dict) -> None:
        topic = f"iot/sensors/{device_id}/data"
        payload = json.dumps(data, ensure_ascii=False)
        result = self.client.publish(topic, payload, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning(f"Publish failed: {topic} rc={result.rc}")

    def publish_heartbeat(self, device_id: str) -> None:
        topic = f"iot/sensors/{device_id}/heartbeat"
        payload = json.dumps({
            "device_id": device_id,
            "timestamp": time.time(),
        })
        self.client.publish(topic, payload, qos=0)

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("MQTT disconnected")
