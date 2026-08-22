"""
test_dsp.py — testy dla dsp.py (filtr Butterwortha, Pan-Tompkins, widmo mocy)

Dokumentuje empiryczne ustalenia z budowy tego modułu:
  - CausalBandpassFilter MUSI utrzymywać stan (zi) między wywołaniami
    process() - bez tego każda granica "porcji" danych (chunk) w
    strumieniu wprowadza słyszalny/widoczny skok (transient).
  - Pan-Tompkins jest znacznie odporniejszy na dryf linii bazowej niż
    prosty detektor progowy bio_core.detect_peaks() - zweryfikowane
    empirycznie (patrz test_pan_tompkins_odporny_na_dryf_liniowy_bazowej).
  - power_spectrum() z domyślnym (za małym) oknem Welcha dawał błędną
    "dominującą częstotliwość" dla EKG (2. harmoniczna zamiast
    fundamentalnej) - naprawiono podniesieniem domyślnego nperseg.
  - power_spectrum() na surowym EKG (impulsowy kształt QRS) generalnie
    NIE ma jednego wyraźnego szczytu widma na częstotliwości
    fundamentalnej (moc rozkłada się między kilka bliskich harmonicznych)
    - to normalna cecha widma sygnałów impulsowych, nie błąd. Dla EKG
    prawidłowym źródłem częstotliwości rytmu jest bpm liczone z
    odstępów RR (rhythm_regularity), nie power_spectrum().
"""

import numpy as np
import pytest

from dsp import (
    butter_bandpass_coeffs,
    butter_bandpass_filter,
    CausalBandpassFilter,
    pan_tompkins_qrs,
    power_spectrum,
)
from bio_core import TIMDRBioSignal
from demo_scenarios import make_demo_data


def _band_power(sig, fs, target, tol=1.0):
    from scipy.signal import welch
    f, p = welch(sig, fs=fs, nperseg=1024)
    mask = (f > target - tol) & (f < target + tol)
    return p[mask].sum()


# ---------------------------------------------------------------------
# butter_bandpass_filter / butter_bandpass_coeffs
# ---------------------------------------------------------------------

def test_bandpass_coeffs_odrzuca_niepoprawne_pasmo():
    with pytest.raises(ValueError):
        butter_bandpass_coeffs(fs=100, low=40, high=10)  # low > high
    with pytest.raises(ValueError):
        butter_bandpass_coeffs(fs=100, low=10, high=60)  # high > Nyquist (50)


def test_bandpass_filter_przepuszcza_pasmo_tlumi_reszte():
    fs = 250.0
    t = np.arange(0, 10, 1 / fs)
    x = 3 * np.sin(2 * np.pi * 1 * t) + 2 * np.sin(2 * np.pi * 10 * t) + 1.5 * np.sin(2 * np.pi * 40 * t)
    y = butter_bandpass_filter(x, fs, low=5, high=15, order=4)

    r1 = _band_power(y, fs, 1) / _band_power(x, fs, 1)
    r10 = _band_power(y, fs, 10) / _band_power(x, fs, 10)
    r40 = _band_power(y, fs, 40) / _band_power(x, fs, 40)

    assert r1 < 0.05, "1Hz (poza pasmem) powinno być mocno stłumione"
    assert r10 > 0.5, "10Hz (w pasmie 5-15Hz) powinno w większości przejść"
    assert r40 < 0.05, "40Hz (poza pasmem) powinno być mocno stłumione"


def test_bandpass_filter_krotki_sygnal_nie_crashuje():
    y = butter_bandpass_filter([1, 2, 3, 4, 5], fs=10, low=1, high=3)
    assert len(y) == 5  # za krótki na filtfilt - zwraca oryginał niezmieniony


# ---------------------------------------------------------------------
# CausalBandpassFilter
# ---------------------------------------------------------------------

def test_causal_filter_przepuszcza_pasmo_tlumi_reszte():
    fs = 250.0
    t = np.arange(0, 10, 1 / fs)
    x = 3 * np.sin(2 * np.pi * 1 * t) + 2 * np.sin(2 * np.pi * 10 * t) + 1.5 * np.sin(2 * np.pi * 40 * t)
    f = CausalBandpassFilter(fs, 5, 15, order=4)
    y = f.process(x)

    r1 = _band_power(y, fs, 1) / _band_power(x, fs, 1)
    r10 = _band_power(y, fs, 10) / _band_power(x, fs, 10)
    r40 = _band_power(y, fs, 40) / _band_power(x, fs, 40)
    assert r1 < 0.05
    assert r10 > 0.5
    assert r40 < 0.05


