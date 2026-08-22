"""
khipu_bio_alert.py — opcjonalny, DODATKOWY alert "zbiorcza zmiana stanu sygnału"
================================================================================
NIE JEST WYROBEM MEDYCZNYM (patrz zastrzeżenie w bio_core.py/README.md -
dotyczy w całości również tego modułu).

Kontekst: cała reszta bio_core.py/dsp.py analizuje sygnał CECHA PO CESZE -
rhythm(), anomalies(), twist(), envelope_drop(), pan_tompkins_qrs() -
każda funkcja patrzy na JEDNĄ własność sygnału naraz. To jest świadomy i
poprawny wybór projektowy (patrz docstring bio_core.py - różne cechy mają
różne skale/znaczenie, łączenie ich naiwnie przed analizą rytmu tworzy
artefakty typu rektyfikacja).

Ten moduł robi coś innego i węższego: bierze WSZYSTKIE te już policzone,
pojedyncze cechy dla krótkiego okna czasu naraz, ściska je w jeden
DYSKRETNY "odcisk stanu" (9-osiowy kod ±1, State9Bottleneck z
jbackk-lang/KHIPU-NEURAL - wierny port matematyki, tak jak w
analizator-gieldowy-v3/khipu_bottleneck.py) i porównuje odcisk sąsiednich
okien czasu. Spadek zgodności = KILKA cech zmieniło się jednocześnie -
sygnał, którego żaden POJEDYNCZY detektor osobno mógłby nie złapać (bo
każda cecha z osobna zmieniła się tylko trochę, ale RAZEM to spora
zmiana). To jest DODATKOWY, KOMPLEMENTARNY alert - nie zastępuje, nie
podnosi ani nie obniża wiarygodności żadnego z istniejących wyników.

Różnice względem analizator-gieldowy-v3/khipu_bottleneck.py (świadome,
nie przeoczenie):
  - BRAK calibrate()/treningu. Tam kalibracja miała (słabą, jawnie
    oznaczoną jako heurystyczną) etykietę "ta sama faza" ze znaku FLOW.
    Tutaj NIE MA żadnej analogicznie uzasadnionej etykiety "ten sam stan
    fizjologiczny" - wymyślanie jednej tylko po to, żeby było czym
    trenować, byłoby mniej uczciwe niż jej brak. Projekcja jest więc
    WYŁĄCZNIE deterministycznym, nietrenowanym "twardym filtrem"
    (_default_projection - ten sam wzorzec Walsha-Hadamarda co w wersji
    giełdowej).
  - Cechy wejściowe są NAJPIERW z-score'owane (MAD-z, dokładnie ten sam
    `_mad_z` co reszta bio_core.py) PO WSZYSTKICH OKNACH danego przebiegu,
    zanim trafią do projekcji - bo cechy mają tu bardzo różne surowe skale
    (bpm rzędu dziesiątek, cv rzędu 0.01-0.3, moc rytmu w [-1,1] itd.), w
    odróżnieniu od giełdy, gdzie make_embedding budował od razu wielkości
    bezwymiarowe. Bez tego kroku projekcja byłaby zdominowana przez
    cechę o największej surowej skali.

KHIPU_BOTTLENECK_ENABLED — wyłącznik (kill switch). Gdy `False`,
api.py/dashboard zachowują się DOKŁADNIE tak jak przed dodaniem tego
modułu - zero zmiany istniejącego wyniku. Testy (`test_khipu_bio_alert.py`,
`test_api_khipu.py`) sprawdzają działanie przełącznika w OBIE strony, nie
zakładają żadnej konkretnej wartości domyślnej wpisanej w tym pliku.

KHIPU_ALERT_THRESHOLD — ustalona wartość HEURYSTYCZNA (jak w wersji
giełdowej) - nie wyprowadzona z rozkładu danych klinicznych (bo takich
tu nie ma i nie będzie - patrz zastrzeżenie). Zweryfikowana WYŁĄCZNIE na
w pełni syntetycznych scenariuszach demo z demo_scenarios.py (patrz
README, sekcja KHIPU, po wyniki tej weryfikacji) - punkt startowy do
dostrojenia, nie potwierdzona liczba.
"""
from __future__ import annotations

