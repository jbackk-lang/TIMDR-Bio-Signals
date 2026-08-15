"""
demo.py — uruchamia bio_core.py na wszystkich 8 scenariuszy demo i drukuje
wyniki. Sygnały ECG/EEG/oddech używają rhythm() (autokorelacja) z
max_lag dobranym pod naturalny zakres okresów danego typu sygnału;
puls (już jest ciągiem "tętno w bpm", nie surowym EKG) i oddech
dodatkowo sprawdzane pod kątem envelope_drop() (bezdech).

NIE jest to narzędzie diagnostyczne - patrz README.md.
"""

from bio_core import TIMDRBioSignal
from demo_scenarios import SCENARIOS, make_demo_data

# max_lag (w próbkach) dobrany pod oczekiwany zakres okresu dla danego typu
# sygnału - zbyt duży max_lag dla szybkich oscylacji (np. EEG) rozmywa
# wynik fałszywymi, dłuższymi "okresami" ze zwykłego dryfu/szumu.
MAX_LAG_BY_TYPE = {
    "eeg": 40,     # obejmuje okresy odpowiadające ~3-60Hz przy fs=128
    "resp": 60,    # obejmuje kilka cykli oddechowych przy fs=5Hz
    "pulse": 90,   # obejmuje ~kilka cykli modulacji oddechowej przy fs=0.5Hz
}

ENVELOPE_WINDOW_S_BY_TYPE = {
    "resp": 10,
    "pulse": 60,
}


def run_scenario(name: str):
    eng = TIMDRBioSignal()
    d = make_demo_data(name)
    t, x, fs, sig_type = d["t"], d["x"], d["fs"], d["signal_type"]

    print(f"\n=== {name} — {d['label']} ===")
    print(f"n={len(x)}  fs={fs}  czas trwania={t[-1]:.1f}s")

    if sig_type == "ecg":
        distance = int(0.3 * fs)  # min. odstęp między załamkami R: 0.3s (~200 bpm max)
        peaks = eng.detect_peaks(x, distance=distance)
        reg = eng.rhythm_regularity(peaks, t=t)
        print(f"wykryte załamki R: {len(peaks)}")
        if reg["mean_interval"] is not None:
            bpm = 60.0 / reg["mean_interval"]
            print(f"średni RR: {reg['mean_interval']:.3f}s (~{bpm:.0f} bpm)  cv (zmienność RR): {reg['cv']:.4f}")
            flag = "PODEJRZENIE NIEMIAROWOŚCI" if reg["cv"] > 0.08 else "rytm regularny"
            print(f"ocena regularności: {flag} (próg demonstracyjny cv>0.08)")

        # WAŻNE: anomalies() na SUROWYM przebiegu EKG nie ma sensu - każdy
        # załamek R jest ostrym, dużym odchyleniem od płaskiej linii
        # bazowej, więc MAD-z na surowym sygnale oznaczyłby PRAWIE KAŻDY
        # normalny QRS jako "anomalię" (zweryfikowano: ~7-8% próbek na w
        # pełni zdrowym, regularnym demo EKG - bezużyteczne). Zamiast tego
        # liczymy anomalie na AMPLITUDACH POSZCZEGÓLNYCH ZAŁAMKÓW R - czy
        # KTÓRE UDERZENIE SERCA ma nietypową amplitudę względem pozostałych
        # (klinicznie bliższe realnemu pytaniu: "czy to jedno pobudzenie
        # wygląda inaczej niż reszta", np. dodatkowe pobudzenie komorowe).
        if len(peaks) >= 4:
            peak_amplitudes = x[peaks]
            beat_anomalies = eng.anomalies(peak_amplitudes, factor=3.5)
            print(f"uderzenia o nietypowej amplitudzie: {len(beat_anomalies)} / {len(peaks)}")
        else:
            print("za mało wykrytych uderzeń do oceny amplitud")

    else:
        max_lag = MAX_LAG_BY_TYPE.get(sig_type, 60)
        periods, power = eng.rhythm(x, max_lag=max_lag)
        anomalies = eng.anomalies(x, factor=3.5)
        twist_idx = eng.twist(x, t=t, factor=3.5)
        print(f"rhythm: moc={power:.3f}  okresy(próbki)={periods[:3]}")
        print(f"anomalies: {len(anomalies)}  twist: {len(twist_idx)}")

        if sig_type in ENVELOPE_WINDOW_S_BY_TYPE:
            window = int(ENVELOPE_WINDOW_S_BY_TYPE[sig_type] * fs)
            ranges = eng.envelope_drop(x, window=window, factor=3.0)
            if ranges:
                ranges_s = [(a / fs, b / fs) for a, b in ranges]
                print(f"envelope_drop (spadek zmienności - np. bezdech): {ranges_s}")
            else:
                print("envelope_drop: brak wykrytych spadków zmienności")

    for key in ("irregular_window_s", "burst_window_s", "event_window_s", "apnea_window_s"):
        if key in d:
            print(f"(prawdziwy wstrzyknięty epizod w danych demo: {key}={d[key]})")


def main():
    for name in SCENARIOS:
        run_scenario(name)


if __name__ == "__main__":
    main()