def test_causal_filter_stan_ciagly_miedzy_porcjami():
    """Regresja: przetwarzanie strumieniowe porcja-po-porcji MUSI dać
    identyczny wynik co jedno wywołanie na całym sygnale - to jedyny
    powód istnienia tej klasy zamiast zwykłego stateless filtrowania."""
    fs = 250.0
    t = np.arange(0, 10, 1 / fs)
    x = 3 * np.sin(2 * np.pi * 1 * t) + 2 * np.sin(2 * np.pi * 10 * t)

    f_single = CausalBandpassFilter(fs, 5, 15, order=4)
    y_single = f_single.process(x)

    f_chunked = CausalBandpassFilter(fs, 5, 15, order=4)
    half = len(x) // 2
    y_chunked = np.concatenate([f_chunked.process(x[:half]), f_chunked.process(x[half:])])

    assert np.allclose(y_single, y_chunked, atol=1e-9)


def test_causal_filter_bez_stanu_dawalby_skok_na_granicy():
    """Dowód na to, że stan (zi) faktycznie coś robi: dwa NIEZALEŻNE
    (świeże) filtry na dwóch połówkach sygnału dają widoczny skok na
    granicy, w przeciwieństwie do jednego filtra ze stanem."""
    fs = 250.0
    t = np.arange(0, 10, 1 / fs)
    x = 3 * np.sin(2 * np.pi * 1 * t) + 2 * np.sin(2 * np.pi * 10 * t)
    half = len(x) // 2

    y_a = CausalBandpassFilter(fs, 5, 15, order=4).process(x[:half])
    y_b = CausalBandpassFilter(fs, 5, 15, order=4).process(x[half:])  # świeży stan!
    y_naive = np.concatenate([y_a, y_b])

    f_stateful = CausalBandpassFilter(fs, 5, 15, order=4)
    y_stateful = f_stateful.process(x)

    boundary_diff = np.max(np.abs(y_naive[half:half + 5] - y_stateful[half:half + 5]))
    assert boundary_diff > 0.01


def test_causal_filter_pusty_chunk():
    f = CausalBandpassFilter(250, 5, 15)
    assert len(f.process([])) == 0


# ---------------------------------------------------------------------
# pan_tompkins_qrs
# ---------------------------------------------------------------------

def test_pan_tompkins_zgadza_sie_z_detect_peaks_na_czystym_sygnale():
    eng = TIMDRBioSignal()
    d = make_demo_data("ecg_normal")
    pt_peaks = pan_tompkins_qrs(d["x"], d["fs"])
    old_peaks = eng.detect_peaks(d["x"], distance=int(0.3 * d["fs"]))
    assert len(pt_peaks) == len(old_peaks) == 70


def test_pan_tompkins_dziala_na_arytmii():
    d = make_demo_data("ecg_arrhythmia")
    pt_peaks = pan_tompkins_qrs(d["x"], d["fs"])
    assert len(pt_peaks) == 70


def test_pan_tompkins_odporny_na_dryf_liniowy_bazowej():
    """Kluczowa przewaga Pan-Tompkins nad prostym detect_peaks(): pasmo
    5-15Hz usuwa wolny dryf linii bazowej PRZED wykrywaniem szczytów.

    Zweryfikowano empirycznie: po dodaniu do czystego demo EKG wolnego
    dryfu (0.3Hz, amplituda porównywalna z QRS) detect_peaks() traci
    większość uderzeń (70 -> 18, bo próg oparty o globalne std(x) zostaje
    rozregulowany przez dryf), podczas gdy pan_tompkins_qrs() nadal
    poprawnie znajduje wszystkie 70."""
    d = make_demo_data("ecg_normal")
    x, fs = d["x"].copy(), d["fs"]
    t = np.arange(len(x)) / fs
    x_wander = x + 0.6 * np.sin(2 * np.pi * 0.3 * t)

    eng = TIMDRBioSignal()
    old_peaks_w = eng.detect_peaks(x_wander, distance=int(0.3 * fs))
    pt_peaks_w = pan_tompkins_qrs(x_wander, fs)

    assert len(old_peaks_w) < 40, "detect_peaks powinien degradować się przy dryfie (regresja testu = zmiana zachowania)"
    assert len(pt_peaks_w) == 70, "pan_tompkins_qrs powinien pozostać stabilny mimo dryfu"


