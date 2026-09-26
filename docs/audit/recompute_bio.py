"""Przeliczenia dla audytu twierdzeń README (TIMDR-Bio-Signals). Reguły: docs/audit/CLAIM_AUDIT_PREREG.md.
Użycie (katalog repo): python docs/audit/recompute_bio.py  ->  docs/audit/RECOMPUTE_BIO.json
v1.1 (aneks 1): dodane bug1.noise_local_max_above_old i welch.ecg_dominant_by_nperseg; trend szuka liczb poza docs/audit.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))


def main():
    out = {}
    # testy
    counts = {}
    for f in sorted(REPO.glob("test_*.py")):
        p = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q", f.name],
                           cwd=REPO, capture_output=True, text=True, timeout=120)
        counts[f.name] = sum("::" in l for l in p.stdout.splitlines())
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=REPO, capture_output=True,
                       text=True, timeout=170)
    out["tests"] = {"per_file": counts, "total": sum(counts.values()), "tail": p.stdout.strip().splitlines()[-1:],
                    "returncode": p.returncode}

    # dane syntetyczne
    ext = {".csv", ".npz", ".npy", ".edf", ".dat", ".mat", ".h5", ".wav", ".hea"}
    files = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True).stdout.split()
    out["synthetic"] = {"data_files": [f for f in files if Path(f).suffix.lower() in ext],
                        "rng_in_demo": "np.random.default_rng" in (REPO / "demo_scenarios.py").read_text(encoding="utf-8")}

    from bio_core import TIMDRBioSignal, _mad_z
    from candidate_user import TIMDRBio
    from demo_scenarios import make_demo_data, SCENARIOS
    from dsp import CausalBandpassFilter, pan_tompkins_qrs, power_spectrum
    eng = TIMDRBioSignal()

    # filtr kauzalny (konfiguracja z test_dsp.py)
    fs = 250.0
    t = np.arange(0, 10, 1 / fs)
    x = 3 * np.sin(2 * np.pi * 1 * t) + 2 * np.sin(2 * np.pi * 10 * t)
    y1 = CausalBandpassFilter(fs, 5, 15, order=4).process(x)
    f2 = CausalBandpassFilter(fs, 5, 15, order=4)
    h = len(x) // 2
    y2 = np.concatenate([f2.process(x[:h]), f2.process(x[h:])])
    ya = CausalBandpassFilter(fs, 5, 15, order=4).process(x[:h])
    yb = CausalBandpassFilter(fs, 5, 15, order=4).process(x[h:])
    out["causal_filter"] = {"max_diff_chunked": float(np.max(np.abs(y1 - y2))),
                            "boundary_diff_stateless": float(np.max(np.abs(np.concatenate([ya, yb])[h:h + 5] - y1[h:h + 5])))}

    # Pan-Tompkins z dryfem (konfiguracja z test_dsp.py)
    d = make_demo_data("ecg_normal")
    xe, fse = d["x"].copy(), d["fs"]
    tt = np.arange(len(xe)) / fse
    xw = xe + 0.6 * np.sin(2 * np.pi * 0.3 * tt)
    out["pan_tompkins"] = {"detect_peaks_clean": len(eng.detect_peaks(xe, distance=int(0.3 * fse))),
                           "pt_clean": len(pan_tompkins_qrs(xe, fse)),
                           "detect_peaks_wander": len(eng.detect_peaks(xw, distance=int(0.3 * fse))),
                           "pt_wander": len(pan_tompkins_qrs(xw, fse))}

    # Welch
    from scipy.signal import welch
    eeg, resp = make_demo_data("eeg_normal"), make_demo_data("resp_normal")
    f256, p256 = welch(xe, fs=fse, nperseg=256)
    peaks = eng.detect_peaks(xe, distance=int(0.3 * fse))
    reg = eng.rhythm_regularity(peaks, t=tt)
    out["welch"] = {"eeg_dominant": power_spectrum(eeg["x"], eeg["fs"])["dominant_freq"],
                    "resp_dominant": power_spectrum(resp["x"], resp["fs"])["dominant_freq"],
                    "ecg_fs": fse, "ecg_n": len(xe), "res_256_hz": fse / 256,
                    "ecg_dominant_256": float(f256[1:][np.argmax(p256[1:])]),
                    "ecg_dominant_now": power_spectrum(xe, fse)["dominant_freq"],
                    "ecg_true_freq_rr": 1.0 / reg["mean_interval"], "bpm": 60.0 / reg["mean_interval"]}
    # v1.1 (aneks 1): dominujaca czestotliwosc EKG w zaleznosci od nperseg
    out["welch"]["ecg_dominant_by_nperseg"] = {str(k): float(power_spectrum(xe, fse, nperseg=k)["dominant_freq"])
                                               for k in (256, 512, 1024, 2048)}

    # bug 1 (konfiguracja z test_bio_core.py)
    rng = np.random.default_rng(1)
    x1 = np.zeros(500)
    x1[::20] = 1.0
    x1 += rng.normal(0, 0.02, 500)
    med, mad, sd = np.median(x1), np.median(np.abs(x1 - np.median(x1))), np.std(x1)
    out["bug1"] = {"buggy_threshold": float(med + 1.5 * mad), "fixed_threshold": float(med + 3.0 * sd),
                   "x6": float(x1[6]), "x6_above_buggy": bool(x1[6] > med + 1.5 * mad),
                   "x6_local_max": bool(x1[6] >= x1[max(0, 6 - 5):6 + 6].max()),
                   "peak_fraction": float(np.mean(x1 > 0.5)),
                   "detect_peaks_now": len(eng.detect_peaks(x1, distance=10))}
    # v1.1 (aneks 1): ile probek szumu (poza szczytami) jest lokalnym maksimum powyzej starego progu
    thr = med + 1.5 * mad
    noise_lm = [i for i in range(1, 499) if i % 20 and x1[i] > thr and x1[i] > x1[i - 1] and x1[i] >= x1[i + 1]]
    out["bug1"]["noise_local_max_above_old"] = len(noise_lm)

    # bug 2 (konfiguracja z test_bio_core.py: nieregularny sygnal, seed 0, max_lag 60)
    rng = np.random.default_rng(0)
    x2 = np.zeros(2000)
    i = 0
    while i < 2000:
        x2[i] = 1.0
        i += rng.integers(12, 35)
    x2 += rng.normal(0, 0.02, 2000)

    def candidate_rhythm(x, max_lag, power_thresh=0.4):
        x = np.asarray(x, float)
        n = len(x)
        xd = x - np.linspace(x[0], x[-1], n)
        xd = xd - xd.mean()
        ac = np.array([np.dot(xd, xd) / n] + [np.dot(xd[:-k], xd[k:]) / (n - k) for k in range(1, max_lag + 1)])
        ac /= ac[0]
        pw = ac[1:]
        dom = np.where(pw >= power_thresh)[0]
        return (np.arange(1, len(ac))[dom].tolist(), float(pw[dom].max())) if dom.size else ([], 0.0)
    cp, cpow = candidate_rhythm(x2, 60)
    own_p, own_pow = eng.rhythm(x2, max_lag=60)
    cand_obj = TIMDRBio()
    try:
        cp2, cpow2 = cand_obj.rhythm(x2, max_lag=60)
        cand_file = {"n_periods": len(cp2), "power": float(cpow2)}
    except Exception as e:  # sygnatura kandydata moze byc inna
        cand_file = {"error": f"{type(e).__name__}: {e}"}
    out["bug2"] = {"candidate_test_copy": {"n_periods": len(cp), "power": cpow}, "candidate_user_py": cand_file,
                   "own": {"n_periods": len(list(own_p)), "power": float(own_pow)}}

    # twist (konfiguracja z test_bio_core.py)
    rw, rwo = [], []
    for seed in range(10):
        r = np.random.default_rng(seed)
        tt2 = np.arange(2000, dtype=float)
        xx = 70 + r.normal(0, 1.5, 2000)
        rw.append(len(eng.twist(xx, t=tt2, factor=3.5)) / 2000)
        rwo.append(len(eng.twist(xx, factor=3.5)) / 2000)
    out["twist"] = {"pct_with_t": 100 * float(np.mean(rw)), "pct_without_t": 100 * float(np.mean(rwo))}

    # trend: README podaje liczby 0.000433..., szukamy konfiguracji w repo
    hits = [f for f in subprocess.run(["git", "-C", str(REPO), "grep", "-l", "0.000433"], capture_output=True,
                                      text=True).stdout.split() if not f.startswith("docs/audit/")]
    out["trend"] = {"files_with_number": hits}

    # envelope_drop / bezdech
    ap, rn = make_demo_data("resp_apnea"), make_demo_data("resp_normal")
    w = int(10 * ap["fs"])
    rngs = eng.envelope_drop(ap["x"], window=w)
    out["envelope"] = {"max_abs_madz": float(np.max(np.abs(_mad_z(ap["x"])))), "ranges_s":
                       [[a / ap["fs"], b / ap["fs"]] for a, b in rngs],
                       "normal_ranges": len(eng.envelope_drop(rn["x"], window=w))}

    # anomalies na surowym EKG
    out["raw_ecg_anomalies_pct"] = 100 * len(eng.anomalies(xe)) / len(xe)

    # KHIPU
    import khipu_bio_alert as K
    episodes = {"ecg": tuple(make_demo_data("ecg_arrhythmia")["irregular_window_s"]), "eeg": (13.5, 17.5),
                "pulse": (240.0, 360.0), "resp": (150.0, 170.0)}
    pairs = {"ecg": ("ecg_normal", "ecg_arrhythmia"), "eeg": ("eeg_normal", "eeg_seizure_like"),
             "resp": ("resp_normal", "resp_apnea"), "pulse": ("pulse_normal", "pulse_tachycardia")}
    table, feats = {}, {"ecg_cv": [], "generic_power": []}
    for typ, (nn, ab) in pairs.items():
        res = {}
        for tag, sc in (("normal", nn), ("abnormal", ab)):
            dd = make_demo_data(sc)
            r = K.regime_score_series(dd["x"], dd["t"], dd["fs"], typ)
            res[tag] = K.regime_alerts(r["scores"], r["window_end_idx"], dd["t"])
            win, stp = int(round(K.WINDOW_S_BY_TYPE[typ] * dd["fs"])), int(round(K.STEP_S_BY_TYPE[typ] * dd["fs"]))
            for s0 in range(0, len(dd["x"]) - win + 1, stp):
                v = K.make_embedding_window(dd["x"][s0:s0 + win], dd["t"][s0:s0 + win], dd["fs"], typ)
                feats["ecg_cv" if typ == "ecg" else "generic_power"].append(float(v[1] if typ == "ecg" else v[0]))
        e0, e1 = episodes[typ]
        hits = sum(1 for a in res["abnormal"] if a["t_s"] is not None and e0 - 5 <= a["t_s"] <= e1 + 5)
        table[typ] = {"window_s": K.WINDOW_S_BY_TYPE[typ], "step_s": K.STEP_S_BY_TYPE[typ],
                      "false_alarms": len(res["normal"]), "alerts": len(res["abnormal"]), "hits": hits,
                      "alert_times": [a["t_s"] for a in res["abnormal"]], "episode": [e0, e1]}
    out["khipu"] = {"enabled": K.KHIPU_BOTTLENECK_ENABLED, "validated": sorted(K.KHIPU_VALIDATED_TYPES),
                    "n_scenarios": len(SCENARIOS), "table": table,
                    "ecg_cv_range": [min(feats["ecg_cv"]), max(feats["ecg_cv"])],
                    "generic_power_range": [min(feats["generic_power"]), max(feats["generic_power"])]}
    (HERE / "RECOMPUTE_BIO.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False)[:7000])


if __name__ == "__main__":
    main()
