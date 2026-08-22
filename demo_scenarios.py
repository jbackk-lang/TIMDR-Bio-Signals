"""
demo_scenarios.py — W CAŁOŚCI SYNTETYCZNE sygnały fizjologiczne do demo.

Żaden z sygnałów poniżej nie pochodzi od prawdziwego pacjenta ani
prawdziwego urządzenia medycznego - wszystko jest wygenerowane
matematycznie (sinusoidy, szablony QRS, szum gaussowski) wyłącznie do
zademonstrowania działania bio_core.py. Kształty fal są UPROSZCZONE
(nie są klinicznie realistyczne w pełnej złożoności) - wystarczające do
pokazania rhythm/anomalies/twist/trend na sygnałach o rozsądnym
kształcie, nie do treningu ani walidacji rzeczywistych algorytmów
medycznych.
"""

import numpy as np


def _qrs_template(width: int = 6, amplitude: float = 1.0) -> np.ndarray:
    """Bardzo uproszczony kształt zespołu QRS (trójkątny spike), nie
    prawdziwa morfologia EKG."""
    half = width // 2
    up = np.linspace(0, amplitude, half)
    down = np.linspace(amplitude, 0, width - half)
    return np.concatenate([up, down])


def ecg_normal(seed: int = 1, fs: int = 250, duration_s: int = 60) -> dict:
    """EKG symulowane: rytm zatokowy ~70 bpm (RR ~0.857s), regularne odstępy."""
    rng = np.random.default_rng(seed)
    n = fs * duration_s
    t = np.arange(n) / fs
    x = np.zeros(n)

    rr_samples = int(0.857 * fs)  # ~70 bpm
    qrs = _qrs_template(width=int(0.08 * fs), amplitude=1.0)
    i = rr_samples // 2
    peak_indices = []
    while i + len(qrs) < n:
        x[i:i + len(qrs)] += qrs
        peak_indices.append(i + np.argmax(qrs))
        i += rr_samples

    x += rng.normal(0, 0.03, n)  # szum linii bazowej
    return {
        "t": t, "x": x, "fs": fs,
        "label": "EKG — rytm zatokowy prawidłowy (~70 bpm, syntetyczny)",
        "true_peaks": np.array(peak_indices),
    }


def ecg_arrhythmia(seed: int = 2, fs: int = 250, duration_s: int = 60) -> dict:
    """EKG symulowane z nieregularnym rytmem (jak migotanie przedsionków —
    'niemiarowość zupełna'): losowe odstępy RR w środkowej jednej trzeciej
    nagrania, prawidłowe poza nią."""
    rng = np.random.default_rng(seed)
    n = fs * duration_s
    t = np.arange(n) / fs
    x = np.zeros(n)
    qrs = _qrs_template(width=int(0.08 * fs), amplitude=1.0)

    rr_normal = int(0.857 * fs)
    irr_start, irr_end = n // 3, 2 * n // 3

    i = rr_normal // 2
    peak_indices = []
    while i + len(qrs) < n:
        x[i:i + len(qrs)] += qrs
        peak_indices.append(i + np.argmax(qrs))
        if irr_start < i < irr_end:
            # niemiarowość zupełna: RR losowe w szerokim zakresie
            i += rng.integers(int(0.45 * fs), int(1.35 * fs))
        else:
            i += rr_normal

    x += rng.normal(0, 0.03, n)
    return {
        "t": t, "x": x, "fs": fs,
        "label": "EKG — niemiarowość (nieregularne RR w środkowym segmencie, syntetyczny)",
        "true_peaks": np.array(peak_indices),
        "irregular_window_s": (irr_start / fs, irr_end / fs),
    }


def eeg_normal(seed: int = 3, fs: int = 128, duration_s: int = 30) -> dict:
    """EEG symulowane: dominacja pasma alfa (~10 Hz), typowa dla spoczynku
    z zamkniętymi oczami — bardzo uproszczone (jedna sinusoida + szum)."""
    rng = np.random.default_rng(seed)
    n = fs * duration_s
    t = np.arange(n) / fs
    alpha = 20 * np.sin(2 * np.pi * 10 * t)
    theta = 5 * np.sin(2 * np.pi * 5 * t + 0.6)
    noise = rng.normal(0, 4, n)
    x = alpha + theta + noise
    return {"t": t, "x": x, "fs": fs, "label": "EEG — rytm alfa w spoczynku (syntetyczny)"}


def eeg_seizure_like(seed: int = 4, fs: int = 128, duration_s: int = 30) -> dict:
    """EEG symulowane z wstrzykniętym epizodem 'napadopodobnym': nagły
    wzrost amplitudy i częstotliwości (uogólniona reprezentacja wyładowań
    typu spike-wave) na kilka sekund w środku nagrania."""
    rng = np.random.default_rng(seed)
    n = fs * duration_s
    t = np.arange(n) / fs
    alpha = 20 * np.sin(2 * np.pi * 10 * t)
    theta = 5 * np.sin(2 * np.pi * 5 * t + 0.6)
    noise = rng.normal(0, 4, n)
    x = alpha + theta + noise

    burst_start_s, burst_dur_s = duration_s * 0.45, 4.0
    i0 = int(burst_start_s * fs)
    i1 = int((burst_start_s + burst_dur_s) * fs)
    burst_t = t[i0:i1]
    x[i0:i1] += 90 * np.sin(2 * np.pi * 3 * burst_t) * np.sin(np.pi * (burst_t - burst_t[0]) / (burst_t[-1] - burst_t[0]))

    return {
        "t": t, "x": x, "fs": fs,
        "label": "EEG — epizod napadopodobny, syntetyczny (NIE prawdziwe dane kliniczne)",
        "burst_window_s": (burst_start_s, burst_start_s + burst_dur_s),
    }


