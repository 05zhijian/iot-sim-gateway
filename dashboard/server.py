"""Dashboard bridge: HTTP server + MQTT subscriber → SSE stream.
Zero new dependencies — uses stdlib http.server + paho-mqtt.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in its own thread."""
    daemon_threads = True

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("bridge")

# --- Config ---
PORT = int(os.environ.get("PORT", "8080"))
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC_DATA = "iot/sensors/+/data"
TOPIC_HEARTBEAT = "iot/sensors/+/heartbeat"

# Thread-safe queue for SSE events
_event_queue: queue.Queue = queue.Queue()
_sse_clients: list[SSEClient] = []
_clients_lock = threading.Lock()


class SSEClient:
    """Writable handle for one SSE connection."""

    def __init__(self, wfile):
        self.wfile = wfile
        self.alive = True

    def send(self, data: str):
        if not self.alive:
            return
        try:
            self.wfile.write(data.encode("utf-8"))
            self.wfile.flush()
        except Exception:
            self.alive = False


def on_mqtt_message(client, userdata, msg):
    """Forward MQTT messages into the event queue."""
    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        return
    topic = msg.topic
    event = {"topic": topic, "payload": payload}
    _event_queue.put(event)


def mqtt_thread():
    """Background thread: connect MQTT and feed messages into queue."""
    mqttc = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"bridge-{int(time.time())}",
    )
    mqttc.on_message = on_mqtt_message

    while True:
        try:
            mqttc.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            mqttc.subscribe(TOPIC_DATA, qos=1)
            mqttc.subscribe(TOPIC_HEARTBEAT, qos=0)
            logger.info(f"MQTT connected → {MQTT_BROKER}:{MQTT_PORT}")
            mqttc.loop_forever()
        except Exception as e:
            logger.warning(f"MQTT error: {e}, retrying in 3s…")
            time.sleep(3)


def broadcast_events():
    """Push queued events to all connected SSE clients."""
    batch = []
    while True:
        try:
            batch.append(_event_queue.get(timeout=0.1))
        except queue.Empty:
            break
        if len(batch) >= 20:
            break

    if not batch:
        return

    data = "data: " + json.dumps(batch, ensure_ascii=False) + "\n\n"
    with _clients_lock:
        dead = [c for c in _sse_clients if not c.alive]
        for c in dead:
            _sse_clients.remove(c)
        for client in _sse_clients:
            client.send(data)


def broadcast_loop():
    """Background thread: periodically flush queued events to SSE clients."""
    while True:
        broadcast_events()
        time.sleep(0.5)


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve dashboard files + SSE endpoint."""

    def __init__(self, *args, **kwargs):
        # Serve from the dashboard directory
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_GET(self):
        if self.path == "/events":
            # SSE endpoint
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            client = SSEClient(self.wfile)
            with _clients_lock:
                _sse_clients.append(client)
            logger.info(f"SSE client connected (total: {len(_sse_clients)})")

            # Keep connection alive; broadcast_thread pushes data
            heartbeat = 0
            while client.alive:
                time.sleep(1)
                heartbeat += 1
                if heartbeat % 15 == 0:
                    try:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                    except Exception:
                        break
            return
        else:
            super().do_GET()

    def log_message(self, format, *args):
        """Suppress default HTTP log noise."""
        if "/events" in str(args):
            return
        logger.debug(format % args)


def start_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    logger.info(f"Dashboard → http://localhost:{PORT}")
    logger.info(f"SSE stream → http://localhost:{PORT}/events")

    # Start MQTT thread
    threading.Thread(target=mqtt_thread, daemon=True, name="mqtt-bridge").start()

    # Start SSE broadcast thread
    threading.Thread(target=broadcast_loop, daemon=True, name="sse-broadcast").start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down…")
        server.server_close()


if __name__ == "__main__":
    start_server()