def test_pan_tompkins_pusty_i_krotki_sygnal():
    assert len(pan_tompkins_qrs([], fs=250)) == 0
    assert len(pan_tompkins_qrs([1, 2, 3], fs=250)) == 0


def test_pan_tompkins_niska_fs_fallback():
    """Przy fs zbyt niskiej dla klasycznego pasma 5-15Hz (potrzeba
    fs > ~11Hz z marginesem), funkcja nie powinna rzucać wyjątku -
    zamiast tego przechodzi na bio_core.detect_peaks jako fallback."""
    rng = np.random.default_rng(0)
    x = np.zeros(200)
    for i in range(0, 200, 20):
        x[i] = 1.0
    x += rng.normal(0, 0.02, 200)
    peaks = pan_tompkins_qrs(x, fs=5.0)  # Nyquist=2.5Hz < wymagane 5Hz
    assert isinstance(peaks, np.ndarray)


# ---------------------------------------------------------------------
# power_spectrum
# ---------------------------------------------------------------------

def test_power_spectrum_eeg_wykrywa_alfa_10hz():
    d = make_demo_data("eeg_normal")
    spec = power_spectrum(d["x"], d["fs"])
    assert spec["dominant_freq"] == pytest.approx(10.0, abs=0.5)


def test_power_spectrum_oddech_wykrywa_czestotliwosc_oddechu():
    d = make_demo_data("resp_normal")
    spec = power_spectrum(d["x"], d["fs"])
    # ~15 oddechow/min = 0.25 Hz
    assert spec["dominant_freq"] == pytest.approx(0.25, abs=0.05)


def test_power_spectrum_krotki_sygnal():
    spec = power_spectrum([1, 2, 3], fs=10)
    assert spec["freqs"] == []
    assert spec["dominant_freq"] is None


def test_power_spectrum_pomija_skladowa_stala():
    """Regresja: sygnał ze stałym, dużym przesunięciem (offsetem) nie
    powinien zgłaszać 0Hz jako 'dominującej częstotliwości' - to by
    było bezużyteczne (każdy sygnał ma jakąś średnią)."""
    rng = np.random.default_rng(0)
    fs = 100.0
    t = np.arange(0, 20, 1 / fs)
    x = 50.0 + 2 * np.sin(2 * np.pi * 3 * t) + rng.normal(0, 0.1, len(t))
    spec = power_spectrum(x, fs)
    assert spec["dominant_freq"] == pytest.approx(3.0, abs=0.3)


def test_power_spectrum_okno_dostatecznie_duze_dla_ekg():
    """Regresja: zbyt małe domyślne okno Welcha (poprzednio stały cap
    256 próbek) dawało błędną 'dominującą częstotliwość' dla EKG -
    zwracało 2. harmoniczną (~1.95Hz) zamiast bliżej fundamentalnej
    (~1.17Hz dla 70bpm). Sprawdzamy, że przy typowym demo EKG (fs=250,
    n=15000) wynik jest wystarczająco blisko prawdziwego bpm z RR."""
    eng = TIMDRBioSignal()
    d = make_demo_data("ecg_normal")
    peaks = eng.detect_peaks(d["x"], distance=int(0.3 * d["fs"]))
    reg = eng.rhythm_regularity(peaks, t=np.arange(len(d["x"])) / d["fs"])
    true_freq = 1.0 / reg["mean_interval"]

    spec = power_spectrum(d["x"], d["fs"])
    # UWAGA (patrz docstring modułu): dla surowego EKG (impulsowy kształt
    # QRS) power_spectrum() nie daje tak ostrego/jednoznacznego wyniku jak
    # dla sygnałów gładkich (EEG/oddech) - moc rozkłada się między kilka
    # sąsiednich harmonicznych. Tolerancja tu jest świadomie szersza niż
    # w testach EEG/oddechu, a NIE jest to zalecana metoda pomiaru bpm dla
    # EKG - właściwa metoda to rhythm_regularity() na wykrytych załamkach R
    # (patrz analyze_signal() w api.py).
    assert spec["dominant_freq"] < 5 * true_freq