import numpy as np

from bio_core import TIMDRBioSignal, _mad_z

KHIPU_BOTTLENECK_ENABLED = True

N_AXES = 9
D_EMBED = 6

KHIPU_ALERT_THRESHOLD = -0.5

# Okno/krok (sekundy) per typ sygnału - dostrojone EMPIRYCZNIE na 8
# scenariuszach demo (demo_scenarios.py), sprawdzając zarówno fałszywe
# alarmy na scenariuszach *_normal, jak i wykrycie znanego, wstrzykniętego
# epizodu w scenariuszach nieprawidłowych (patrz README, sekcja KHIPU, po
# pełną tabelę wyników tej walidacji - NIE jest to jednolicie dobry wynik,
# patrz KHIPU_VALIDATED_TYPES niżej).
WINDOW_S_BY_TYPE = {"ecg": 10.0, "eeg": 5.0, "resp": 30.0, "pulse": 120.0}
STEP_S_BY_TYPE = {"ecg": 2.5, "eeg": 2.5, "resp": 7.5, "pulse": 15.0}

# Typy sygnału, dla których walidacja na demo_scenarios.py dała ROZSĄDNY
# wynik (zero/mało fałszywych alarmów na scenariuszu *_normal I trafienie
# w okolicy znanego wstrzykniętego epizodu): tylko "ecg" i "eeg". Dla
# "resp"/"pulse" mechanizm DZIAŁA (nie crashuje, ma sensowny kształt), ale
# walidacja pokazała słabą dyskryminację (zbyt mało okien w typowym
# nagraniu na stabilny z-score kolumn - patrz README) - NIE polegaj na tym
# dla resp/pulse bez dalszego dostrojenia. `api.py` używa tego zbioru do
# oznaczenia wyniku jako `khipu_regime_validated: False` dla reszty typów,
# zamiast cichego ukrycia ograniczenia.
KHIPU_VALIDATED_TYPES = frozenset({"ecg", "eeg"})

# max_lag dla rhythm() per typ - te same wartości co MAX_LAG_BY_TYPE w api.py
# (celowo zduplikowane, nie zaimportowane z api.py - patrz uwaga w README o
# unikaniu importu api.py z tego modułu, żeby nie tworzyć zależności
# okrężnej: api.py ma docelowo importować STĄD, nie odwrotnie).
_MAX_LAG_BY_TYPE = {"eeg": 40, "resp": 60, "pulse": 90}

_engine = TIMDRBioSignal()
_EPS = 1e-9


# ---------------------------------------------------------------------
# State9Bottleneck — wierny port matematyki z KHIPU-NEURAL, WYŁĄCZNIE
# forward (bez backward/calibrate - patrz docstring modułu, dlaczego).
# ---------------------------------------------------------------------

