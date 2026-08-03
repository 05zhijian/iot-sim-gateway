"""SQLite 时序存储。"""
from __future__ import annotations

import logging
import sqlite3
import threading

logger = logging.getLogger("gateway.storage")


class SensorDB:
    def __init__(self, db_path: str = "data/sensor.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                temperature REAL,
                humidity REAL,
                state TEXT DEFAULT 'NORMAL',
                is_anomaly INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                severity TEXT NOT NULL,
                message TEXT,
                ai_diagnosis TEXT,
                resolved_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_sensor_device_time
                ON sensor_data(device_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_alerts_time
                ON alerts(timestamp DESC);
        """)
        conn.commit()
        conn.close()

    def insert(self, data: dict) -> int:
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO sensor_data (device_id, timestamp, temperature, humidity, state, is_anomaly) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                data["device_id"],
                data["timestamp"],
                data.get("temperature"),
                data.get("humidity"),
                data.get("state", "NORMAL"),
                1 if data.get("state", "NORMAL") != "NORMAL" else 0,
            ),
        )
        self._conn.commit()
        return c.lastrowid

    def insert_alert(self, alert: dict) -> int:
        c = self._conn.cursor()
        c.execute(
            "INSERT INTO alerts (device_id, timestamp, severity, message, ai_diagnosis) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                alert["device_id"],
                alert["timestamp"],
                alert["severity"],
                alert["message"],
                alert.get("ai_diagnosis"),
            ),
        )
        self._conn.commit()
        return c.lastrowid

    def recent_data(self, device_id: str | None, seconds: float) -> list[dict]:
        cutoff = __import__("time").time() - seconds
        if device_id:
            rows = self._conn.execute(
                "SELECT * FROM sensor_data WHERE device_id=? AND timestamp >= ? ORDER BY timestamp DESC",
                (device_id, cutoff),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM sensor_data WHERE timestamp >= ? ORDER BY timestamp DESC",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        c = self._conn.cursor()
        c.execute("SELECT COUNT(*) FROM sensor_data")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT device_id) FROM sensor_data")
        devices = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sensor_data WHERE is_anomaly=1")
        anomalies = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM alerts")
        alerts = c.fetchone()[0]
        c.execute(
            "SELECT severity, COUNT(*) FROM alerts GROUP BY severity"
        )
        by_severity = {row[0]: row[1] for row in c.fetchall()}
        return {
            "total_readings": total,
            "device_count": devices,
            "anomaly_count": anomalies,
            "alert_count": alerts,
            "alerts_by_severity": by_severity,
        }

    def device_history(self, device_id: str, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM sensor_data WHERE device_id=? ORDER BY timestamp DESC LIMIT ?",
            (device_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_alerts(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        """关闭当前线程的数据库连接。"""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