def pulse_normal(seed: int = 5, fs: float = 0.5, duration_s: int = 600) -> dict:
    """Tętno (bpm) próbkowane co 2s przez 10 minut, ~70 bpm z naturalną
    zmiennością (uproszczona zatokowa arytmia oddechowa)."""
    rng = np.random.default_rng(seed)
    n = int(fs * duration_s)
    t = np.arange(n) / fs
    x = 70 + 3 * np.sin(2 * np.pi * t / 60) + rng.normal(0, 1.2, n)
    return {"t": t, "x": x, "fs": fs, "label": "Tętno — spoczynkowe ~70 bpm (syntetyczne)"}


def pulse_tachycardia(seed: int = 6, fs: float = 0.5, duration_s: int = 600) -> dict:
    """Tętno z epizodem częstoskurczu (nagły wzrost do ~140 bpm na 2 minuty)."""
    rng = np.random.default_rng(seed)
    n = int(fs * duration_s)
    t = np.arange(n) / fs
    x = 70 + 3 * np.sin(2 * np.pi * t / 60) + rng.normal(0, 1.2, n)

    ev_start_s, ev_dur_s = duration_s * 0.4, 120
    i0, i1 = int(ev_start_s * fs), int((ev_start_s + ev_dur_s) * fs)
    ramp = np.linspace(0, 1, min(int(10 * fs), i1 - i0))
    x[i0:i0 + len(ramp)] += ramp * 65
    x[i0 + len(ramp):i1] = 135 + rng.normal(0, 3, max(0, i1 - i0 - len(ramp)))
    down = np.linspace(1, 0, min(int(15 * fs), n - i1)) if i1 < n else np.array([])
    if len(down):
        x[i1:i1 + len(down)] += down * 60

    return {
        "t": t, "x": x, "fs": fs,
        "label": "Tętno — epizod częstoskurczu ~135 bpm (syntetyczny)",
        "event_window_s": (ev_start_s, ev_start_s + ev_dur_s),
    }


def resp_normal(seed: int = 7, fs: float = 5.0, duration_s: int = 300) -> dict:
    """Sygnał oddechowy (umowna jednostka rozszerzenia klatki piersiowej),
    ~15 oddechów/min, 5 minut nagrania."""
    rng = np.random.default_rng(seed)
    n = int(fs * duration_s)
    t = np.arange(n) / fs
    breaths_per_min = 15
    x = np.sin(2 * np.pi * t * breaths_per_min / 60) + rng.normal(0, 0.06, n)
    return {"t": t, "x": x, "fs": fs, "label": "Oddech — regularny ~15/min (syntetyczny)"}


def resp_apnea(seed: int = 8, fs: float = 5.0, duration_s: int = 300) -> dict:
    """Sygnał oddechowy z epizodem bezdechu (~20s spłaszczenia amplitudy)."""
    rng = np.random.default_rng(seed)
    n = int(fs * duration_s)
    t = np.arange(n) / fs
    breaths_per_min = 15
    x = np.sin(2 * np.pi * t * breaths_per_min / 60) + rng.normal(0, 0.06, n)

    apnea_start_s, apnea_dur_s = duration_s * 0.5, 20
    i0, i1 = int(apnea_start_s * fs), int((apnea_start_s + apnea_dur_s) * fs)
    x[i0:i1] = rng.normal(0, 0.03, i1 - i0)  # niemal płaska linia = brak ruchu oddechowego

    return {
        "t": t, "x": x, "fs": fs,
        "label": "Oddech — epizod bezdechu ~20s (syntetyczny)",
        "apnea_window_s": (apnea_start_s, apnea_start_s + apnea_dur_s),
    }


SCENARIOS = {
    "ecg_normal": ecg_normal,
    "ecg_arrhythmia": ecg_arrhythmia,
    "eeg_normal": eeg_normal,
    "eeg_seizure_like": eeg_seizure_like,
    "pulse_normal": pulse_normal,
    "pulse_tachycardia": pulse_tachycardia,
    "resp_normal": resp_normal,
    "resp_apnea": resp_apnea,
}

SIGNAL_TYPE_OF = {
    "ecg_normal": "ecg", "ecg_arrhythmia": "ecg",
    "eeg_normal": "eeg", "eeg_seizure_like": "eeg",
    "pulse_normal": "pulse", "pulse_tachycardia": "pulse",
    "resp_normal": "resp", "resp_apnea": "resp",
}


def make_demo_data(scenario: str, seed: int = None) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"Nieznany scenariusz: {scenario!r}. Dostępne: {list(SCENARIOS)}")
    fn = SCENARIOS[scenario]
    kwargs = {} if seed is None else {"seed": seed}
    data = fn(**kwargs)
    data["scenario"] = scenario
    data["signal_type"] = SIGNAL_TYPE_OF[scenario]
    return data
