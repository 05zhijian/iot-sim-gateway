"""异常工况单元测试。"""
from simulator.anomaly import (
    NormalBehavior,
    DriftBehavior,
    StuckBehavior,
    SpikeBehavior,
    DropoutBehavior,
)


def test_normal():
    b = NormalBehavior()
    assert b.apply(25.0) == 25.0
    assert b.label == "NORMAL"


def test_drift():
    b = DriftBehavior(rate=0.1, elapsed=10.0)
    assert b.apply(25.0) == 26.0  # 25 + 0.1*10
    assert b.label == "DRIFT"


def test_stuck():
    b = StuckBehavior()
    assert b.apply(25.0) == 25.0
    assert b.apply(26.0) == 25.0  # frozen at first value
    b.reset()
    assert b.apply(30.0) == 30.0  # new frozen value after reset
    assert b.label == "STUCK"


def test_spike():
    b = SpikeBehavior(amplitude=10.0)
    assert b.apply(25.0) == 35.0
    assert b.label == "SPIKE"


def test_dropout():
    b = DropoutBehavior()
    assert b.apply(25.0) is None  # 掉线不上报
    assert b.label == "DROPOUT"


def test_all_labels_distinct():
    """确保所有异常类型名唯一。"""
    behaviors = [
        NormalBehavior(),
        DriftBehavior(0.1),
        StuckBehavior(),
        SpikeBehavior(),
        DropoutBehavior(),
    ]
    labels = [b.label for b in behaviors]
    assert len(labels) == len(set(labels))
