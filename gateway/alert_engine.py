"""告警引擎 — 防抖 / 冷却 / 分级 / 趋势预判。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("gateway.alert")


@dataclass
class AlertRule:
    name: str
    field: str              # "temperature" | "humidity"
    upper: float | None = None
    lower: float | None = None
    debounce_count: int = 1
    cooldown_sec: int = 60
    severity: str = "warning"
    trend_watch: bool = False


@dataclass
class Alert:
    device_id: str
    timestamp: float
    severity: str
    message: str
    rule_name: str
    current_value: float
    threshold: float
    ai_diagnosis: str | None = None


class AlertEngine:
    def __init__(self, rules: list[AlertRule]):
        self.rules = rules
        self._breach_counters: dict[str, int] = {}     # key → 连续超限次数
        self._last_alerted: dict[str, float] = {}       # key → 上次告警时间
        self._trend_windows: dict[str, list[tuple[float, float]]] = {}  # key → [(ts, value), ...]

    def evaluate(self, device_id: str, data: dict) -> list[Alert]:
        alerts: list[Alert] = []
        now = time.time()

        for rule in self.rules:
            value = data.get(rule.field)
            if value is None:
                continue

            key = f"{device_id}:{rule.name}"

            if self._is_breach(rule, value):
                self._breach_counters[key] = self._breach_counters.get(key, 0) + 1

                if self._breach_counters[key] >= rule.debounce_count:
                    if self._can_alert(rule, key):
                        severity = rule.severity
                        message = self._build_message(rule, device_id, value)
                        alerts.append(Alert(
                            device_id=device_id,
                            timestamp=now,
                            severity=severity,
                            message=message,
                            rule_name=rule.name,
                            current_value=value,
                            threshold=rule.upper if rule.upper else rule.lower or 0,
                        ))
                        self._last_alerted[key] = now
                        self._breach_counters[key] = 0
            else:
                # 值恢复正常，复位计数器
                if key in self._breach_counters and self._breach_counters[key] > 0:
                    logger.debug(f"{key}: breach cleared after {self._breach_counters[key]} hits")
                self._breach_counters[key] = 0

            # 趋势预判
            if rule.trend_watch and value is not None:
                self._trend_windows.setdefault(key, []).append((now, value))
                # 只保留最近 60 秒
                self._trend_windows[key] = [
                    (t, v) for t, v in self._trend_windows[key] if now - t <= 60
                ]
                trend_alert = self._check_trend(rule, device_id, key, now)
                if trend_alert:
                    alerts.append(trend_alert)

        return alerts

    def _is_breach(self, rule: AlertRule, value: float) -> bool:
        if rule.upper is not None and value > rule.upper:
            return True
        if rule.lower is not None and value < rule.lower:
            return True
        return False

    def _can_alert(self, rule: AlertRule, key: str) -> bool:
        last = self._last_alerted.get(key, 0)
        return (time.time() - last) >= rule.cooldown_sec

    def _build_message(self, rule: AlertRule, device_id: str, value: float) -> str:
        direction = "偏高" if rule.upper and value > rule.upper else "偏低"
        threshold = rule.upper if rule.upper else rule.lower
        return (
            f"[{rule.severity.upper()}] 设备 {device_id} "
            f"{rule.field} {direction}: {value:.1f} (阈值: {threshold})"
        )

    def _check_trend(self, rule: AlertRule, device_id: str, key: str, now: float) -> Alert | None:
        """简单线性回归趋势预判：若斜率指向阈值方向且将持续触达，提前告警。"""
        window = self._trend_windows.get(key, [])
        if len(window) < 10:
            return None

        xs = [t - window[0][0] for t, _ in window]
        ys = [v for _, v in window]
        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)
        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return None
        slope = (n * sum_xy - sum_x * sum_y) / denom

        # 检查方向：升且上限、降且下限
        if rule.upper and slope > 0:
            threshold = rule.upper
            current = ys[-1]
            if current >= threshold:
                return None
            eta = (threshold - current) / slope
            if eta > 0 and eta <= 300:  # 5 分钟内
                return Alert(
                    device_id=device_id,
                    timestamp=now,
                    severity="warning",
                    message=(
                        f"[趋势预判] 设备 {device_id} {rule.field} "
                        f"持续上升 (斜率={slope:.2f}/s)，预计 {eta:.0f}s 后触达阈值 {threshold}"
                    ),
                    rule_name=f"{rule.name}_trend",
                    current_value=current,
                    threshold=threshold,
                )
        elif rule.lower and slope < 0:
            threshold = rule.lower
            current = ys[-1]
            if current <= threshold:
                return None
            eta = (threshold - current) / slope  # eta > 0 because slope < 0
            if eta > 0 and eta <= 300:
                return Alert(
                    device_id=device_id,
                    timestamp=now,
                    severity="warning",
                    message=(
                        f"[趋势预判] 设备 {device_id} {rule.field} "
                        f"持续下降 (斜率={slope:.2f}/s)，预计 {eta:.0f}s 后触达阈值 {threshold}"
                    ),
                    rule_name=f"{rule.name}_trend",
                    current_value=current,
                    threshold=threshold,
                )

        return None
