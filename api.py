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

import csv
import io
import json
import os
import time

import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

from bio_core import TIMDRBioSignal
from bio_trigger import BioTrigger
from demo_scenarios import SCENARIOS, make_demo_data
from dsp import CausalBandpassFilter, butter_bandpass_filter, pan_tompkins_qrs, power_spectrum

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

# Pasma filtra Butterwortha (Hz) do OPCJONALNEGO wyświetlania/analizy
# przefiltrowanego sygnału (parametr ?filter=1) - dobrane pod typowe pasmo
# fizjologiczne danego sygnału, NIEZALEŻNE od wewnętrznego pasma 5-15Hz,
# którego pan_tompkins_qrs() używa zawsze do wykrywania załamków R (to
# dwa różne zastosowania filtracji - patrz README, sekcja "Filtracja").
# Dla "pulse" (fs=0.5Hz, Nyquist=0.25Hz) pasmo pomijamy - zbyt niska
# częstotliwość próbkowania na sensowną filtrację pasmowoprzepustową.
FILTER_BAND_BY_TYPE = {
    "ecg": (0.5, 40.0),
    "eeg": (1.0, 45.0),
    "resp": (0.05, 1.0),
}


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


def analyze_signal(t, x, fs, signal_type: str, apply_filter: bool = False, include_khipu: bool = True) -> dict:
    t = np.asarray(t, dtype=float)
    x = np.asarray(x, dtype=float)
    result = {"signal_type": signal_type, "fs": fs, "n": len(x)}

    # Opcjonalna filtracja pasmowoprzepustowa (offline, zerofazowa) do
    # WYŚWIETLANIA/analizy statystycznej - patrz FILTER_BAND_BY_TYPE.
    # NIEZALEŻNA od wewnętrznego filtra Pan-Tompkins (zawsze aktywny dla
    # EKG, własne pasmo 5-15Hz specyficzne dla QRS).
    filter_info = None
    x_analysis = x
    if apply_filter and signal_type in FILTER_BAND_BY_TYPE and len(x) > 0:
        low, high = FILTER_BAND_BY_TYPE[signal_type]
        nyq = fs / 2.0
        if 0 < low < high < nyq:
            try:
                x_filtered = butter_bandpass_filter(x, fs, low, high, order=4)
                x_analysis = x_filtered
                filter_info = {"low_hz": low, "high_hz": high, "type": "butterworth_bandpass_zerophase"}
                result["filtered"] = x_filtered.tolist()
            except ValueError:
                filter_info = None
    result["filter_applied"] = filter_info

    if signal_type == "ecg":
        # Pan-Tompkins (dsp.py) zamiast prostego detect_peaks() - odporny
        # na dryf linii bazowej (zweryfikowano empirycznie w test_dsp.py:
        # detect_peaks traci ~75% uderzeń przy dryfie 0.3Hz, Pan-Tompkins
        # zachowuje 100%). Zawsze działa na SUROWYM x (ma własny wewnętrzny
        # filtr QRS-specyficzny 5-15Hz), niezależnie od apply_filter.
        peaks = pan_tompkins_qrs(x, fs)
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
            "qrs_method": "pan_tompkins",
        })

        # Widmo mocy na surowym EKG jest zwracane tylko informacyjnie -
        # dla impulsowego kształtu QRS "dominująca częstotliwość" widma NIE
        # jest wiarygodnym miernikiem bpm (moc rozkłada się między kilka
        # sąsiednich harmonicznych - zweryfikowano w test_dsp.py). Właściwe
        # źródło bpm to `bpm` powyżej (z odstępów RR).
        result["spectrum"] = power_spectrum(x, fs)
        result["spectrum_note"] = (
            "Dla surowego EKG widmo mocy NIE jest wiarygodnym źródłem bpm "
            "(kształt impulsowy QRS rozmywa moc na kilku harmonicznych) - "
            "użyj pola 'bpm' (liczone z odstępów RR)."
        )
    else:
        max_lag = min(MAX_LAG_BY_TYPE.get(signal_type, 60), max(2, len(x_analysis) // 3))
        periods, power = engine.rhythm(x_analysis, max_lag=max_lag)
        anomalies = engine.anomalies(x_analysis, factor=3.5).tolist()
        twist_idx = engine.twist(x_analysis, t=t, factor=3.5).tolist()

        envelope_ranges = []
        if signal_type in ENVELOPE_WINDOW_S_BY_TYPE:
            window = int(ENVELOPE_WINDOW_S_BY_TYPE[signal_type] * fs)
            if window >= 4 and len(x_analysis) >= window * 2:
                ranges = engine.envelope_drop(x_analysis, window=window, factor=3.0)
                envelope_ranges = [{"start_idx": a, "end_idx": b, "start_s": a / fs, "end_s": b / fs} for a, b in ranges]

        slope, _ = engine.trend(t, x_analysis, window=min(len(x_analysis), max(10, int(len(x_analysis) * 0.15))))

        result.update({
            "rhythm_power": power,
            "rhythm_periods_samples": periods[:5],
            "anomalies_idx": anomalies,
            "twist_idx": twist_idx,
            "envelope_drop_ranges": envelope_ranges,
            "recent_trend_slope": slope,
            "spectrum": power_spectrum(x_analysis, fs),
        })

    # OPCJONALNY, DODATKOWY alert "zbiorcza zmiana stanu sygnału" (patrz
    # khipu_bio_alert.py) - łączy WSZYSTKIE cechy okna (rytm, anomalie,
    # twist, trend...) w jeden dyskretny odcisk stanu i porównuje sąsiednie
    # okna czasu. Domyślnie WYŁĄCZONY (KHIPU_BOTTLENECK_ENABLED=False w
    # khipu_bio_alert.py) - dopóki ktoś świadomie nie włączy tej flagi,
    # wynik jest identyczny jak przed dodaniem tego modułu. Liczony na
    # SUROWYM `x` (nie x_analysis) niezależnie od apply_filter, żeby wynik
    # zawsze odpowiadał parametrom zwalidowanym w README. Failuje cicho -
    # to dodatkowy sygnał, awaria tutaj nie ma prawa wywrócić reszty analizy.
    #
    # `include_khipu=False` (używane przez /api/stream, patrz niżej) wyłącza
    # TEN blok niezależnie od KHIPU_BOTTLENECK_ENABLED - walidacja tego modułu
    # (patrz README, sekcja KHIPU) była robiona WYŁĄCZNIE na pełnych,
    # gotowych nagraniach demo, nie na krótkich, narastających oknach
    # strumienia na żywo; okna niektórych typów (np. puls: 120s) są też
    # dłuższe niż domyślny bufor streamingu tego typu, więc regime_score_series
    # dostałoby na starcie streamu za mało danych na sensowny wynik.
    if include_khipu:
        try:
            from khipu_bio_alert import (
                KHIPU_BOTTLENECK_ENABLED, KHIPU_VALIDATED_TYPES, KHIPU_ALERT_THRESHOLD,
                regime_score_series, regime_alerts,
            )
            if KHIPU_BOTTLENECK_ENABLED:
                khipu_result = regime_score_series(x, t, fs, signal_type)
                khipu_scores = khipu_result["scores"]
                if len(khipu_scores):
                    alerts = regime_alerts(khipu_scores, khipu_result["window_end_idx"], t)
                    result["khipu_regime_last"] = round(float(khipu_scores[-1]), 3)
                    result["khipu_regime_mean"] = round(float(np.mean(khipu_scores)), 3)
                    result["khipu_regime_alerts"] = [a["message"] for a in alerts]
                    result["khipu_regime_alerts_idx"] = [a["index"] for a in alerts]
                    result["n_khipu_regime_alerts"] = len(alerts)
                    result["khipu_regime_alert_active"] = bool(khipu_scores[-1] <= KHIPU_ALERT_THRESHOLD)
                    result["khipu_regime_validated"] = signal_type in KHIPU_VALIDATED_TYPES
        except Exception:
            pass

    # PODSUMOWANIE: BioTrigger (bio_trigger.py) - jeden, priorytetyzowany
    # wynik "co jest najważniejsze i gdzie" nad WSZYSTKIMI powyższymi,
    # równoległymi polami (anomalies_idx/twist_idx/envelope_drop_ranges/
    # beat_amplitude_anomalies/arrhythmia_suspected). Nie zastępuje żadnego
    # z nich - dashboard może dalej pokazywać wszystkie osobno; to
    # dodatkowe, zwięzłe pole na wierzchu. Failuje cicho jak KHIPU wyżej -
    # to dodatkowe podsumowanie, awaria tutaj nie ma prawa wywrócić reszty.
    try:
        trig = BioTrigger().analyze(result)
        result["trigger"] = trig.as_dict()
    except Exception:
        pass

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


def _parse_bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "tak", "on")


@app.route("/api/demo")
def demo():
    scenario = request.args.get("scenario", "ecg_normal")
    apply_filter = _parse_bool(request.args.get("filter"))
    if scenario not in SCENARIOS:
        return jsonify({"error": f"nieznany scenariusz '{scenario}'. Dostępne: {list(SCENARIOS)}"}), 400

    d = make_demo_data(scenario)
    result = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"], apply_filter=apply_filter)
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
    apply_filter = _parse_bool(body.get("filter"))

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
    result = analyze_signal(t, x, fs, signal_type, apply_filter=apply_filter)
    result.update({
        "t": t.tolist(),
        "x": x.tolist(),
        "is_demo": False,
        "disclaimer": DISCLAIMER,
    })
    return jsonify(_clean(result))


# ---------------------------------------------------------------------
# Eksport JSON/CSV
# ---------------------------------------------------------------------

def _build_export_payload(scenario=None, custom_body=None, apply_filter=False):
    """Wspólna logika dla /api/export/demo i /api/export/analyze - zwraca
    (result_dict, filename_stub) albo rzuca ValueError z komunikatem."""
    if scenario is not None:
        if scenario not in SCENARIOS:
            raise ValueError(f"nieznany scenariusz '{scenario}'. Dostępne: {list(SCENARIOS)}")
        d = make_demo_data(scenario)
        result = analyze_signal(d["t"], d["x"], d["fs"], d["signal_type"], apply_filter=apply_filter)
        result.update({
            "scenario": scenario, "label": d["label"],
            "t": d["t"].tolist(), "x": d["x"].tolist(), "is_demo": True,
        })
        for key in ("irregular_window_s", "burst_window_s", "event_window_s", "apnea_window_s"):
            if key in d:
                result[key] = list(d[key])
        return result, scenario

    body = custom_body or {}
    signal_type = body.get("signal_type", "pulse")
    fs = body.get("fs")
    values = body.get("values")
    if signal_type not in ("ecg", "eeg", "pulse", "resp"):
        raise ValueError(f"signal_type musi być jednym z: ecg, eeg, pulse, resp (podano '{signal_type}')")
    if not fs or fs <= 0:
        raise ValueError("wymagane pole 'fs' > 0")
    if not values or not isinstance(values, list) or len(values) < 10:
        raise ValueError("wymagane pole 'values' (min. 10 próbek)")
    x = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(x)):
        raise ValueError("'values' zawiera NaN/Infinity")
    t = np.arange(len(x)) / fs
    result = analyze_signal(t, x, fs, signal_type, apply_filter=apply_filter)
    result.update({"t": t.tolist(), "x": x.tolist(), "is_demo": False})
    return result, f"wlasny_{signal_type}"


