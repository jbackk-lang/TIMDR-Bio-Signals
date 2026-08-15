"""
api.py — TIMDR-Bio-Signals, lokalne REST API + dashboard
===========================================================
NIE JEST WYROBEM MEDYCZNYM. Narzędzie badawczo-edukacyjne do
przetwarzania sygnałów fizjologicznych (EKG/EEG/puls/oddech). Nie
diagnozuje, nie zastępuje personelu medycznego ani certyfikowanego
sprzętu. Patrz README.md.

Endpointy:
  GET  /                  -> dashboard (static/dashboard.html)
  GET  /api/health        -> healthcheck
  GET  /api/scenarios     -> lista dostępnych scenariuszy demo
  GET  /api/demo          -> analiza wybranego scenariusza demo (?scenario=...)
  POST /api/analyze       -> analiza WŁASNEGO sygnału przesłanego w body

Uruchomienie: `python api.py` (albo `run.bat`), potem
http://127.0.0.1:5050
"""

import os

import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from bio_core import TIMDRBioSignal
from demo_scenarios import SCENARIOS, make_demo_data

app = Flask(__name__, static_folder="static", static_url_path="")
engine = TIMDRBioSignal()

DISCLAIMER = (
    "Narzędzie badawczo-edukacyjne. NIE jest wyrobem medycznym, nie "
    "diagnozuje i nie zastępuje personelu medycznego ani certyfikowanego "
    "sprzętu (np. Holter EKG). Wyniki to statystyczne odchylenia "
    "względem lokalnej historii sygnału, nie rozpoznania kliniczne."
)

# max_lag (w próbkach) i okno envelope_drop dobrane pod typ sygnału -
# patrz demo.py dla uzasadnienia tych wartości.
MAX_LAG_BY_TYPE = {"eeg": 40, "resp": 60, "pulse": 90}
ENVELOPE_WINDOW_S_BY_TYPE = {"resp": 10, "pulse": 60}


def _clean(obj):
    """Zamienia NaN/Infinity na None przed jsonify (patrz analizator-gieldowy
    README, Bug 7 - ten sam problem może wystąpić tu przy skrajnych
    parametrach wejściowych)."""
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return _clean(float(obj))
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    return obj


def analyze_signal(t, x, fs, signal_type: str) -> dict:
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    result = {"signal_type": signal_type, "fs": fs, "n": len(x)}

    if signal_type == "ecg":
        distance = max(1, int(0.3 * fs))
        peaks = engine.detect_peaks(x, distance=distance)
        reg = engine.rhythm_regularity(peaks, t=t)
        beat_anomalies = []
        if len(peaks) >= 4:
            beat_anomalies = engine.anomalies(x[peaks], factor=3.5).tolist()

        bpm = 60.0 / reg["mean_interval"] if reg["mean_interval"] else None
        arrhythmia_suspected = bool(reg["cv"] is not None and reg["cv"] > 0.08)

        result.update({
            "peaks": peaks.tolist(),
            "n_peaks": len(peaks),
            "mean_rr_s": reg["mean_interval"],
            "bpm": bpm,
            "rr_cv": reg["cv"],
            "arrhythmia_suspected": arrhythmia_suspected,
            "beat_amplitude_anomalies": [int(peaks[i]) for i in beat_anomalies if i < len(peaks)],
        })
    else:
        max_lag = min(MAX_LAG_BY_TYPE.get(signal_type, 60), max(2, len(x) // 3))
        periods, power = engine.rhythm(x, max_lag=max_lag)
        anomalies = engine.anomalies(x, factor=3.5).tolist()
        twist_idx = engine.twist(x, t=t, factor=3.5).tolist()

        envelope_ranges = []
        if signal_type in ENVELOPE_WINDOW_S_BY_TYPE:
            window = int(ENVELOPE_WINDOW_S_BY_TYPE[signal_type] * fs)
            if window >= 4 and len(x) >= window * 2:
                ranges = engine.envelope_drop(x, window=window, factor=3.0)
                envelope_ranges = [{"start_idx": a, "end_idx": b, "start_s": a / fs, "end_s": b / fs} for a, b in ranges]

        slope, _ = engine.trend(t, x, window=min(len(x), max(10, int(len(x) * 0.15))))

        result.update({
            "rhythm_power": power,
            "rhythm_periods_samples": periods[:5],
            "anomalies_idx": anomalies,
            "twist_idx": twist_idx,
            "envelope_drop_ranges": envelope_ranges,
            "recent_trend_slope": slope,
        })

    return result


@app.route("/")
def dashboard():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "disclaimer": DISCLAIMER})


@app.route("/api/scenarios")
def scenarios():
    labels = {}
    for name in SCENARIOS:
        d = make_demo_data(name)
        labels[name] = {"label": d["label"], "signal_type": d["signal_type"], "fs": d["fs"]}
    return jsonify({"scenarios": labels, "disclaimer": DISCLAIMER})


@app.route("/api/demo")
def demo():
    scenario = request.args.get("scenario", "ecg_normal")
    if scenario not in SCENARIOS:
        return jsonify({"error": f"nieznany scenariusz '{scenario}'. Dostępne: {list(SCENARIOS)}"}), 400

    d = make_demo_data(scenario)
    result = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"])
    result.update({
        "scenario": scenario,
        "label": d["label"],
        "t": d["t"].tolist(),
        "x": d["x"].tolist(),
        "is_demo": True,
        "disclaimer": DISCLAIMER,
    })
    for key in ("irregular_window_s", "burst_window_s", "event_window_s", "apnea_window_s"):
        if key in d:
            result[key] = list(d[key])

    return jsonify(_clean(result))


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Body (JSON):
      signal_type: "ecg" | "eeg" | "pulse" | "resp"
      fs: float — częstotliwość próbkowania (Hz)
      values: [float, ...] — surowe wartości sygnału (bez znaczników czasu;
              znaczniki wyliczane jako i/fs)
    """
    body = request.get_json(force=True, silent=True) or {}
    signal_type = body.get("signal_type", "pulse")
    fs = body.get("fs")
    values = body.get("values")

    if signal_type not in ("ecg", "eeg", "pulse", "resp"):
        return jsonify({"error": f"signal_type musi być jednym z: ecg, eeg, pulse, resp (podano '{signal_type}')"}), 400
    if not fs or fs <= 0:
        return jsonify({"error": "wymagane pole 'fs' (częstotliwość próbkowania, Hz) > 0"}), 400
    if not values or not isinstance(values, list) or len(values) < 10:
        return jsonify({"error": "wymagane pole 'values' (lista liczb, min. 10 próbek)"}), 400

    try:
        x = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return jsonify({"error": "'values' musi być listą liczb"}), 400

    if not np.all(np.isfinite(x)):
        return jsonify({"error": "'values' zawiera NaN/Infinity"}), 400

    t = np.arange(len(x)) / fs
    result = analyze_signal(t, x, fs, signal_type)
    result.update({
        "t": t.tolist(),
        "x": x.tolist(),
        "is_demo": False,
        "disclaimer": DISCLAIMER,
    })
    return jsonify(_clean(result))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
