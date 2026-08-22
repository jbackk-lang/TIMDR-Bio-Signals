"""
test_demo_scenarios.py — sanity check dla syntetycznych scenariuszy demo.
"""

import numpy as np
import pytest

from demo_scenarios import SCENARIOS, SIGNAL_TYPE_OF, make_demo_data


@pytest.mark.parametrize("name", list(SCENARIOS.keys()))
def test_scenario_generuje_dane_o_spojnym_ksztalcie(name):
    d = make_demo_data(name)
    assert len(d["t"]) == len(d["x"])
    assert len(d["x"]) > 0
    assert np.all(np.isfinite(d["x"]))
    assert d["fs"] > 0
    assert d["signal_type"] == SIGNAL_TYPE_OF[name]


def test_ecg_normal_ma_regularne_rr():
    from bio_core import TIMDRBioSignal
    eng = TIMDRBioSignal()
    d = make_demo_data("ecg_normal")
    peaks = eng.detect_peaks(d["x"], distance=int(0.3 * d["fs"]))
    reg = eng.rhythm_regularity(peaks, t=d["t"])
    assert reg["cv"] is not None
    assert reg["cv"] < 0.05


def test_ecg_arrhythmia_ma_wyzsza_zmiennosc_rr_niz_normalne():
    from bio_core import TIMDRBioSignal
    eng = TIMDRBioSignal()
    normal = make_demo_data("ecg_normal")
    arr = make_demo_data("ecg_arrhythmia")

    peaks_n = eng.detect_peaks(normal["x"], distance=int(0.3 * normal["fs"]))
    peaks_a = eng.detect_peaks(arr["x"], distance=int(0.3 * arr["fs"]))
    cv_n = eng.rhythm_regularity(peaks_n, t=normal["t"])["cv"]
    cv_a = eng.rhythm_regularity(peaks_a, t=arr["t"])["cv"]

    assert cv_a > cv_n * 5


def test_resp_apnea_wykrywalny_przez_envelope_drop():
    from bio_core import TIMDRBioSignal
    eng = TIMDRBioSignal()
    d = make_demo_data("resp_apnea")
    ranges = eng.envelope_drop(d["x"], window=int(10 * d["fs"]), factor=3.0)
    assert len(ranges) >= 1


def test_pulse_tachycardia_wykrywalny_przez_anomalie():
    from bio_core import TIMDRBioSignal
    eng = TIMDRBioSignal()
    d = make_demo_data("pulse_tachycardia")
    idx = eng.anomalies(d["x"], factor=3.5)
    assert len(idx) > 0


def test_eeg_seizure_like_wykrywalny_przez_anomalie():
    from bio_core import TIMDRBioSignal
    eng = TIMDRBioSignal()
    d = make_demo_data("eeg_seizure_like")
    idx = eng.anomalies(d["x"], factor=3.5)
    assert len(idx) > 0


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        make_demo_data("nieistniejacy_scenariusz")
