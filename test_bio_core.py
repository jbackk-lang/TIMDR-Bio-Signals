"""
test_bio_core.py — testy dla bio_core.py (TIMDR-Bio-Signals)

Dokumentuje:
  Bug 1 (detect_peaks): próg oparty o MAD zawodzi, gdy prawdziwe szczyty
         są rzadkie względem długości sygnału (MAD zdominowany przez
         szum tła) - naprawiono przejściem na próg oparty o std(x).
  Bug 2 (odrzucony kandydat użytkownika, rhythm()): wersja z detrendem
         np.linspace(x[0], x[-1], n) i BEZ ograniczenia do lokalnych
         maksimów zgłaszała periodyczność na PRAWIE KAŻDYM opóźnieniu
         (także na sygnale bez regularnego rytmu / arytmii) - odtworzone
         i odrzucone poniżej, z uzasadnieniem w README.md.
"""

import numpy as np
import pytest

from bio_core import TIMDRBioSignal, TIMDRBioFusion, _mad_z


@pytest.fixture()
def eng():
    return TIMDRBioSignal()


def _regular_ecg_like(n=2000, rr=20, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(0, n, rr):
        x[i] = 1.0
    x += rng.normal(0, 0.02, n)
    return x


def _irregular_ecg_like(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    i = 0
    while i < n:
        x[i] = 1.0
        i += rng.integers(12, 35)
    x += rng.normal(0, 0.02, n)
    return x


# ---------------------------------------------------------------------
# rhythm() — regularność / arytmia
# ---------------------------------------------------------------------

def test_rhythm_regularny_sygnal_ma_silny_szczyt(eng):
    x = _regular_ecg_like(rr=20)
    periods, power = eng.rhythm(x, max_lag=60)
    assert power > 0.9
    assert 20 in periods


def test_rhythm_nieregularny_sygnal_brak_periodycznosci(eng):
    x = _irregular_ecg_like()
    periods, power = eng.rhythm(x, max_lag=60)
    assert power == 0.0
    assert periods == []


def test_rhythm_tylko_lokalne_maksima_nie_kazdy_lag_powyzej_progu(eng):
    """Regresja: rhythm() nie może zwracać dziesiątek 'okresów' dla
    sygnału z jednym wyraźnym rytmem - patrz Bug 2 (odrzucony kandydat)."""
    x = _regular_ecg_like(rr=20)
    periods, _ = eng.rhythm(x, max_lag=60)
    assert len(periods) < 5, f"zbyt wiele 'wykrytych okresów' ({len(periods)}) - prawdopodobnie brak filtra lokalnych maksimów"


def test_bug2_reprodukcja_odrzuconego_kandydata_rhythm():
    """Odtwarza dokładnie logikę odrzuconego kandydata (linspace-detrend +
    brak filtra lokalnych maksimów) i pokazuje, że zgłasza periodyczność
    na sygnale BEZ regularnego rytmu (arytmia) - dyskwalifikujący błąd
    dla wykrywacza arytmii."""
    def candidate_rhythm(x, max_lag, power_thresh=0.4):
        x = np.asarray(x, float)
        n = len(x)
        trend = np.linspace(x[0], x[-1], n)
        x_d = x - trend
        x_d = x_d - np.mean(x_d)
        ac = np.zeros(max_lag + 1)
        for lag in range(max_lag + 1):
            if lag == 0:
                ac[lag] = np.dot(x_d, x_d) / n
            else:
                overlap = n - lag
                ac[lag] = np.dot(x_d[:-lag], x_d[lag:]) / overlap
        ac /= ac[0]
        lags = np.arange(1, len(ac))
        power = ac[1:]
        dom = np.where(power >= power_thresh)[0]
        if dom.size == 0:
            return [], 0.0
        return lags[dom].tolist(), float(power[dom].max())

    x_irregular = _irregular_ecg_like()
    periods, power = candidate_rhythm(x_irregular, max_lag=60)
    # BUG: kandydat zgłasza "rytm" nawet na nieregularnym (arytmicznym) sygnale
    assert power > 0.4
    assert len(periods) > 10, "kandydat zgłasza periodyczność na prawie każdym lagu, nie tylko lokalne maksima"


# ---------------------------------------------------------------------
# detect_peaks() — Bug 1
# ---------------------------------------------------------------------

def test_bug1_detect_peaks_nie_lapie_szumu_miedzy_szczytami(eng):
    """Regresja: próg oparty o std (nie MAD) - na sygnale z rzadkimi,
    dużymi szczytami detect_peaks nie powinien wykrywać próbek szumu
    tła jako fałszywych szczytów."""
    x = _regular_ecg_like(n=500, rr=20, seed=1)
    peaks = eng.detect_peaks(x, distance=10)
    expected = list(range(0, 500, 20))
    assert len(peaks) == len(expected), f"oczekiwano {len(expected)} szczytów, wykryto {len(peaks)}: {peaks}"


def test_bug1_reprodukcja_oryginalnego_bledu_progu_mad():
    """Odtwarza oryginalny (zepsuty) próg z MAD i pokazuje, że dawał
    próg praktycznie w skali szumu, przepuszczając fałszywe wykrycia."""
    rng = np.random.default_rng(1)
    n = 500
    x = np.zeros(n)
    for i in range(0, n, 20):
        x[i] = 1.0
    x += rng.normal(0, 0.02, n)

    med = np.median(x)
    mad = np.median(np.abs(x - med))
    std = np.std(x)

    buggy_threshold = med + 1.5 * mad
    fixed_threshold = med + 3.0 * std

    # próg z MAD leży praktycznie w paśmie samego szumu (~2-3x odchylenie std szumu = 0.02)
    assert buggy_threshold < 0.05
    # próg ze std wyraźnie oddziela szum (~0.02-0.06) od prawdziwych szczytów (~1.0)
    assert 0.1 < fixed_threshold < 0.9


def test_detect_peaks_dziala_na_pustym_i_krotkim_sygnale(eng):
    assert len(eng.detect_peaks([], distance=5)) == 0
    assert len(eng.detect_peaks([1.0, 2.0], distance=5)) == 0


# ---------------------------------------------------------------------
# anomalies() / twist() / trend()
# ---------------------------------------------------------------------

def test_anomalies_wykrywa_wstrzykniety_epizod(eng):
    rng = np.random.default_rng(1)
    n = 500
    pulse = 70 + rng.normal(0, 1.5, n)
    pulse[250:280] = 130 + rng.normal(0, 2, 30)
    idx = eng.anomalies(pulse, factor=3.5)
    assert len(idx) > 0
    assert all(200 <= i <= 300 for i in idx)


def test_twist_z_czasem_i_bez_maja_podobny_niski_falszywy_alarm():
    """Zweryfikowano empirycznie: obie ścieżki twist() (z jawnym `t` przez
    np.gradient i bez `t` przez np.diff) mają porównywalny, niski odsetek
    fałszywych alarmów na czystym szumie."""
    eng_local = TIMDRBioSignal()
    rates_with_t, rates_without_t = [], []
    for seed in range(10):
        rng = np.random.default_rng(seed)
        n = 2000
        t = np.arange(n, dtype=float)
        x = 70 + rng.normal(0, 1.5, n)
        rates_with_t.append(len(eng_local.twist(x, t=t, factor=3.5)) / n)
        rates_without_t.append(len(eng_local.twist(x, factor=3.5)) / n)
    assert np.mean(rates_with_t) < 0.02
    assert np.mean(rates_without_t) < 0.02


def test_trend_centrowanie_dziala_na_duzych_znacznikach_czasu(eng):
    """Regresja: nachylenie nie może zależeć od przesunięcia zegara (np.
    epoka Unix vs. czas względny) - patrz historia tego bugu w innych
    modułach TIMDR tego repo (TTF/trend)."""
    n = 200
    x = np.linspace(70, 85, n) + np.random.default_rng(0).normal(0, 0.5, n)

    t_relative = np.arange(n, dtype=float)
    t_epoch = t_relative + 1_700_000_000.0

    slope_rel, _ = eng.trend(t_relative, x, window=50)
    slope_epoch, _ = eng.trend(t_epoch, x, window=50)

    assert slope_rel == pytest.approx(slope_epoch, rel=1e-6)


def test_trend_pusty_i_za_krotki_sygnal(eng):
    assert eng.trend([], [], window=10) == (0.0, 0.0)
    assert eng.trend([1.0], [5.0], window=10) == (0.0, 0.0)


# ---------------------------------------------------------------------
# envelope_drop() — bezdech / spadek obwiedni
# ---------------------------------------------------------------------

def test_envelope_drop_wykrywa_splaszczenie(eng):
    rng = np.random.default_rng(7)
    fs = 5.0
    n = 1500
    t = np.arange(n) / fs
    x = np.sin(2 * np.pi * t * 15 / 60) + rng.normal(0, 0.06, n)
    i0, i1 = int(150 * fs), int(170 * fs)
    x[i0:i1] = rng.normal(0, 0.03, i1 - i0)

    ranges = eng.envelope_drop(x, window=int(10 * fs), factor=3.0)
    assert len(ranges) >= 1
    r_start, r_end = ranges[0]
    # wykryty zakres powinien pokrywać się (choćby częściowo) z prawdziwym epizodem
    assert r_start <= i1 and r_end >= i0


def test_envelope_drop_brak_falszywego_alarmu_na_normalnym_sygnale(eng):
    rng = np.random.default_rng(7)
    fs = 5.0
    n = 1500
    t = np.arange(n) / fs
    x = np.sin(2 * np.pi * t * 15 / 60) + rng.normal(0, 0.06, n)
    ranges = eng.envelope_drop(x, window=int(10 * fs), factor=3.0)
    assert ranges == []


def test_envelope_drop_za_krotki_sygnal_nie_crashuje(eng):
    assert eng.envelope_drop([1, 2, 3], window=100) == []


# ---------------------------------------------------------------------
# rhythm_regularity()
# ---------------------------------------------------------------------

def test_rhythm_regularity_regularne_uderzenia(eng):
    peaks = np.arange(0, 1000, 20)
    reg = eng.rhythm_regularity(peaks)
    assert reg["cv"] == pytest.approx(0.0, abs=1e-9)
    assert reg["mean_interval"] == pytest.approx(20.0)


def test_rhythm_regularity_za_malo_uderzen(eng):
    reg = eng.rhythm_regularity([5])
    assert reg["n_intervals"] == 0
    assert reg["cv"] is None


# ---------------------------------------------------------------------
# TIMDRBioFusion
# ---------------------------------------------------------------------

def test_fuse_wymaga_tej_samej_dlugosci_kanalow():
    fusion = TIMDRBioFusion()
    with pytest.raises(ValueError):
        fusion.fuse(a=[1, 2, 3], b=[1, 2])


def test_fuse_wykrywa_anomalie_na_polaczonym_sygnale():
    rng = np.random.default_rng(3)
    n = 500
    pulse = 70 + rng.normal(0, 1.5, n)
    resp = 15 + rng.normal(0, 0.5, n)
    pulse[300:320] = 140
    resp[300:320] = 30

    fusion = TIMDRBioFusion()
    E = fusion.fuse(pulse=pulse, resp=resp)
    idx = set(fusion.anomalies(E, factor=3.0).tolist())
    # cały wstrzyknięty epizod (300-319) musi zostać wykryty (brak fałszywych negatywów)
    assert set(range(300, 320)).issubset(idx)
    # dopuszczalna niewielka liczba pojedynczych wykryć poza epizodem
    # (statystyczny poziom fałszywych alarmów przy factor=3.0 na czystym
    # szumie - patrz test_twist_z_czasem_i_bez_maja_podobny_niski_falszywy_alarm)
    outside = [i for i in idx if not (280 <= i <= 340)]
    assert len(outside) <= 5


def test_mad_z_plaski_sygnal_nie_dzieli_przez_zero():
    x = np.full(50, 5.0)
    z = _mad_z(x)
    assert np.all(z == 0.0)
