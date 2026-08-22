"""Testy dla khipu_bio_alert.py - opcjonalny, dodatkowy alert "zbiorcza
zmiana stanu sygnału" (State9Bottleneck z KHIPU-NEURAL, forward-only,
bez treningu - patrz docstring modułu po pełne uzasadnienie).
"""
import numpy as np
import pytest

import khipu_bio_alert as kb
from khipu_bio_alert import (
    balance_correct, regime_agreement_score, make_embedding_window,
    regime_score_series, regime_alerts, N_AXES, D_EMBED, KHIPU_ALERT_THRESHOLD,
)
from demo_scenarios import make_demo_data


def test_switch_is_boolean_and_actually_gates_api_result(monkeypatch):
    """Nie zakładamy konkretnej wartości domyślnej (bywa świadomie
    przełączana) - test sprawdza tylko, że przełącznik NAPRAWDĘ włącza/
    wyłącza pola khipu_* w wyniku api.py::analyze_signal (patrz też
    test_api_khipu.py, gdzie to samo jest sprawdzone bardziej szczegółowo)."""
    assert isinstance(kb.KHIPU_BOTTLENECK_ENABLED, bool)

    from api import analyze_signal
    from demo_scenarios import make_demo_data
    d = make_demo_data("ecg_normal")

    monkeypatch.setattr(kb, "KHIPU_BOTTLENECK_ENABLED", False)
    result_off = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"])
    assert "khipu_regime_last" not in result_off

    monkeypatch.setattr(kb, "KHIPU_BOTTLENECK_ENABLED", True)
    result_on = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"])
    assert "khipu_regime_last" in result_on


def test_balance_correct_always_satisfies_constraint():
    rng = np.random.default_rng(0)
    for _ in range(200):
        t = rng.normal(size=N_AXES)
        q = np.sign(t)
        q[q == 0] = 1.0
        q = balance_correct(q, t)
        assert abs(int(q.sum())) <= 1
        assert set(np.unique(q)).issubset({-1.0, 1.0})


def test_default_projection_is_deterministic():
    from khipu_bio_alert import _default_projection
    W1 = _default_projection(D_EMBED)
    W2 = _default_projection(D_EMBED)
    assert np.array_equal(W1, W2)
    assert W1.shape == (N_AXES, D_EMBED)


def test_regime_agreement_identical_and_opposite():
    q = np.array([1, -1, 1, 1, -1, 1, -1, -1, 1], dtype=float)
    assert regime_agreement_score(q, q) == pytest.approx(1.0)
    assert regime_agreement_score(q, -q) == pytest.approx(-1.0)


# ---------------------------------------------------------------------
# make_embedding_window - kształt/skończoność dla każdego typu sygnału
# ---------------------------------------------------------------------

@pytest.mark.parametrize("scenario,signal_type", [
    ("ecg_normal", "ecg"),
    ("eeg_normal", "eeg"),
    ("pulse_normal", "pulse"),
    ("resp_normal", "resp"),
])
def test_make_embedding_window_shape_and_finite(scenario, signal_type):
    d = make_demo_data(scenario)
    fs = d["fs"]
    window = int(10 * fs) if signal_type != "pulse" else int(120 * fs)
    window = max(window, 8)
    x_win = d["x"][:window]
    t_win = d["t"][:window]
    emb = make_embedding_window(x_win, t_win, fs, signal_type)
    assert emb.shape == (D_EMBED,)
    assert np.all(np.isfinite(emb))


def test_make_embedding_window_handles_very_short_window_without_crashing():
    d = make_demo_data("ecg_normal")
    fs = d["fs"]
    emb = make_embedding_window(d["x"][:5], d["t"][:5], fs, "ecg")
    assert emb.shape == (D_EMBED,)
    assert np.all(np.isfinite(emb))


# ---------------------------------------------------------------------
# regime_score_series - kształt, spójność, przypadek zbyt krótkiego sygnału
# ---------------------------------------------------------------------

def test_regime_score_series_shapes_consistent_on_demo_ecg():
    d = make_demo_data("ecg_normal")
    result = regime_score_series(d["x"], d["t"], d["fs"], "ecg")
    scores, idx = result["scores"], result["window_end_idx"]
    assert len(scores) == len(idx)
    assert len(scores) > 0
    assert np.all(scores >= -1.0 - 1e-9) and np.all(scores <= 1.0 + 1e-9)
    assert np.all(np.diff(idx) > 0)
    assert np.all(idx < len(d["x"]))


def test_regime_score_series_empty_for_too_short_signal():
    d = make_demo_data("ecg_normal")
    result = regime_score_series(d["x"][:50], d["t"][:50], d["fs"], "ecg")
    assert len(result["scores"]) == 0
    assert len(result["window_end_idx"]) == 0


def test_regime_score_series_is_deterministic():
    d = make_demo_data("resp_normal")
    r1 = regime_score_series(d["x"], d["t"], d["fs"], "resp")
    r2 = regime_score_series(d["x"], d["t"], d["fs"], "resp")
    assert np.array_equal(r1["scores"], r2["scores"])
    assert np.array_equal(r1["window_end_idx"], r2["window_end_idx"])


@pytest.mark.parametrize("scenario,signal_type", [
    ("eeg_normal", "eeg"),
    ("pulse_normal", "pulse"),
    ("resp_normal", "resp"),
])
def test_regime_score_series_works_on_all_signal_types(scenario, signal_type):
    d = make_demo_data(scenario)
    result = regime_score_series(d["x"], d["t"], d["fs"], signal_type)
    assert len(result["scores"]) > 0


# ---------------------------------------------------------------------
# regime_alerts - logika progu
# ---------------------------------------------------------------------

def test_regime_alerts_fires_only_below_threshold():
    scores = np.array([0.9, 0.1, -0.4, -0.6, -1.0])
    idx = np.array([10, 20, 30, 40, 50])
    t = np.arange(100) / 10.0
    alerts = regime_alerts(scores, idx, t, threshold=-0.5)
    assert [a["index"] for a in alerts] == [40, 50]
    assert all(a["score"] <= -0.5 for a in alerts)
    assert all("Zbiorcza zmiana stanu sygnału (KHIPU)" in a["message"] for a in alerts)


def test_regime_alerts_boundary_is_inclusive():
    alerts = regime_alerts(np.array([-0.5]), np.array([7]), np.arange(20) / 2.0, threshold=-0.5)
    assert len(alerts) == 1


def test_regime_alerts_empty_when_nothing_crosses_threshold():
    scores = np.array([0.9, 0.5, 0.1, -0.2])
    idx = np.array([1, 2, 3, 4])
    t = np.arange(10) / 1.0
    alerts = regime_alerts(scores, idx, t, threshold=KHIPU_ALERT_THRESHOLD)
    assert alerts == []