def balance_correct(q: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Koryguje wektor +/-1 `q` tak, żeby |sum(q)| <= 1 (warunek F4-RED).
    Port 1:1 z khipu_neural/quantize.py (patrz też analizator-gieldowy-v3/
    khipu_bottleneck.py, gdzie ten sam kod jest gradientowo zweryfikowany
    do ~1e-11 - tu nie ma gradientu do weryfikacji, bo nie ma treningu)."""
    q = q.copy()
    total = int(q.sum())
    while abs(total) > 1:
        majority_sign = 1 if total > 0 else -1
        idx = np.where(q == majority_sign)[0]
        pick = idx[np.argmin(np.abs(t[idx]))]
        q[pick] = -majority_sign
        total = int(q.sum())
    return q


def _default_projection(d_in: int) -> np.ndarray:
    """Ustalona (nielosowa) projekcja d_in -> N_AXES osi - identyczny
    wzorzec co analizator-gieldowy-v3/khipu_bottleneck.py::_default_projection
    (dyskretna transformata Walsha-Hadamarda obcięta do N_AXES wierszy) -
    w pełni deterministyczna i odtwarzalna, żeby dwa uruchomienia na tych
    samych danych dawały identyczny wynik."""
    W = np.zeros((N_AXES, d_in))
    for k in range(N_AXES):
        for j in range(d_in):
            W[k, j] = 1.0 if ((k + 1) * (j + 1)) % (k + 2) < (k + 2) / 2 else -1.0
    return W / np.sqrt(d_in)


def _encode(x_row: np.ndarray, W: np.ndarray) -> np.ndarray:
    proj = W @ x_row
    t = np.tanh(proj)
    q = np.sign(t)
    q[q == 0] = 1.0
    return balance_correct(q, t)


def regime_agreement_score(q_i: np.ndarray, q_j: np.ndarray) -> float:
    """Średnia iloczynu per-oś (reguła GIPU) - [-1, 1]. +1 = identyczny
    dyskretny odcisk stanu w obu oknach, -1 = maksymalnie odwrotny."""
    return float(np.mean(q_i * q_j))


# ---------------------------------------------------------------------
# Embedding okna - per typ sygnału, z JUŻ ISTNIEJĄCYCH funkcji bio_core.py
# (świadomie: ECG idzie ścieżką peak/RR-based, jak w api.py::analyze_signal,
# NIE surowym anomalies()/rhythm() na przebiegu - dokładnie to ograniczenie,
# które README już dokumentuje dla surowego EKG).
# ---------------------------------------------------------------------

def _raw_features_ecg(x_win: np.ndarray, t_win: np.ndarray, fs: float) -> np.ndarray:
    try:
        from dsp import pan_tompkins_qrs
        peaks = pan_tompkins_qrs(x_win, fs)
    except Exception:
        peaks = np.array([], dtype=int)
    if len(peaks) < 2:
        peaks = _engine.detect_peaks(x_win, distance=max(1, int(0.3 * fs)))

    reg = _engine.rhythm_regularity(peaks, t=t_win)
    rate = 60.0 / reg["mean_interval"] if reg["mean_interval"] else 0.0
    cv = reg["cv"] if reg["cv"] is not None else 0.0
    rate_density = len(peaks) / max(len(x_win), 1)

    if len(peaks) >= 2:
        amp = x_win[peaks]
        amp_cv = float(np.std(amp) / (np.mean(np.abs(amp)) + _EPS))
    else:
        amp_cv = 0.0

    local_std = float(np.std(x_win))
    busy = float(np.mean(np.abs(np.diff(x_win)))) if len(x_win) > 1 else 0.0

    return np.array([rate, cv, rate_density, amp_cv, local_std, busy], dtype=float)


def _raw_features_generic(x_win: np.ndarray, t_win: np.ndarray, fs: float, signal_type: str) -> np.ndarray:
    n = len(x_win)
    max_lag = min(_MAX_LAG_BY_TYPE.get(signal_type, 60), max(2, n // 3))
    _, power = _engine.rhythm(x_win, max_lag=max_lag)

    anomaly_density = len(_engine.anomalies(x_win, factor=3.5)) / max(n, 1)
    twist_density = len(_engine.twist(x_win, t=t_win, factor=3.5)) / max(n, 1)

    local_std = float(np.std(x_win))
    slope, _ = _engine.trend(t_win, x_win, window=n) if n >= 2 else (0.0, 0.0)
    slope_norm = slope / (local_std + _EPS)
    busy = float(np.mean(np.abs(np.diff(x_win)))) if n > 1 else 0.0

    return np.array([power, anomaly_density, twist_density, slope_norm, local_std, busy], dtype=float)


def make_embedding_window(x_win: np.ndarray, t_win: np.ndarray, fs: float, signal_type: str) -> np.ndarray:
    """(D_EMBED,) surowy (jeszcze nie znormalizowany) wektor cech okna -
    patrz _raw_features_ecg / _raw_features_generic dla znaczenia per typ."""
    if signal_type == "ecg":
        return _raw_features_ecg(x_win, t_win, fs)
    return _raw_features_generic(x_win, t_win, fs, signal_type)


def _zscore_columns(raw: np.ndarray) -> np.ndarray:
    """MAD-z KAŻDEJ kolumny (cechy) NIEZALEŻNIE, po wszystkich oknach -
    dokładnie `_mad_z` z bio_core.py, zastosowane kolumna po kolumnie, żeby
    cechy o różnych surowych skalach (bpm vs cv vs moc rytmu) stały się
    porównywalne PRZED wejściem do projekcji."""
    out = np.zeros_like(raw)
    for j in range(raw.shape[1]):
        out[:, j] = _mad_z(raw[:, j])
    return out


# ---------------------------------------------------------------------
# Główna funkcja: seria zgodności stanu między sąsiednimi oknami
# ---------------------------------------------------------------------

def regime_score_series(x, t, fs: float, signal_type: str,
                         window_s: float | None = None, step_s: float | None = None) -> dict:
    """Zwraca dict {"scores": (n_windows-1,), "window_end_idx": (n_windows-1,)}.

    window_end_idx to indeks OSTATNIEJ próbki okna j+1 dla każdego wyniku -
    używany do naniesienia alertu na wykres sygnału (ta sama oś co
    anomalies_idx/twist_idx/peaks), analogicznie do bar_indices w
    analizator-gieldowy-v3/khipu_bottleneck.py."""
    x = np.asarray(x, dtype=float)
    t = np.asarray(t, dtype=float)
    n = len(x)

    window_s = window_s if window_s is not None else WINDOW_S_BY_TYPE.get(signal_type, 10.0)
    step_s = step_s if step_s is not None else STEP_S_BY_TYPE.get(signal_type, window_s / 2)
    window = max(4, int(round(window_s * fs)))
    step = max(1, int(round(step_s * fs)))

    starts = list(range(0, n - window + 1, step))
    if len(starts) < 2:
        return {"scores": np.array([], dtype=float), "window_end_idx": np.array([], dtype=int)}

    raw = np.array([
        make_embedding_window(x[s:s + window], t[s:s + window], fs, signal_type)
        for s in starts
    ], dtype=float)
    normalized = _zscore_columns(raw)

    W = _default_projection(normalized.shape[1])
    codes = [_encode(row, W) for row in normalized]

    scores = np.array([
        regime_agreement_score(codes[i], codes[i + 1])
        for i in range(len(codes) - 1)
    ], dtype=float)
    window_end_idx = np.array([
        starts[i + 1] + window - 1
        for i in range(len(codes) - 1)
    ], dtype=int)

    return {"scores": scores, "window_end_idx": window_end_idx}


def regime_alerts(scores: np.ndarray, window_end_idx: np.ndarray, t,
                   threshold: float = KHIPU_ALERT_THRESHOLD) -> list[dict]:
    """Alerty dla okien, gdzie regime_agreement_score <= threshold - patrz
    docstring modułu. `t` to znaczniki czasu PEŁNEGO sygnału (do zamiany
    indeksu próbki na sekundy w komunikacie)."""
    t = np.asarray(t, dtype=float)
    alerts = []
    for score, idx in zip(scores, window_end_idx):
        if score <= threshold:
            t_s = float(t[idx]) if 0 <= idx < len(t) else None
            msg = (
                f"Zbiorcza zmiana stanu sygnału (KHIPU) w okolicy t={t_s:.1f}s (score={score:.2f})"
                if t_s is not None
                else f"Zbiorcza zmiana stanu sygnału (KHIPU) (score={score:.2f})"
            )
            alerts.append({
                "index": int(idx),
                "t_s": t_s,
                "score": round(float(score), 3),
                "message": msg,
            })
    return alerts