def _result_to_csv(result: dict) -> str:
    """Buduje tabelaryczny CSV: t, x, [filtered], + kolumny znacznikowe
    (0/1) zależne od typu sygnału. Metadane skalarne (bpm, rr_cv, moc
    rytmu itd.) NIE trafiają do CSV (to tabela, nie dokument) - dostępne
    w wariancie JSON eksportu."""
    t = result.get("t", [])
    x = result.get("x", [])
    n = len(x)
    filtered = result.get("filtered")
    signal_type = result.get("signal_type")

    fieldnames = ["i", "t_s", "x"]
    if filtered is not None:
        fieldnames.append("x_filtered")

    marker_cols = {}
    if signal_type == "ecg":
        peaks = set(result.get("peaks", []))
        beat_anom = set(result.get("beat_amplitude_anomalies", []))
        marker_cols["is_r_peak"] = peaks
        marker_cols["is_anomalous_beat"] = beat_anom
    else:
        marker_cols["is_anomaly"] = set(result.get("anomalies_idx", []))
        marker_cols["is_twist"] = set(result.get("twist_idx", []))
    fieldnames.extend(marker_cols.keys())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(fieldnames)
    for i in range(n):
        row = [i, t[i] if i < len(t) else "", x[i]]
        if filtered is not None:
            row.append(filtered[i] if i < len(filtered) else "")
        for col_set in marker_cols.values():
            row.append(1 if i in col_set else 0)
        writer.writerow(row)
    return buf.getvalue()


