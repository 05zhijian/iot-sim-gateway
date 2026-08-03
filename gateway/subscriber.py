"""MQTT 订阅 + 消息路由。"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable, Protocol

import paho.mqtt.client as mqtt

logger = logging.getLogger("gateway.subscriber")


class DataHandler(Protocol):
    def __call__(self, topic: str, payload: dict) -> None: ...


class MQTTSubscriber:
    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topics: list[str] | None = None,
        on_data: DataHandler | None = None,
    ):
        self.broker = broker
        self.port = port
        self.topics = topics or [
            "iot/sensors/+/data",
            "iot/sensors/+/heartbeat",
        ]
        self.on_data = on_data
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"gw-{int(time.time())}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            for topic in self.topics:
                client.subscribe(topic, qos=1)
                logger.info(f"Subscribed: {topic}")
        else:
            logger.error(f"MQTT connect failed: rc={reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON on {msg.topic}: {msg.payload[:100]}")
            return
        if self.on_data:
            self.on_data(msg.topic, payload)

    def start(self):
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            logger.info(f"Gateway listening on {self.broker}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Subscriber connect failed: {e}")
            return False

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Gateway stopped")
