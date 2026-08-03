"""异常工况策略 — 每种异常独立实现，可组合叠加。"""
from abc import ABC, abstractmethod
import random


class AnomalyBehavior(ABC):
    """异常工况基类。"""

    @abstractmethod
    def apply(self, base_value: float) -> float | None:
        """对基准值施加异常变换。返回 None 表示本次不上报（模拟掉线）。"""
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """异常类型名（NORMAL/DRIFT/STUCK/SPIKE/DROPOUT）。"""
        ...


# ── 正常（无异常） ──
class NormalBehavior(AnomalyBehavior):
    label = "NORMAL"

    def apply(self, base_value: float) -> float:
        return base_value


# ── 数值漂移 ──
class DriftBehavior(AnomalyBehavior):
    label = "DRIFT"

    def __init__(self, rate: float, elapsed: float = 0.0):
        """
        Args:
            rate: 漂移速率 (°C/s)
            elapsed: 已漂移时长 (s)
        """
        self.rate = rate
        self.elapsed = elapsed

    def apply(self, base_value: float) -> float:
        return base_value + self.rate * self.elapsed


# ── 数据卡死 ──
class StuckBehavior(AnomalyBehavior):
    label = "STUCK"

    def __init__(self):
        self._frozen: float | None = None

    def apply(self, base_value: float) -> float:
        if self._frozen is None:
            self._frozen = base_value
        return self._frozen

    def reset(self):
        self._frozen = None


# ── 毛刺跳变 ──
class SpikeBehavior(AnomalyBehavior):
    label = "SPIKE"

    def __init__(self, amplitude: float | None = None):
        """
        Args:
            amplitude: 跳变幅度。若为 None，随机 5-15°C。
        """
        self.amplitude = amplitude or random.uniform(5, 15) * random.choice([-1, 1])

    def apply(self, base_value: float) -> float:
        return base_value + self.amplitude


# ── 间歇掉线 ──
class DropoutBehavior(AnomalyBehavior):
    label = "DROPOUT"

    def apply(self, base_value: float) -> float | None:
        return None  # 返回 None 表示跳过本次上报