@app.route("/api/export/demo")
def export_demo():
    scenario = request.args.get("scenario", "ecg_normal")
    fmt = request.args.get("format", "json").lower()
    apply_filter = _parse_bool(request.args.get("filter"))
    try:
        result, stub = _build_export_payload(scenario=scenario, apply_filter=apply_filter)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return _export_response(result, stub, fmt)


@app.route("/api/export/analyze", methods=["POST"])
def export_analyze():
    body = request.get_json(force=True, silent=True) or {}
    fmt = body.get("format", "json").lower()
    apply_filter = _parse_bool(body.get("filter"))
    try:
        result, stub = _build_export_payload(custom_body=body, apply_filter=apply_filter)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return _export_response(result, stub, fmt)


def _export_response(result: dict, stub: str, fmt: str):
    clean = _clean(result)
    clean["disclaimer"] = DISCLAIMER
    ts = time.strftime("%Y%m%d_%H%M%S")
    if fmt == "csv":
        csv_text = _result_to_csv(clean)
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="timdr_bio_{stub}_{ts}.csv"'},
        )
    if fmt == "json":
        return Response(
            json.dumps(clean, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="timdr_bio_{stub}_{ts}.json"'},
        )
    return jsonify({"error": f"nieobsługiwany format '{fmt}' (dostępne: json, csv)"}), 400


# ---------------------------------------------------------------------
# Live streaming (Server-Sent Events) - symulacja akwizycji "na żywo"
# ---------------------------------------------------------------------

# Bufor analizy (sekundy sygnału wstecz brane pod uwagę przy okresowym
# przeliczaniu statystyk) i domyślne przyspieszenie symulacji ("speed"x
# realnego czasu) - dobrane tak, by demo dało się obejrzeć w rozsądnym
# czasie nawet dla wolnych sygnałów (puls: prawdziwe demo trwa 598s).
STREAM_BUFFER_S_BY_TYPE = {"ecg": 15, "eeg": 10, "resp": 40, "pulse": 180}
STREAM_DEFAULT_SPEED_BY_TYPE = {"ecg": 20.0, "eeg": 20.0, "resp": 30.0, "pulse": 60.0}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(_clean(data), ensure_ascii=False)}\n\n"


