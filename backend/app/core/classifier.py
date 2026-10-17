"""ML log-outcome classifier engine (the AI/ML core of Nexus Forge).

A from-scratch bag-of-counts logistic-regression classifier trained on a
hand-labeled dataset of real test-runner output (node ``--test`` tap-like lines,
pytest/jest/go-test summaries). Pure-Python (no third-party ML dependency),
deterministic (fixed seed), and trained from scratch at startup then cached.

It solves the ledger-evidence problem from issue #2342: the raw runner tail for
``node --test`` is a ``# duration_ms ...`` line that carries no pass/fail signal.
The classifier inspects the *whole* captured log, so the ledger records a
meaningful ``passed``/``failed`` label rather than echoing the duration line.

Feature engineering (4 real-valued features; a linear model over counts is a
standard, honest baseline):
- ``pass_n``  : largest test count paired with a success token
- ``fail_n``  : largest test count paired with a failure token
- ``success`` : 1 if any success token is present
- ``failure`` : 1 if any failure token is present

Exit code remains authoritative in orchestration; this classifier is advisory and
surfaces conflicts (see README "AI/ML evaluation" for measured metrics and
failure cases).
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from typing import Sequence

# Hand-labeled dataset of real runner output. 1 = passed, 0 = failed.
DATASET: list[tuple[str, int]] = [
    # passing
    ("# pass 4\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 52.464833", 1),
    ("# pass 5\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 44.363458", 1),
    ("# pass 12\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 159.210958", 1),
    ("PASS (12 tests, 45ms)\n\nTest Suites: 1 passed, 1 total\nTests:       12 passed, 12 total", 1),
    ("✓ 3 passed (48ms)\n\n  3 passing", 1),
    ("✓ 10 passed (1.2s)\n\n  10 passing", 1),
    ("ok 1 test passing\n", 1),
    ("ok 3 tests passing\n", 1),
    ("1 passing (2s)\n\n  1 passed", 1),
    ("All 5 tests passed\n\nPASS", 1),
    ("PASS — 8 tests\n\nTest Suites: 1 passed", 1),
    ("✓ 13 passing (52ms)", 1),
    ("# pass 1\n# duration_ms 2.1\nok 1 test", 1),
    ("ok 1\n1 passing", 1),
    ("PASS 6 tests\n\n6 passing", 1),
    ("--- PASS: suite 0.5s\n=== RUN: ok\nPASS", 1),
    # failing
    ("# pass 0\n# fail 1\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 10.0", 0),
    ("# pass 11\n# fail 2\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 88.1", 0),
    ("# pass 0\n# fail 3\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 31.2", 0),
    ("✕ 2 failing (15ms)\n\n  2 failing", 0),
    ("✕ 1 failing (3ms)\n\n  1 failing\n\nError: expect(received).toBe(expected)", 0),
    ("FAIL (12 tests, 2 failures)\n\nTest Suites: 1 failed\nTests:       2 failed, 10 passed", 0),
    ("not ok 1 test failed", 0),
    ("not ok 2 tests failed", 0),
    ("Error: expect(x).toBe(1)\nReceived: 2\n\n1 failing\n\n  1 failing", 0),
    ("✕ 3 failing (50ms)", 0),
    ("FAIL — 4 tests\n\nTests: 4 failed, 0 passed", 0),
    ("× 2 failing (50ms)", 0),
    ("Error: Command failed: jest\n\nTest suite failed to run", 0),
    ("# pass 0\n# fail 1\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 5.0\nnot ok 1", 0),
    ("not ok\n0 passing\n1 failing", 0),
    ("--- FAIL: suite 0.7s\nFAIL\n  1 failure", 0),
    ("Error: exit status 1\n\nCommand failed", 0),
]

_SUCCESS_TOKENS = ("pass", "passing", "passed", " ok ", "✓", "✔", "success")
_FAILURE_TOKENS = ("fail", "failing", "failed", "✕", "×", "error", "not ok", "failure")
_PASS_NUM_RE = re.compile(r"pass\s+(\d+)|(\d+)\s+passed|(\d+)\s+passing", re.IGNORECASE)
_FAIL_NUM_RE = re.compile(r"fail\s+(\d+)|(\d+)\s+failing|(\d+)\s+failed|(\d+)\s+fail\b", re.IGNORECASE)


def _max_group(re_obj: re.Pattern, text: str) -> int:
    best = 0
    for m in re_obj.finditer(text):
        for g in m.groups():
            if g is not None:
                best = max(best, int(g))
    return best


def _features(text: str) -> list[float]:
    low = text.lower()
    pass_n = _max_group(_PASS_NUM_RE, low)
    fail_n = _max_group(_FAIL_NUM_RE, low)
    success = 1.0 if any(tok in low for tok in _SUCCESS_TOKENS) else 0.0
    failure = 1.0 if any(tok in low for tok in _FAILURE_TOKENS) else 0.0
    return [float(pass_n), float(fail_n), success, failure]


@dataclass
class Model:
    weights: list[float]
    bias: float
    feature_names: tuple[str, ...] = ("pass_n", "fail_n", "success", "failure")

    def predict_log_odds(self, text: str) -> float:
        z = self.bias
        for w, f in zip(self.weights, _features(text), strict=True):
            z += w * f
        return z

    def predict_proba(self, text: str) -> float:
        z = self.predict_log_odds(text)
        if z >= 30:
            return 1.0
        if z <= -30:
            return 0.0
        return 1.0 / (1.0 + math.exp(-z))

    def predict(self, text: str, threshold: float = 0.5) -> int:
        return 1 if self.predict_proba(text) >= threshold else 0


def _sigmoid(z: float) -> float:
    if z >= 30:
        return 1.0
    if z <= -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def train(
    dataset: Sequence[tuple[str, int]] = DATASET,
    epochs: int = 300,
    lr: float = 0.05,
    seed: int = 7,
    l2: float = 0.01,
) -> Model:
    """Train a deterministic logistic-regression classifier via SGD."""
    rng = random.Random(seed)
    n_features = len(_features(""))  # number of feature slots
    weights = [0.0] * n_features
    bias = 0.0
    order = list(dataset)
    for _epoch in range(epochs):
        rng.shuffle(order)
        for text, label in order:
            feats = _features(text)
            z = bias + sum(weights[i] * feats[i] for i in range(n_features))
            p = _sigmoid(z)
            err = p - float(label)
            for i in range(n_features):
                weights[i] -= lr * (err * feats[i] + l2 * weights[i])
            bias -= lr * err
    return Model(weights=weights, bias=bias)


def evaluate(
    dataset: Sequence[tuple[str, int]] = DATASET,
    split: float = 0.7,
    seed: int = 7,
) -> dict[str, float | int]:
    """Deterministic train/test-split metrics over the committed dataset."""
    rng = random.Random(seed)
    rows = list(dataset)
    rng.shuffle(rows)
    n = len(rows)
    k = max(1, int(n * split))
    train_ds, test_ds = rows[:k], rows[k:]
    model = train(train_ds, epochs=300, lr=0.05, seed=seed)
    tp = fp = tn = fn = 0
    for text, label in test_ds:
        pred = model.predict(text)
        if pred == 1 and label == 1:
            tp += 1
        elif pred == 1 and label == 0:
            fp += 1
        elif pred == 0 and label == 0:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    acc = (tp + tn) / len(test_ds) if test_ds else 0.0
    return {
        "accuracy": round(acc, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "train_size": len(train_ds),
        "test_size": len(test_ds),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


_MODEL: Model | None = None


def default_model() -> Model:
    global _MODEL
    if _MODEL is None:
        _MODEL = train()
    return _MODEL


def classify_log(text: str) -> tuple[str, float, int]:
    """Classify a log without an authoritative exit code (classifier-only)."""
    model = default_model()
    proba = model.predict_proba(text)
    pred = 1 if proba >= 0.5 else 0
    label = "passed" if pred == 1 else "failed"
    confidence = proba if pred == 1 else 1.0 - proba
    return label, float(round(confidence, 4)), pred


def classify_outcome(
    exit_code: int | None, log_text: str, last_line: str = "", head: str = ""
) -> tuple[str, bool, float, str]:
    """Combine the authoritative exit code with the advisory classifier.

    Returns (label, passed, confidence, agreement).
    """
    label, confidence, pred = classify_log(log_text)
    passed = pred == 1
    if exit_code == 0:
        agree = "match" if passed else "classifier-conflict"
        return "passed", True, 1.0 if passed else 0.7, agree
    if exit_code is not None and exit_code != 0:
        agree = "match" if not passed else "classifier-conflict"
        return "failed", False, 1.0, agree
    return label, passed, confidence, "classifier-only"