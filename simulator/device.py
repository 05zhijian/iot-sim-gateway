"""虚拟传感器设备状态机。"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto

from .anomaly import (
    AnomalyBehavior,
    NormalBehavior,
    DriftBehavior,
    StuckBehavior,
    SpikeBehavior,
    DropoutBehavior,
)


class DeviceState(Enum):
    NORMAL = auto()
    DRIFT = auto()
    STUCK = auto()
    SPIKE = auto()
    DROPOUT = auto()


@dataclass
class DeviceConfig:
    """单个设备的出厂配置。"""

    device_id: str
    base_temperature: float      # 基准温度
    base_humidity: float         # 基准湿度
    noise_temp: float = 0.3      # 温度正常波动幅度
    noise_humidity: float = 1.5  # 湿度正常波动幅度


@dataclass
class Device:
    """传感器设备状态机。"""

    config: DeviceConfig
    state: DeviceState = DeviceState.NORMAL
    state_timer: float = 0.0          # 进入当前状态已持续秒数
    last_heartbeat: float = field(default_factory=time.time)

    # 异常参数（进入异常时随机生成）
    _anomaly: AnomalyBehavior = field(default_factory=NormalBehavior)

    # ── 常量（从全局配置注入） ──
    drift_rate_range: tuple[float, float] = (0.02, 0.15)
    spike_probability: float = 0.01
    dropout_probability: float = 0.005
    stuck_duration_range: tuple[int, int] = (30, 120)

    def tick(self, dt: float) -> dict | None:
        """推进一帧。dt = 距上次 tick 的秒数。返回传感数据或 None（掉线）。"""
        self.state_timer += dt

        # ── 状态转换 ──
        self._check_transitions()

        # ── 生成数据 ──
        temp = self._generate_value(self.config.base_temperature, self.config.noise_temp)
        humidity = self._generate_value(self.config.base_humidity, self.config.noise_humidity)

        # 如果处于掉线状态，不上报
        if self.state == DeviceState.DROPOUT:
            return None

        return {
            "device_id": self.config.device_id,
            "timestamp": time.time(),
            "temperature": round(temp, 2),
            "humidity": round(humidity, 2),
            "state": self._anomaly.label,
        }

    def heartbeat_ok(self) -> bool:
        """心跳是否正常（掉线状态返回 False）。"""
        return self.state != DeviceState.DROPOUT

    # ── 内部 ──

    def _generate_value(self, base: float, noise: float) -> float:
        value = self._anomaly.apply(base)
        if value is None:
            return base  # 不应发生，安全兜底
        # 叠加上报时的瞬时噪声
        return value + random.gauss(0, noise)

    def _check_transitions(self):
        """检查并执行状态转换。"""
        roll = random.random()

        if self.state == DeviceState.NORMAL:
            # NORMAL → DRIFT
            if roll < 0.002:
                rate = random.uniform(*self.drift_rate_range)
                self._anomaly = DriftBehavior(rate)
                self.state = DeviceState.DRIFT
                self.state_timer = 0
                return
            # NORMAL → STUCK
            if roll < 0.003:
                self._anomaly = StuckBehavior()
                self.state = DeviceState.STUCK
                self.state_timer = 0
                return
            # NORMAL → SPIKE（瞬时，下帧自动恢复）
            if roll < self.spike_probability:
                self._anomaly = SpikeBehavior()
                self.state = DeviceState.SPIKE
                self.state_timer = 0
                return
            # NORMAL → DROPOUT
            if roll < self.dropout_probability:
                self._anomaly = DropoutBehavior()
                self.state = DeviceState.DROPOUT
                self.state_timer = 0
                return

        elif self.state == DeviceState.DRIFT:
            # DRIFT → NORMAL（漂移超限或持续过久）
            self._anomaly.elapsed = self.state_timer
            if self.state_timer > 600 or abs(self._anomaly.rate * self.state_timer) > 10:
                self._recover()

        elif self.state == DeviceState.STUCK:
            # STUCK → NORMAL（随机时长后恢复）
            if self.state_timer > random.uniform(*self.stuck_duration_range):
                self._anomaly = StuckBehavior.__new__(StuckBehavior)  # reset
                self._anomaly._frozen = None
                self._recover()

        elif self.state == DeviceState.SPIKE:
            # SPIKE → NORMAL（本帧结束后自动恢复）
            self._recover()

        elif self.state == DeviceState.DROPOUT:
            # DROPOUT → NORMAL（随机 30-300s 后恢复）
            if self.state_timer > random.uniform(30, 300):
                self._recover()

    def _recover(self):
        self._anomaly = NormalBehavior()
        self.state = DeviceState.NORMAL
        self.state_timer = 0
        self.last_heartbeat = time.time()
