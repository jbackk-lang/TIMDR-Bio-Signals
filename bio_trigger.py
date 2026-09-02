# bio_trigger.py
# ============================================
# TIMDR Bio Trigger Module
# ============================================
#
# ROLA: czujnik sygnałowy — NIE model, NIE rozpoznanie kliniczne (patrz
# zastrzeżenie na górze bio_core.py: to narzędzie badawczo-edukacyjne, nie
# wyrób medyczny). Ten plik nie liczy własnej statystyki: dispatcher nad
# już przetestowanym wynikiem `analyze_signal()` z api.py (rhythm/
# anomalies/twist/envelope_drop/rhythm_regularity z bio_core.py) — jedyna
# jego robota: powiedzieć, KTÓRY typ zdarzenia się odpalił i GDZIE.
#
# ZASTANY STAN (powód budowy tego pliku): api.py::analyze_signal() już
# liczy WSZYSTKIE te detektory i wystawia je w /api/analyze, /api/demo i
# dashboardzie — ale jako osobne, równoległe listy/pola
# (anomalies_idx, twist_idx, envelope_drop_ranges, beat_amplitude_
# anomalies, arrhythmia_suspected...), bez jednego, priorytetyzowanego
# „co jest najważniejsze i gdzie". Ten dispatcher NIE zastępuje żadnego
# z tych pól (dashboard może dalej pokazywać wszystkie), tylko dodaje
# jedno zwięzłe podsumowanie na wierzchu.
#
# Priorytet (uzasadnienie kliniczne, patrz bio_core.py docstringi):
#   ENVELOPE_DROP (utrata zmienności — bezdech/asystolia/cisza EEG — to,
#     czego zwykłe anomalie/twist NIE widzą, patrz envelope_drop() —
#     najbardziej doniosłe pojedyncze zdarzenie) >
#   ARRHYTHMIA (nieregularność odstępów RR, tylko EKG — ugruntowany
#     kliniczny wskaźnik) >
#   BEAT_ANOMALY (nietypowa amplituda pojedynczego uderzenia, tylko EKG) >
#   TWIST (nagła zmiana tempa/kierunku) >
#   ANOMALY (pojedyncza statystyczna anomalia na surowym przebiegu —
#     najsłabszy/najbardziej szumiący sygnał z tego zestawu, patrz
#     ograniczenie anomalies() opisane w bio_core.py) >
#   NONE.

from enum import Enum


class BioTriggerType(Enum):
    ENVELOPE_DROP = "envelope_drop"
    ARRHYTHMIA = "arrhythmia"
    BEAT_ANOMALY = "beat_anomaly"
    TWIST = "twist"
    ANOMALY = "anomaly"
    NONE = "none"


class BioTriggerResult:
    def __init__(self, triggered=False, trigger_type=BioTriggerType.NONE,
                 location=None, message=""):
        self.triggered = triggered
        self.trigger_type = trigger_type
        self.location = location
        self.message = message

    def as_dict(self):
        return {
            "triggered": self.triggered,
            "type": self.trigger_type.value,
            "location": self.location,
            "message": self.message,
        }


class BioTrigger:
    """
    Dispatcher nad wynikiem `analyze_signal()` (api.py) — działa na
    SŁOWNIKU wyniku (nie na surowym sygnale), więc pasuje do obu ścieżek
    (ecg i generic/eeg/resp/pulse), które wypełniają różne podzbiory
    kluczy. Brakujący klucz jest traktowany jak "brak zdarzenia tego
    typu", nie błąd — dispatcher jest tolerancyjny na kształt wejścia z
    dowolnej z dwóch ścieżek api.py.

    arrhythmia_cv_thresh musi zgadzać się z progiem użytym do policzenia
    `arrhythmia_suspected` w api.py (domyślnie 0.08 tam) - jeśli wynik
    już zawiera `arrhythmia_suspected` (bool), dispatcher używa go
    WPROST i NIE przelicza własnego progu z `rr_cv` (unika rozjazdu
    dwóch niezależnych implementacji tego samego progu - patrz §6
    duplication-drift w skill timdr-signal-framework).
    """

    def __init__(self):
        self.last_result = BioTriggerResult()

    def analyze(self, result: dict) -> BioTriggerResult:
        envelope_ranges = result.get("envelope_drop_ranges") or []
        if envelope_ranges:
            r0 = envelope_ranges[0]
            return self._set_result(
                True, BioTriggerType.ENVELOPE_DROP, r0["start_idx"],
                f"Utrata zmienności sygnału (obwiedni) między próbkami "
                f"{r0['start_idx']}-{r0['end_idx']}."
            )

        if result.get("arrhythmia_suspected"):
            peaks = result.get("peaks") or []
            loc = int(peaks[-1]) if peaks else None
            return self._set_result(
                True, BioTriggerType.ARRHYTHMIA, loc,
                f"Podejrzenie arytmii (zmienność odstępów RR, cv={result.get('rr_cv')})."
            )

        beat_anomalies = result.get("beat_amplitude_anomalies") or []
        if beat_anomalies:
            loc = int(min(beat_anomalies))
            return self._set_result(
                True, BioTriggerType.BEAT_ANOMALY, loc,
                "Nietypowa amplituda uderzenia (załamka R)."
            )

        twist_idx = result.get("twist_idx") or []
        if twist_idx:
            loc = int(min(twist_idx))
            return self._set_result(
                True, BioTriggerType.TWIST, loc,
                "Nagła zmiana tempa/kierunku przebiegu."
            )

        anomalies_idx = result.get("anomalies_idx") or []
        if anomalies_idx:
            loc = int(min(anomalies_idx))
            return self._set_result(
                True, BioTriggerType.ANOMALY, loc,
                "Pojedyncza statystyczna anomalia w przebiegu."
            )

        return self._set_result(
            False, BioTriggerType.NONE, None,
            "Brak wykrytego zdarzenia sygnałowego."
        )

    def _set_result(self, triggered, trigger_type, location, message):
        self.last_result = BioTriggerResult(triggered, trigger_type, location, message)
        return self.last_result

    def get_last(self):
        return self.last_result
