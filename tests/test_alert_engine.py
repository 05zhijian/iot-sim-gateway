"""告警引擎单元测试。"""
import time
from gateway.alert_engine import AlertEngine, AlertRule


def test_no_breach():
    rules = [AlertRule(name="高温", field="temperature", upper=35, debounce_count=1)]
    engine = AlertEngine(rules)
    alerts = engine.evaluate("sensor-01", {"temperature": 25.0})
    assert len(alerts) == 0


def test_breach_and_debounce():
    rules = [AlertRule(name="高温", field="temperature", upper=35, debounce_count=3)]
    engine = AlertEngine(rules)

    # 2 次超限 — 未达防抖阈值
    assert len(engine.evaluate("s-01", {"temperature": 36.0})) == 0
    assert len(engine.evaluate("s-01", {"temperature": 36.0})) == 0

    # 第 3 次 — 触发
    alerts = engine.evaluate("s-01", {"temperature": 36.0})
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"


def test_cooldown():
    rules = [AlertRule(name="高温", field="temperature", upper=35, cooldown_sec=10)]
    engine = AlertEngine(rules)

    # 首次触发
    alerts = engine.evaluate("s-01", {"temperature": 36.0})
    assert len(alerts) == 1

    # 立即再次超限 — 冷却中
    alerts = engine.evaluate("s-01", {"temperature": 36.0})
    assert len(alerts) == 0


def test_recovery_resets_counter():
    rules = [AlertRule(name="高温", field="temperature", upper=35, debounce_count=3)]
    engine = AlertEngine(rules)

    engine.evaluate("s-01", {"temperature": 36.0})  # breach 1
    engine.evaluate("s-01", {"temperature": 36.0})  # breach 2
    engine.evaluate("s-01", {"temperature": 25.0})  # recovered — counter reset
    engine.evaluate("s-01", {"temperature": 36.0})  # breach 1 (reset)

    # 只有 1 次连续超限 — 不触发
    alerts = engine.evaluate("s-01", {"temperature": 36.0})
    assert len(alerts) == 0  # 2 consecutive, debounce=3 → no trigger