@app.route("/api/stream")
def stream():
    """
    Symuluje akwizycję sygnału NA ŻYWO z prędkością `speed`x realnego
    czasu (domyślnie dobrana per typ sygnału - patrz
    STREAM_DEFAULT_SPEED_BY_TYPE) - w PRAWDZIWYM czasie serwer wysyła
    kolejne próbki gotowego demo-sygnału małymi porcjami przez SSE
    (Server-Sent Events), tak jakby przychodziły z urządzenia pomiarowego.

    Co jakiś czas (gdy w buforze uzbiera się >= 2s nowych danych)
    dolicza się też zdarzenie "analysis" z pełną analizą (analyze_signal)
    na OSTATNICH STREAM_BUFFER_S_BY_TYPE[typ] sekundach zebranego sygnału
    (nie na całej historii od początku - realny monitor też patrzy na
    ostatnie okno, nie na cały zapis od rana).

    Query params: scenario (wymagany), speed (opcjonalny mnożnik czasu).
    """
    scenario = request.args.get("scenario", "ecg_normal")
    if scenario not in SCENARIOS:
        return jsonify({"error": f"nieznany scenariusz '{scenario}'. Dostępne: {list(SCENARIOS)}"}), 400

    d = make_demo_data(scenario)
    t_full, x_full, fs, sig_type = d["t"], d["x"], d["fs"], d["signal_type"]

    default_speed = STREAM_DEFAULT_SPEED_BY_TYPE.get(sig_type, 20.0)
    try:
        speed = float(request.args.get("speed", default_speed))
    except (TypeError, ValueError):
        speed = default_speed
    speed = max(0.5, min(speed, 500.0))

    buffer_s = STREAM_BUFFER_S_BY_TYPE.get(sig_type, 20)
    chunk_samples = max(1, int(round(fs * 0.5)))  # ~0.5s sygnału na porcję
    analysis_every_samples = max(chunk_samples, int(round(fs * 2.0)))  # przelicz co ~2s nowych danych

    @stream_with_context
    def generate():
        yield _sse_event("meta", {
            "scenario": scenario, "label": d["label"], "signal_type": sig_type,
            "fs": fs, "n_total": len(x_full), "speed": speed, "disclaimer": DISCLAIMER,
        })

        sent = 0
        since_analysis = 0
        n = len(x_full)
        while sent < n:
            end = min(n, sent + chunk_samples)
            t_chunk = t_full[sent:end]
            x_chunk = x_full[sent:end]
            yield _sse_event("sample", {"t": t_chunk.tolist(), "x": x_chunk.tolist()})

            since_analysis += (end - sent)
            sent = end

            if since_analysis >= analysis_every_samples or sent >= n:
                since_analysis = 0
                buf_start = max(0, sent - int(buffer_s * fs))
                t_buf = t_full[buf_start:sent]
                x_buf = x_full[buf_start:sent]
                if len(x_buf) >= 10:
                    try:
                        # include_khipu=False: patrz komentarz przy bloku KHIPU
                        # w analyze_signal() - moduł nie jest zwalidowany na
                        # krótkich, narastających oknach trybu na żywo.
                        analysis = analyze_signal(t_buf, x_buf, fs, sig_type, include_khipu=False)
                        analysis["window_start_s"] = float(t_buf[0])
                        analysis["window_end_s"] = float(t_buf[-1])
                        yield _sse_event("analysis", analysis)
                    except Exception as e:  # nie przerywaj streamu, jeśli okno jest degenerate
                        yield _sse_event("analysis_error", {"error": str(e)})

            time.sleep((chunk_samples / fs) / speed)

        yield _sse_event("done", {"n_sent": sent})

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
