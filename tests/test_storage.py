"""存储层单元测试。使用临时文件数据库，测试后清理。"""
import os
import tempfile
import time
from gateway.storage import SensorDB


def _make_db():
    """创建临时文件数据库，避免污染正式数据。"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return SensorDB(path), path


def _cleanup(db, path):
    """关闭连接并删除临时文件。"""
    db.close()
    os.remove(path)


def test_insert_and_query():
    db, path = _make_db()
    try:
        db.insert({
            "device_id": "sensor-01",
            "timestamp": time.time(),
            "temperature": 25.5,
            "humidity": 60.0,
            "state": "NORMAL",
        })
        rows = db.device_history("sensor-01", 10)
        assert len(rows) == 1
        assert rows[0]["temperature"] == 25.5
    finally:
        _cleanup(db, path)


def test_insert_alert():
    db, path = _make_db()
    try:
        db.insert_alert({
            "device_id": "sensor-02",
            "timestamp": time.time(),
            "severity": "critical",
            "message": "高温告警",
            "ai_diagnosis": None,
        })
        alerts = db.recent_alerts(10)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"
    finally:
        _cleanup(db, path)


def test_stats():
    db, path = _make_db()
    try:
        now = time.time()
        db.insert({"device_id": "a", "timestamp": now, "temperature": 20, "humidity": 50, "state": "NORMAL"})
        db.insert({"device_id": "b", "timestamp": now, "temperature": 30, "humidity": 55, "state": "NORMAL"})
        db.insert({"device_id": "a", "timestamp": now, "temperature": 40, "humidity": 50, "state": "DRIFT"})
        db.insert({"device_id": "c", "timestamp": now, "temperature": 25, "humidity": 60, "state": "NORMAL"})

        s = db.stats()
        assert s["total_readings"] == 4
        assert s["device_count"] == 3
        assert s["anomaly_count"] == 1
        assert s["alert_count"] == 0
    finally:
        _cleanup(db, path)


def test_device_history_limit():
    db, path = _make_db()
    try:
        now = time.time()
        for i in range(10):
            db.insert({
                "device_id": "sensor-01",
                "timestamp": now + i,
                "temperature": 20 + i,
                "humidity": 50,
                "state": "NORMAL",
            })
        rows = db.device_history("sensor-01", 5)
        assert len(rows) == 5
        # 最近 5 条应该是温度最高的
        temps = [r["temperature"] for r in rows]
        assert temps == [29, 28, 27, 26, 25]  # DESC
    finally:
        _cleanup(db, path)


def test_recent_data():
    """验证 recent_data 按时间过滤。"""
    db, path = _make_db()
    try:
        now = time.time()
        for i in range(5):
            db.insert({
                "device_id": "sensor-01",
                "timestamp": now - 100 + i,  # 100 秒前
                "temperature": 20 + i,
                "humidity": 50,
                "state": "NORMAL",
            })
        for i in range(3):
            db.insert({
                "device_id": "sensor-01",
                "timestamp": now + i,  # 现在
                "temperature": 30 + i,
                "humidity": 55,
                "state": "DRIFT",
            })
        rows = db.recent_data("sensor-01", 60)
        # 只应返回最近 60 秒的 3 条
        temps = [r["temperature"] for r in rows]
        assert len(rows) == 3
        assert all(t >= 30 for t in temps)
    finally:
        _cleanup(db, path)


def test_alerts_ordered():
    """验证告警按时间倒序。"""
    db, path = _make_db()
    try:
        now = time.time()
        db.insert_alert({"device_id": "a", "timestamp": now - 10, "severity": "warning", "message": "w1"})
        db.insert_alert({"device_id": "b", "timestamp": now, "severity": "critical", "message": "c1"})
        db.insert_alert({"device_id": "c", "timestamp": now - 5, "severity": "info", "message": "i1"})

        alerts = db.recent_alerts(10)
        assert len(alerts) == 3
        # 最新的在最前
        assert alerts[0]["message"] == "c1"
        assert alerts[1]["message"] == "i1"
        assert alerts[2]["message"] == "w1"
    finally:
        _cleanup(db, path)


def test_stats_alerts_by_severity():
    db, path = _make_db()
    try:
        now = time.time()
        db.insert_alert({"device_id": "x", "timestamp": now, "severity": "warning", "message": ""})
        db.insert_alert({"device_id": "x", "timestamp": now, "severity": "warning", "message": ""})
        db.insert_alert({"device_id": "x", "timestamp": now, "severity": "critical", "message": ""})
        db.insert_alert({"device_id": "x", "timestamp": now, "severity": "info", "message": ""})

        s = db.stats()
        assert s["alert_count"] == 4
        assert s["alerts_by_severity"] == {"warning": 2, "critical": 1, "info": 1}
    finally:
        _cleanup(db, path)
