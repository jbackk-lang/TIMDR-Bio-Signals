"""
test_bio_trigger.py — testy bio_trigger.py (BioTrigger).

Ten plik NIE re-weryfikuje matematyki bio_core.py (anomalies/twist/
envelope_drop/rhythm_regularity, już przetestowane w test_bio_core.py) -
to nie jest robota dispatchera. Dwa rodzaje testów:

1. test_anomaly_z_realnie_policzonym_bio_core - `anomalies_idx` w słowniku
   wyniku jest liczone PRAWDZIWYM TIMDRBioSignal.anomalies() (nie
   zamockowane), na ręcznie wyprowadzonym przykładzie (pojedynczy skok
   10->20 wśród 10 próbek - ten sam wzorzec MAD=0 -> fallback do
   rozstępu/4 jak w innych modułach TIMDR tego zestawu). Dowód, że
   dispatcher poprawnie odczytuje faktyczny wynik bio_core.
2. Reszta testów podaje RĘCZNIE ZBUDOWANE słowniki wynikowe (tej samej
   struktury co analyze_signal() z api.py) - testujemy WYŁĄCZNIE logikę
   priorytetów/mapowania dispatchera.
"""
from bio_core import TIMDRBioSignal
from bio_trigger import BioTrigger, BioTriggerType


# ----------------------------------------------------------------------
# 1) Test z realnie policzonym anomalies_idx (bio_core, bez mockowania)
# ----------------------------------------------------------------------

def test_anomaly_z_realnie_policzonym_bio_core():
    """
    x = [10]*10 z pojedynczym skokiem do 20 w idx=5.
    _mad_z: mediana=10, mad_raw=median(|x-10|)=0 (9 z 10 wartosci to 0)
    -> fallback span/4 = (20-10)/4 = 2.5. z[5]=(20-10)/2.5=4.0 > factor=3.5
    domyslny -> anomalies() zwraca [5]. Wszystkie inne pola wyniku
    nieobecne (brak innych kategorii) -> ANOMALY w lokalizacji 5.
    """
    x = [10.0] * 10
    x[5] = 20.0
    engine = TIMDRBioSignal()
    anomalies_idx = engine.anomalies(x, factor=3.5).tolist()
    assert anomalies_idx == [5]  # sanity - to jest to, co dispatcher dostanie

    result = {"anomalies_idx": anomalies_idx}
    trigger = BioTrigger()
    out = trigger.analyze(result)

    assert out.triggered is True
    assert out.trigger_type == BioTriggerType.ANOMALY
    assert out.location == 5


# ----------------------------------------------------------------------
# 2) Testy priorytetów/mapowania na ręcznie zbudowanych słownikach
# ----------------------------------------------------------------------

def test_priorytet_envelope_drop_nad_wszystkim():
    result = {
        "envelope_drop_ranges": [{"start_idx": 40, "end_idx": 90}],
        "arrhythmia_suspected": True,
        "peaks": [10, 20, 30],
        "beat_amplitude_anomalies": [15],
        "twist_idx": [5],
        "anomalies_idx": [1],
    }
    trigger = BioTrigger()
    out = trigger.analyze(result)
    assert out.trigger_type == BioTriggerType.ENVELOPE_DROP
    assert out.location == 40


def test_priorytet_arrhythmia_nad_beat_anomaly_i_reszta():
    result = {
        "arrhythmia_suspected": True,
        "peaks": [10, 25, 42],
        "rr_cv": 0.15,
        "beat_amplitude_anomalies": [25],
        "twist_idx": [5],
        "anomalies_idx": [1],
    }
    trigger = BioTrigger()
    out = trigger.analyze(result)
    assert out.trigger_type == BioTriggerType.ARRHYTHMIA
    assert out.location == 42  # ostatni wykryty zalamek R
    assert "0.15" in out.message


def test_priorytet_beat_anomaly_nad_twist_i_anomaly():
    result = {
        "arrhythmia_suspected": False,
        "beat_amplitude_anomalies": [30, 12],
        "twist_idx": [5],
        "anomalies_idx": [1],
    }
    trigger = BioTrigger()
    out = trigger.analyze(result)
    assert out.trigger_type == BioTriggerType.BEAT_ANOMALY
    assert out.location == 12  # min z listy


def test_priorytet_twist_nad_anomaly():
    result = {"twist_idx": [8, 3], "anomalies_idx": [1]}
    trigger = BioTrigger()
    out = trigger.analyze(result)
    assert out.trigger_type == BioTriggerType.TWIST
    assert out.location == 3


def test_anomaly_gdy_reszta_pusta():
    result = {"anomalies_idx": [7]}
    trigger = BioTrigger()
    out = trigger.analyze(result)
    assert out.triggered is True
    assert out.trigger_type == BioTriggerType.ANOMALY
    assert out.location == 7


def test_none_gdy_slownik_pusty():
    trigger = BioTrigger()
    out = trigger.analyze({})
    assert out.triggered is False
    assert out.trigger_type == BioTriggerType.NONE
    assert out.location is None


def test_arrhythmia_bez_peaks_daje_location_none():
    """Brzegowy przypadek: arrhythmia_suspected=True, ale brak listy
    peaks w wyniku (np. skrócona odpowiedź) - lokalizacja None, nie crash."""
    result = {"arrhythmia_suspected": True}
    trigger = BioTrigger()
    out = trigger.analyze(result)
    assert out.trigger_type == BioTriggerType.ARRHYTHMIA
    assert out.location is None


def test_get_last_zwraca_ostatni_wynik():
    trigger = BioTrigger()
    out = trigger.analyze({"anomalies_idx": [2]})
    assert trigger.get_last() is out
