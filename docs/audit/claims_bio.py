"""Karty twierdzeń README (TIMDR-Bio-Signals) dla tools/claim_audit.py.
Reguły: docs/audit/CLAIM_AUDIT_PREREG.md + CLAIM_AUDIT_ADDENDUM_1.md. Przeliczenia: docs/audit/RECOMPUTE_BIO.json.

v1.1 (po przebiegu 1 i poprawce README): nowe cytaty F10 (rozbite na F10/F13/F14), B3, B4, B5, B9, W2, W3, K2, K6;
komunikat B4 liczony; W3 z ujawnieniem (UJAWNIONE).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from claim_audit import POTWIERDZONE, SPRZECZNE, NIEROZSTRZYGNIETE, Claim, Result  # noqa: E402

TITLE = "README → zastrzeżenie, testy, DSP, naprawione błędy, parametry, alert KHIPU (TIMDR-Bio-Signals)"
README = "README.md"
PREREG = "docs/audit/CLAIM_AUDIT_PREREG.md"
OUTPUT = "CLAIM_AUDIT.md"
SCOPES = [(r"^## ⚠️ Zastrzeżenie", r"^## Szybki start"), (r"^## Testy", r"^@@@KONIEC")]


def rc() -> dict:
    return json.loads((HERE / "RECOMPUTE_BIO.json").read_text(encoding="utf-8"))


def src(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def R(ok, value, note=""):
    return Result(POTWIERDZONE if ok else SPRZECZNE, value, note)


def near(stated, actual, rel=0.15):
    return abs(actual - stated) <= rel * abs(stated)


def c(x, n=3):
    return f"{x:.{n}f}".replace(".", ",")


def z_synthetic():
    s = rc()["synthetic"]
    return R(not s["data_files"] and s["rng_in_demo"], f"pliki danych w repo: {s['data_files'] or 'brak'}; demo z numpy.random",
             "R13")


def t_total():
    t = rc()["tests"]
    ok = t["total"] == 85 and t["returncode"] == 0 and "85 passed" in " ".join(t["tail"]) and len(t["per_file"]) == 7
    return R(ok, f"{t['total']} testów w {len(t['per_file'])} plikach; {t['tail']}", "KOD REPO")


def f_chunks():
    v = rc()["causal_filter"]["max_diff_chunked"]
    return R(v < 1e-9, f"maks. różnica {v:.1e}", "konfiguracja z test_dsp.py")


def f_stateless():
    v = rc()["causal_filter"]["boundary_diff_stateless"]
    return R(v > 0.01, f"skok na granicy {c(v)}", "konfiguracja z test_dsp.py")


def f_pt_algo():
    d = src("dsp.py")
    ok = "Pan & Tompkins, 1985" in d and "5-15 Hz" in d and "150ms" in d
    return R(ok, "docstring i kod pan_tompkins_qrs: 5-15 Hz, okno ~150 ms", "KOD; rok publikacji jako DOKUMENT")


def f_drift_cfg():
    t = src("test_dsp.py")
    return R("0.6 * np.sin(2 * np.pi * 0.3 * t)" in t, "dryf 0,3 Hz, amplituda 0,6", "konfiguracja z test_dsp.py")


def f_dp():
    p = rc()["pan_tompkins"]
    return R(p["detect_peaks_clean"] == 70 and p["detect_peaks_wander"] == 18,
             f"detect_peaks: {p['detect_peaks_clean']} → {p['detect_peaks_wander']}", "KOD REPO")


def f_pt():
    p = rc()["pan_tompkins"]
    return R(p["pt_clean"] == 70 and p["pt_wander"] == 70, f"pan_tompkins_qrs: {p['pt_clean']} → {p['pt_wander']}", "KOD REPO")


def f_welch_known():
    w = rc()["welch"]
    ok = round(w["eeg_dominant"], 1) == 10.0 and round(w["resp_dominant"], 3) == 0.253
    return R(ok, f"EEG {c(w['eeg_dominant'])} Hz, oddech {c(w['resp_dominant'])} Hz", "KOD REPO, demo eeg_normal/resp_normal")


def f_welch_res():
    w = rc()["welch"]
    ok = w["ecg_fs"] == 250 and w["ecg_n"] == 15000 and near(1.0, w["res_256_hz"])
    return R(ok, f"fs {w['ecg_fs']}, n {w['ecg_n']}, rozdzielczość {c(w['res_256_hz'])} Hz", "")


def f_welch_true():
    w = rc()["welch"]
    return R(near(1.17, w["ecg_true_freq_rr"]) and near(70, w["bpm"]),
             f"z odstępów RR: {c(w['ecg_true_freq_rr'])} Hz = {c(w['bpm'], 1)} bpm", "")


def f_welch_bug():
    w = rc()["welch"]
    ok = near(1.95, w["ecg_dominant_256"]) and "min(2048" in src("dsp.py")
    return R(ok, f"nperseg=256: {c(w['ecg_dominant_256'])} Hz; obecnie (cap 2048): {c(w['ecg_dominant_now'])} Hz",
             "NIEZALEŻNE (scipy.welch nperseg=256)")


def f_bands():
    a = src("api.py")
    ok = all(s in a for s in ('"ecg": (0.5, 40.0)', '"eeg": (1.0, 45.0)', '"resp": (0.05, 1.0)')) \
        and '"pulse": (' not in a.split("FILTER_BAND_BY_TYPE = {")[1].split("}")[0] and "fs: float = 0.5" in src("demo_scenarios.py")
    return R(ok, "FILTER_BAND_BY_TYPE: ecg 0,5–40, eeg 1–45, resp 0,05–1; brak pulse; demo puls fs 0,5", "KOD")


def f_stream():
    a = src("api.py")
    ok = '{"ecg": 20.0, "eeg": 20.0, "resp": 30.0, "pulse": 60.0}' in a and "int(round(fs * 2.0))" in a \
        and "duration_s: int = 600" in src("demo_scenarios.py")
    return R(ok, "prędkość 20–60×, przeliczenie co 2 s, demo pulsu 600 s = 10 min", "KOD")


def b_head1():
    d = src("bio_core.py")
    ok = "threshold = med + prominence_factor * np.std(x)" in d and "prominence_factor: float = 3.0" in d
    return R(ok, "detect_peaks: próg mediana + 3·std(x)", "KOD")


def b_95():
    f = rc()["bug1"]["peak_fraction"]
    return R(near(95, 100 * (1 - f)), f"szum = {100 * (1 - f):.0f}% próbek".replace(".", ","), "konfiguracja z testu bug 1")


def b_mad():
    v = rc()["bug1"]["buggy_threshold"]
    return R(near(0.024, v), f"mediana + 1,5·MAD = {c(v, 4)}", "konfiguracja z testu bug 1 (seed 1, n 500)")


def b_x6():
    b = rc()["bug1"]
    ok = round(b["x6"], 4) == 0.0349 and b["x6_above_buggy"] and b["x6_local_max"]
    return R(ok, f"x[6] = {c(b['x6'], 4)}, powyżej starego progu, lokalne maksimum", "")


def b_std():
    v = rc()["bug1"]["fixed_threshold"]
    return R(near(0.33, v), f"mediana + 3·std = {c(v)}", "")


def b_edges():
    return R(rc()["bug1"]["detect_peaks_now"] == 25, f"obecnie wykryte {rc()['bug1']['detect_peaks_now']}/25 (w tym indeks 0)",
             "stan po naprawie; stanu sprzed naprawy nie da się uruchomić z repo")


def b_head2():
    s = src("candidate_user.py")
    return R("np.where(power >= power_thresh)" in s, "kandydat: wszystkie lagi ≥ progu, bez filtra lokalnych maksimów", "KOD")


def b_linspace():
    return R("np.linspace(x[0], x[-1], n)" in src("candidate_user.py"), "candidate_user.py: detrend linspace", "KOD")


def b_cand():
    b = rc()["bug2"]
    t, f = b["candidate_test_copy"], b["candidate_user_py"]
    ok = round(t["power"], 3) == 0.656 and t["n_periods"] == 60
    return R(ok, f"kopia z testu: power {c(t['power'])}, {t['n_periods']} okresów; candidate_user.py: {f}",
             "konfiguracja z testu bug 2 (seed 0, max_lag 60)")


def b_own():
    o = rc()["bug2"]["own"]
    return R(o["power"] == 0.0 and o["n_periods"] == 0, f"power {o['power']}, okresów {o['n_periods']}", "KOD REPO")


def w_code():
    cu, bc = src("candidate_user.py"), src("bio_core.py")
    ok = cu.count("np.gradient(") >= 2 and "np.diff(x, n=2)" in bc and "np.gradient(" in bc
    return R(ok, "kandydat: 2× np.gradient; bio_core: np.gradient z t, np.diff(n=2) bez t", "KOD")


def w_rates():
    w = rc()["twist"]
    ok = all(0.045 <= w[k] <= 0.065 for k in ("pct_with_t", "pct_without_t"))
    return R(ok, f"z t {c(w['pct_with_t'])}%, bez t {c(w['pct_without_t'])}% (10 ziaren)", "konfiguracja z testu twist")


def w_trend():
    f = rc()["trend"]["files_with_number"]
    if f == ["README.md"] or not f:
        return Result(NIEROZSTRZYGNIETE, "liczby występują tylko w README", "R9: brak konfiguracji w repo")
    return R(True, f"liczby w: {f}", "")


def e_z():
    e = rc()["envelope"]
    ok = round(e["max_abs_madz"], 2) == 1.21 and "factor: float = 3.5" in src("bio_core.py")
    return R(ok, f"maks. |z| = {c(e['max_abs_madz'], 2)}; domyślny próg anomalies 3,5", "KOD REPO, demo resp_apnea")


def e_window():
    e = rc()["envelope"]
    r = e["ranges_s"][0] if e["ranges_s"] else [None, None]
    ok = bool(e["ranges_s"]) and round(r[0], 1) == 141.6 and round(r[1], 1) == 178.0 and e["normal_ranges"] == 0 \
        and "apnea_start_s, apnea_dur_s = duration_s * 0.5, 20" in src("demo_scenarios.py")
    return R(ok, f"wykryte {e['ranges_s']} s; na resp_normal: {e['normal_ranges']}", "KOD REPO; epizod 150–170 s z kodu")


def f_welch_before():
    w = rc()["welch"]
    return R(near(1.95, w["ecg_dominant_256"]) and near(1.17, w["ecg_true_freq_rr"]),
             f"nperseg=256: {c(w['ecg_dominant_256'])} Hz; prawdziwa {c(w['ecg_true_freq_rr'])} Hz", "NIEZALEŻNE + KOD REPO")


def f_welch_sweep():
    b = rc()["welch"]["ecg_dominant_by_nperseg"]
    ok = "min(2048" in src("dsp.py") and near(2.32, b["2048"], 0.02) and near(1.22, b["1024"], 0.02) and near(2.44, b["512"], 0.02)
    return R(ok, "; ".join(f"{k}: {c(v)} Hz" for k, v in b.items()), "KOD REPO")


def f_welch_test():
    return R('assert spec["dominant_freq"] < 5 * true_freq' in src("test_dsp.py"), "test: dominant_freq < 5 × prawdziwa", "KOD")


def b_mad_v11():
    v = rc()["bug1"]["buggy_threshold"]
    return R(near(0.020, v), f"mediana + 1,5·MAD = {c(v, 4)}", "konfiguracja z testu bug 1")


def b_noise_v11():
    n = rc()["bug1"]["noise_local_max_above_old"]
    return R(n == 42, f"{n} lokalnych maksimów szumu powyżej starego progu", "")


def b_std_v11():
    v = rc()["bug1"]["fixed_threshold"]
    return R(near(0.66, v), f"mediana + 3·std = {c(v)}", "")


def b_cand_v11():
    t = rc()["bug2"]["candidate_test_copy"]
    return R(round(t["power"], 3) == 0.684 and t["n_periods"] == 60, f"power {c(t['power'])}, {t['n_periods']} okresów",
             "konfiguracja z testu bug 2")


def w_rates_v11():
    w = rc()["twist"]
    return R(round(w["pct_with_t"], 2) == 0.07 and round(w["pct_without_t"], 2) == 0.02,
             f"z t {c(w['pct_with_t'])}%, bez t {c(w['pct_without_t'])}%", "konfiguracja z testu twist")


def w_trend_v11():
    f = rc()["trend"]["files_with_number"]
    return Result("UJAWNIONE" if f == ["README.md"] else SPRZECZNE, f"liczby tylko w: {f}",
                  "R9: brak konfiguracji w repo - README to teraz mówi")


def k_ranges_v11():
    k = rc()["khipu"]
    cv, pw = k["ecg_cv_range"], k["generic_power_range"]
    ok = 0.003 / 3 <= cv[0] and cv[1] <= 0.5 * 3 and -1 <= pw[0] and pw[1] <= 1
    return R(ok, f"cv EKG {c(cv[0])}–{c(cv[1])}; moc rytmu {c(pw[0])}–{c(pw[1])}", "R11")


def k_off_v11():
    ok = "def test_switch_is_boolean_and_actually_gates_api_result" in src("test_khipu_bio_alert.py") \
        and rc()["tests"]["returncode"] == 0 and "if KHIPU_BOTTLENECK_ENABLED" in src("api.py")
    return R(ok, "api.py liczy KHIPU tylko przy włączonej fladze; test przełącznika przechodzi", "KOD")


def a_raw():
    v = rc()["raw_ecg_anomalies_pct"]
    return R(7 * 0.85 <= v <= 8 * 1.15, f"{c(v, 1)}% próbek ecg_normal", "KOD REPO")


def p_table():
    a, k = src("api.py"), src("khipu_bio_alert.py")
    ok = '{"eeg": 40, "resp": 60, "pulse": 90}' in a and '{"resp": 10, "pulse": 60}' in a and '{"eeg": 40, "resp": 60, "pulse": 90}' in k
    return R(ok, "MAX_LAG eeg 40, resp 60, pulse 90; okno envelope resp 10 s, pulse 60 s", "KOD (api.py i khipu_bio_alert.py)")


def k_on():
    return R(rc()["khipu"]["enabled"] is True, f"KHIPU_BOTTLENECK_ENABLED = {rc()['khipu']['enabled']}", "R12")


def k_ranges():
    k = rc()["khipu"]
    cv, pw = k["ecg_cv_range"], k["generic_power_range"]
    ok = 0.01 / 3 <= cv[0] and cv[1] <= 0.3 * 3 and -1 <= pw[0] and pw[1] <= 1
    return R(ok, f"cv EKG {c(cv[0])}–{c(cv[1])}; moc rytmu {c(pw[0])}–{c(pw[1])}", "R11, wszystkie okna KHIPU 8 scenariuszy")


def k_eight():
    return R(rc()["khipu"]["n_scenarios"] == 8, f"{rc()['khipu']['n_scenarios']} scenariuszy", "")


def k_table():
    tb = rc()["khipu"]["table"]
    want = {"ecg": (10.0, 2.5, 0, 2, 2), "eeg": (5.0, 2.5, 2, 3, 2), "resp": (30.0, 7.5, 1, 4, 1), "pulse": (120.0, 15.0, 3, 1, 1)}
    got = {k: (v["window_s"], v["step_s"], v["false_alarms"], v["alerts"], v["hits"]) for k, v in tb.items()}
    bad = {k: got[k] for k in want if got[k] != want[k]}
    return R(not bad, "; ".join(f"{k}: fałszywe {got[k][2]}, alerty {got[k][3]}, trafione {got[k][4]}" for k in want),
             "R10" + (f"; różne: {bad}" if bad else ""))


def k_validated():
    return R(rc()["khipu"]["validated"] == ["ecg", "eeg"], f"{rc()['khipu']['validated']}", "KOD")


def k_default():
    on = rc()["khipu"]["enabled"]
    return R(on is False, f"w kodzie KHIPU_BOTTLENECK_ENABLED = {on}",
             "R12: nagłówek sekcji mówi „obecnie: WŁĄCZONY”, a to zdanie - że domyślnie False")


def k_tests():
    p = rc()["tests"]["per_file"]
    return R(p.get("test_khipu_bio_alert.py") == 18 and p.get("test_api_khipu.py") == 4,
             f"{p.get('test_khipu_bio_alert.py')} + {p.get('test_api_khipu.py')}", "")


def k_stream():
    a = src("api.py")
    ok = "include_khipu=False" in a and "def test_khipu_excluded_when_include_khipu_false_even_if_globally_enabled" \
        in src("test_api_khipu.py") and rc()["tests"]["returncode"] == 0
    return R(ok, "/api/stream: include_khipu=False; test obecny i przechodzi", "KOD")


CLAIMS = [
    Claim("Z1", "Wszystkie dane demonstracyjne w tym repo są **w całości syntetyczne** (generowane matematycznie, "
                "`demo_scenarios.py`) — żadne prawdziwe dane pacjenta nie zostały użyte", z_synthetic),
    Claim("T1", "85/85 testów przechodzi (`test_bio_core.py` + `test_demo_scenarios.py` + `test_dsp.py` + "
                "`test_khipu_bio_alert.py` + `test_api_khipu.py`", t_total),
    Claim("F1", "przetwarzanie tego samego sygnału w jednym wywołaniu vs. w dwóch porcjach daje IDENTYCZNY wynik (różnica < 1e-9)", f_chunks),
    Claim("F2", "na granicy porcji powstaje widoczny skok (>0.01 różnicy amplitudy)", f_stateless),
    Claim("F3", "Klasyczny algorytm (Pan & Tompkins, 1985): filtr 5-15Hz → pochodna → kwadrat → całkowanie w oknie ~150ms", f_pt_algo),
    Claim("F4", "wolnego dryfu linii bazowej (0.3Hz, amplituda porównywalna z QRS", f_drift_cfg),
    Claim("F5", "traci większość uderzeń: **70 → 18 wykrytych**", f_dp),
    Claim("F6", "pozostaje w pełni stabilny: **70 → 70 wykrytych** (pasmo 5-15Hz usuwa dryf PRZED wykrywaniem szczytów)", f_pt),
    Claim("F7", "EEG (10Hz alfa) → wykryte 10.0Hz; oddech (~15/min=0.25Hz) → wykryte 0.253Hz", f_welch_known),
    Claim("F8", "(stały cap 256 próbek) - dla EKG (fs=250Hz, n=15000) dawało to rozdzielczość ~1Hz", f_welch_res),
    Claim("F9", "(~1.17Hz przy 70bpm)", f_welch_true),
    Claim("F10", "Skutek: `dominant_freq` wychodziło ~1.95Hz zamiast ~1.17Hz", f_welch_before),
    Claim("F13", "Górny cap okna podniesiono do 2048 próbek, ale to NIE naprawia wyniku dla demo EKG: przy nperseg=2048 "
                 "wychodzi ~2.32Hz (2. harmoniczna), przy 1024 ~1.22Hz, przy 512 ~2.44Hz", f_welch_sweep),
    Claim("F14", "Test sprawdza tylko, że wynik jest mniejszy niż 5× prawdziwa częstotliwość", f_welch_test),
    Claim("F11", "(EKG 0.5-40Hz, EEG 1-45Hz, oddech 0.05-1Hz; puls pomijany - zbyt niska częstotliwość próbkowania, fs=0.5Hz", f_bands),
    Claim("F12", "(np. 20-60x, dobranym pod typ sygnału - inaczej demo pulsu trwałoby 10 minut) i co ~2 sekundy nowych danych", f_stream),
    Claim("B1", "### Bug 1 — `detect_peaks`: próg z MAD zawodzi przy rzadkich szczytach", b_head1),
    Claim("B2", "bo MAD jest zdominowany przez te ~95% próbek, które są szumem", b_95),
    Claim("B3", "(amplituda szczytu 1.0, szum std=0.02) oryginalny próg `mediana + 1.5·MAD` wychodzi ≈ 0.020", b_mad_v11),
    Claim("B4", "w tym sygnale 42 próbki szumu (lokalne maksima poza prawdziwymi szczytami) przekraczają stary próg", b_noise_v11),
    Claim("B5", "próg zmieniony na `mediana + 3.0·std(x)` (≈0.66 w tym samym przykładzie", b_std_v11),
    Claim("B6", "(indeksy `0` i `n-1` mogły wcześniej nigdy nie zostać wykryte jako szczyt)", b_edges),
    Claim("B7", "### Bug 2 — odrzucony kandydat: `rhythm()` bez filtra lokalnych maksimów", b_head2),
    Claim("B8", "detrend przez prostą linię `linspace(x[0], x[-1], n)`", b_linspace),
    Claim("B9", "kandydat mimo to zgłaszał `power=0.684` (powyżej własnego progu 0.4) i aż 60 \"wykrytych okresów\"", b_cand_v11),
    Claim("B10", "daje poprawnie `power=0.0, periods=[]`", b_own),
    Claim("W1", "liczy drugą pochodną przez dwukrotne `np.gradient(x, t)`, co poprawnie obsługuje sygnały o nierównomiernym "
                "próbkowaniu w czasie (w przeciwieństwie do `np.diff(x, n=2)`", w_code),
    Claim("W2", "(0.07% z `t` i 0.02% bez `t`, 10 powtórzeń", w_rates_v11),
    Claim("W3", "wyniki zgodne co do ~10 miejsc po przecinku (`0.00043334633260878435` vs `0.00043334633260879205`; "
                "jednorazowe sprawdzenie - konfiguracji tego porównania nie zapisano w repo)", w_trend_v11),
    Claim("E1", "maksymalne |z| całego sygnału wynosiło tylko 1.21, dużo poniżej progu 3.5", e_z),
    Claim("E2", "poprawnie wykryła okno 141.6s–178.0s, pokrywające się z wstrzykniętym epizodem bezdechu (150s–170s), bez "
                "fałszywych alarmów na normalnym oddechu", e_window),
    Claim("A1", "daje ~7-8% \"fałszywych\" anomalii", a_raw),
    Claim("P1", "| EEG | 40 próbek | — | | oddech | 60 próbek | 10 s | | puls | 90 próbek | 60 s |", p_table),
    Claim("K1", "wyłącznik `KHIPU_BOTTLENECK_ENABLED` (obecnie: WŁĄCZONY)", k_on),
    Claim("K2", "(bpm rzędu dziesiątek, cv rzędu 0.003-0.5, moc rytmu w [-1,1]...)", k_ranges_v11),
    Claim("K3", "Sprawdzone empirycznie na wszystkich 8 syntetycznych scenariuszach demo", k_eight),
    Claim("K4", "| EKG | 10s / 2.5s | 0 | 2 | 2/2 | | EEG | 5s / 2.5s | 2 | 3 | 2/3 | | oddech | 30s / 7.5s | 1 | 4 | 1/4 | "
                "| puls | 120s / 15s | 3 | 1 | 1/1 |", k_table),
    Claim("K5", "`KHIPU_VALIDATED_TYPES = {\"ecg\", \"eeg\"}`", k_validated),
    Claim("K6", "Po wyłączeniu (`False`) wynik jest identyczny jak przed dodaniem tego modułu", k_off_v11),
    Claim("K7", "Testy: 18 w `test_khipu_bio_alert.py` (moduł: kształt/determinizm/próg/ wyłącznik) + 4 w `test_api_khipu.py`", k_tests),
    Claim("K8", "`/api/stream` woła go zawsze z `include_khipu=False`", k_stream),
]
FORBIDDEN = [(r"diagnozuj\w*|rozpoznani\w*\s+klin\w*", r"\bnie\b", "narzędzie badawcze, nie wyrób medyczny")]
ABSOLUTE = [(r"\btak samo\b", "podaj różnicę"), (r"\bzawsze\b|\bnigdy\b", "słowo bezwzględne"),
            (r"\bdowodzi\b|\budowodni\w*", "„dowodzi” wymaga dowodu"), (r"(?<!\d)100 ?%", "sprawdź liczność")]
