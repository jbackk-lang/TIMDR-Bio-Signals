"""Testy integracji khipu_bio_alert.py z api.py::analyze_signal() - alert
"zbiorcza zmiana stanu sygnału" jest DODATKOWY i domyślnie WYŁĄCZONY.
Testy jawnie ustawiają flagę przez monkeypatch w obie strony (patrz
analogiczny wzorzec w analizator-gieldowy-v3/test_khipu_bottleneck.py) -
nie zakładają żadnej konkretnej wartości domyślnej wpisanej w pliku.
"""
import khipu_bio_alert
from api import analyze_signal
from demo_scenarios import make_demo_data


def test_khipu_keys_absent_when_disabled(monkeypatch):
    monkeypatch.setattr(khipu_bio_alert, "KHIPU_BOTTLENECK_ENABLED", False)
    d = make_demo_data("ecg_normal")
    result = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"])
    assert "khipu_regime_last" not in result
    assert "khipu_regime_alerts" not in result
    assert "n_khipu_regime_alerts" not in result
    assert "khipu_regime_alert_active" not in result
    assert "khipu_regime_validated" not in result


def test_khipu_keys_present_when_enabled(monkeypatch):
    monkeypatch.setattr(khipu_bio_alert, "KHIPU_BOTTLENECK_ENABLED", True)
    d = make_demo_data("ecg_normal")
    result = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"])

    assert -1.0 <= result["khipu_regime_last"] <= 1.0
    assert isinstance(result["n_khipu_regime_alerts"], int)
    assert isinstance(result["khipu_regime_alert_active"], bool)
    assert len(result["khipu_regime_alerts"]) == result["n_khipu_regime_alerts"]
    assert len(result["khipu_regime_alerts_idx"]) == result["n_khipu_regime_alerts"]
    assert result["khipu_regime_validated"] is True  # ecg jest w KHIPU_VALIDATED_TYPES
    for idx in result["khipu_regime_alerts_idx"]:
        assert 0 <= idx < result["n"]


def test_khipu_regime_validated_false_for_unvalidated_type(monkeypatch):
    monkeypatch.setattr(khipu_bio_alert, "KHIPU_BOTTLENECK_ENABLED", True)
    d = make_demo_data("resp_normal")
    result = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"])
    assert "khipu_regime_validated" in result
    assert result["khipu_regime_validated"] is False  # resp NIE jest w KHIPU_VALIDATED_TYPES


def test_khipu_excluded_when_include_khipu_false_even_if_globally_enabled(monkeypatch):
    """`/api/stream` (api.py) wywołuje analyze_signal(..., include_khipu=False)
    - moduł KHIPU nie jest zwalidowany na krótkich, narastających oknach
    trybu na żywo (patrz README, sekcja KHIPU). To musi działać niezależnie
    od globalnego przełącznika KHIPU_BOTTLENECK_ENABLED, żeby /api/stream
    nigdy nie wystawiał pól khipu_* - dokładnie to sprawdza ten test."""
    monkeypatch.setattr(khipu_bio_alert, "KHIPU_BOTTLENECK_ENABLED", True)
    d = make_demo_data("ecg_normal")
    result = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"], include_khipu=False)
    for key in (
        "khipu_regime_last", "khipu_regime_mean", "khipu_regime_alerts",
        "khipu_regime_alerts_idx", "n_khipu_regime_alerts",
        "khipu_regime_alert_active", "khipu_regime_validated",
    ):
        assert key not in result
