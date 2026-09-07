"""
test_bio_trigger_api.py — testy integracji bio_trigger.py z
api.py::analyze_signal() (wpięcie, nie logika dispatchera - ta jest w
test_bio_trigger.py).
"""
from api import analyze_signal
from demo_scenarios import SCENARIOS, make_demo_data


def _run(scenario):
    d = make_demo_data(scenario)
    return analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"])


def test_trigger_key_present_dla_kazdego_scenariusza():
    for scenario in SCENARIOS:
        result = _run(scenario)
        assert "trigger" in result, f"brak klucza 'trigger' dla {scenario}"
        assert result["trigger"]["type"] in {
            "envelope_drop", "arrhythmia", "beat_anomaly", "twist", "anomaly", "none",
        }


def test_resp_apnea_daje_envelope_drop():
    """Dokładnie przypadek opisany w bio_core.py::envelope_drop() -
    bezdech nie jest widoczny dla anomalies()/twist() (wartości w
    normalnym zakresie oscylacji), ale JEST widoczny jako utrata
    zmienności - to powinien być najwyższy priorytet w wyniku."""
    result = _run("resp_apnea")
    assert result["trigger"]["type"] == "envelope_drop"
    assert result["trigger"]["triggered"] is True


def test_ecg_arrhythmia_daje_arrhythmia():
    result = _run("ecg_arrhythmia")
    assert result["trigger"]["type"] == "arrhythmia"


def test_ecg_normal_nie_wywoluje_triggera():
    """Kontrola negatywna: zdrowy, regularny rytm zatokowy nie powinien
    dawać żadnego zdarzenia w podsumowaniu."""
    result = _run("ecg_normal")
    assert result["trigger"]["type"] == "none"
    assert result["trigger"]["triggered"] is False
