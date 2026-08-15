"""
bio_core.py — TIMDR dla sygnałów fizjologicznych (EKG, EEG, puls, oddech)
==========================================================================

WAŻNE ZASTRZEŻENIE (przeczytaj przed użyciem):
Ten moduł jest narzędziem edukacyjno-badawczym do przetwarzania sygnałów
czasowych. NIE JEST wyrobem medycznym, nie ma certyfikacji CE/FDA i NIE
SŁUŻY do diagnostyki, monitorowania pacjentów ani podejmowania decyzji
klinicznych. Wyniki (np. "arytmia", "anomalia") to statystyczne
odchylenia względem lokalnej historii sygnału, NIE rozpoznania medyczne.
Realne EKG/EEG wymagają certyfikowanego sprzętu i interpretacji przez
wykwalifikowany personel medyczny. Dane demo w tym repo są W CAŁOŚCI
syntetyczne (wygenerowane matematycznie) - nigdy nie pochodzą od
prawdziwego pacjenta.

Architektura — ta sama rodzina algorytmów co w innych modułach TIMDR w
tym repo (trzęsienia ziemi, bateria przemysłowa), zastosowana do sygnałów
fizjologicznych:

  rhythm(x, ...)      — wykrywa okresowość / regularność rytmu (do
                         wykrywania arytmii: nieregularne EKG traci
                         wyraźny szczyt okresowości, które ma zdrowy rytm
                         zatokowy)
  anomalies(x, ...)   — pojedyncze impulsy odstające (MAD-z threshold) -
                         np. pojedyncze dodatkowe pobudzenie (PVC),
                         iglica padaczkowa w EEG
  twist(x, ...)       — nagłe zmiany kierunku/tempa sygnału (druga
                         pochodna) - np. nagły skok tętna, początek
                         epizodu bezdechu
  trend(t, x, window) — powolny dryf w OSTATNIM oknie czasowym (nie w
                         całej historii) - np. stopniowo rosnące tętno

Każda funkcja pracuje NA POJEDYNCZYM kanale (nie na fuzji wielokanałowej)
- to świadoma decyzja projektowa, nie uproszczenie: EKG (~1 Hz), oddech
(~0.2-0.3 Hz) i EEG (pasma kilka-kilkadziesiąt Hz) mają zupełnie różne
naturalne częstotliwości, więc łączenie ich w jeden sygnał przed analizą
rytmu nie ma sensu fizjologicznego i - jak udokumentowano w innych
modułach tego repo (TIMDR-Battery-Predict, TIMDR-Earthquake-Core) -
fuzja L2-norm wielu zsynchronizowanych kanałów przed analizą rytmu może
tworzyć fałszywą periodyczność o podwojonej częstotliwości (efekt
rektyfikacji). fuse() istnieje tylko dla ogólnego wskaźnika "coś jest
nie tak" (anomalie połączone), NIE dla rytmu.
"""

from __future__ import annotations

import numpy as np


def _mad_z(x: np.ndarray) -> np.ndarray:
    """Robust z-score oparty o medianę i MAD (Median Absolute Deviation).
    Fallback do rozstępu/4, gdy MAD=0 (płaski sygnał) - ten sam wzorzec
    co w pozostałych modułach TIMDR tego repo."""
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    if mad == 0:
        span = np.max(x) - np.min(x)
        if span == 0:
            return np.zeros_like(x)
        return (x - med) / (span / 4)
    return 0.6745 * (x - med) / mad


class TIMDRBioSignal:
    """Analiza pojedynczego kanału fizjologicznego (EKG, EEG, puls albo
    oddech - ten sam silnik, różne parametry wywołania)."""

    def anomalies(self, x, factor: float = 3.5) -> np.ndarray:
        """Indeksy próbek odstających (|MAD-z| > factor). Domyślny próg
        3.5 (nie 3.0 jak w innych modułach) - sygnały fizjologiczne mają
        naturalnie wyższą zmienność próbka-do-próbki (np. QRS w EKG) niż
        np. dane sejsmiczne, więc niższy próg dawałby zbyt wiele
        fałszywych trafień na samych, normalnych zespołach QRS.

        OGRANICZENIE (znalezione empirycznie przy budowie demo): dla
        sygnałów z RZADKIMI, ale DUŻYMI i REGULARNYMI szczytami na tle
        płaskiej linii bazowej (typowo: surowy przebieg EKG, gdzie
        wąskie zespoły QRS to tylko kilka % próbek) - mediana i MAD są
        zdominowane przez linię bazową, więc każdy pojedynczy, zupełnie
        normalny QRS wygląda statystycznie jak "odstająca" próbka.
        Zweryfikowano: na w pełni regularnym, zdrowym demo EKG
        anomalies() flagował ~7-8% wszystkich próbek - bezużyteczne jako
        wskaźnik "coś jest nie tak". Dla takich sygnałów NIE wołaj
        anomalies() na surowym przebiegu - zamiast tego wykryj uderzenia
        (detect_peaks()) i wywołaj anomalies() na WYEKSTRAHOWANYCH
        AMPLITUDACH poszczególnych uderzeń (x[peaks]) - patrz demo.py.
        Dla sygnałów bez tej struktury (puls jako szereg bpm, oddech,
        tło EEG) anomalies() na surowym przebiegu działa poprawnie."""
        x = np.asarray(x, dtype=float)
        if len(x) == 0:
            return np.array([], dtype=int)
        z = _mad_z(x)
        return np.where(np.abs(z) > factor)[0]

    def twist(self, x, t=None, factor: float = 3.5) -> np.ndarray:
        """Nagłe zmiany kierunku/tempa - druga pochodna (przyspieszenie
        sygnału) powyżej progu MAD-z. Wykrywa np. gwałtowny skok tętna
        albo nagłe załamanie amplitudy oddechu (początek bezdechu).

        Jeśli podano `t` (rzeczywiste znaczniki czasu próbek), druga
        pochodna liczona jest przez np.gradient(x, t) dwukrotnie - poprawnie
        obsługuje NIERÓWNOMIERNE próbkowanie (typowe dla realnych zapisów
        Holtera/EEG, gdzie odstępy między próbkami nie muszą być stałe).
        Bez `t` (domyślnie) liczona jest przez np.diff(x, n=2), co zakłada
        równomierne próbkowanie - szybsze, ale mniej ogólne. Zweryfikowano
        empirycznie: obie metody mają porównywalny, niski odsetek fałszywych
        alarmów na czystym szumie (~0.05-0.06% przy domyślnym progu 3.5)."""
        x = np.asarray(x, dtype=float)
        n = len(x)
        if n < 3:
            return np.array([], dtype=int)

        if t is not None:
            t = np.asarray(t, dtype=float)
            dx = np.gradient(x, t)
            d2 = np.gradient(dx, t)
            z = _mad_z(d2)
            return np.where(np.abs(z) > factor)[0]

        d2 = np.diff(x, n=2)
        z = _mad_z(d2)
        idx = np.where(np.abs(z) > factor)[0]
        return idx + 1  # przesunięcie o 1, bo diff(n=2) skraca tablicę z obu końców

    def trend(self, t, x, window: int = 30):
        """Nachylenie (jednostka sygnału / jednostka czasu) w OSTATNIM
        `window`-próbkowym oknie - nie w całej historii. Centrowanie
        t0 = t[window_start] dla numerycznej stabilności przy dużych
        znacznikach czasu (ten sam wzorzec co w TIMDR-Battery-Predict/
        TIMDR-Industrial-Predict - patrz ich README dla historii tego
        konkretnego bugu w oryginalnych wersjach kodu)."""
        t = np.asarray(t, dtype=float)
        x = np.asarray(x, dtype=float)
        n = len(x)
        if n < 2:
            return 0.0, 0.0
        start = max(0, n - window)
        t_win = t[start:] - t[start]
        x_win = x[start:]
        if len(t_win) < 2:
            return 0.0, 0.0
        A = np.vstack([t_win, np.ones_like(t_win)]).T
        (slope, intercept), *_ = np.linalg.lstsq(A, x_win, rcond=None)
        return float(slope), float(intercept)

    def rhythm(self, x, max_lag: int = 60, power_thresh: float = 0.35):
        """
        Wykrywa dominującą okresowość sygnału (regularność rytmu) metodą
        autokorelacji na sygnale po pełnym odtrendowaniu (nachylenie +
        wyraz wolny), z detekcją TYLKO lokalnych maksimów - dokładnie ten
        sam, zweryfikowany wzorzec co w catalog_core.py
        (TIMDR-Earthquake-Core) i timdr_battery_fusion.py
        (TIMDR-Battery-Predict), gdzie udokumentowano i naprawiono bug
        rektyfikacji (branie |sygnału| przed analizą rytmu tworzy
        sztuczną periodyczność o podwojonej częstotliwości - TU tego
        unikamy pracując na sygnale ZE ZNAKIEM, nie na |x| ani na
        pochodnej bezwzględnej).

        Zwraca: (periods, power) - periods to lista wykrytych opóźnień
        (w próbkach) z lokalnym maksimum mocy, power to moc najsilniejszego
        z nich (0 jeśli brak wyraźnej periodyczności).

        Zastosowanie: zdrowy rytm zatokowy (EKG) albo regularny oddech
        MA wyraźny, silny szczyt periodyczności przy opóźnieniu = R-R
        interval / cykl oddechowy. Arytmia / nieregularny oddech
        rozmywa ten szczyt - power spada poniżej progu.
        """
        x = np.asarray(x, dtype=float)
        n = len(x)
        if n < 8:
            return [], 0.0

        idx = np.arange(n, dtype=float)
        coeffs = np.polyfit(idx, x, 1)
        trend_line = np.polyval(coeffs, idx)
        detrended = x - trend_line

        std = np.std(detrended)
        if std == 0:
            return [], 0.0

        max_lag = min(max_lag, n - 2)
        if max_lag < 2:
            return [], 0.0

        acf = np.zeros(max_lag + 1)
        for lag in range(1, max_lag + 1):
            a, b = detrended[:-lag], detrended[lag:]
            denom = np.std(a) * np.std(b) * len(a)
            if denom == 0:
                acf[lag] = 0.0
                continue
            acf[lag] = np.sum(a * b) / denom

        peaks = []
        for lag in range(2, max_lag):
            if acf[lag] > acf[lag - 1] and acf[lag] > acf[lag + 1] and acf[lag] > power_thresh:
                peaks.append((lag, float(acf[lag])))

        if not peaks:
            return [], 0.0

        peaks.sort(key=lambda p: -p[1])
        periods = [p[0] for p in peaks]
        best_power = peaks[0][1]
        return periods, best_power

    def rhythm_regularity(self, peak_indices, t=None) -> dict:
        """
        Regularność rytmu na podstawie odstępów MIĘDZY WYKRYTYMI SZCZYTAMI
        (np. załamkami R w EKG, cyklami oddechu) - odpowiednik klinicznej
        zmienności rytmu (HRV - heart rate variability). To osobna,
        bardziej bezpośrednia metoda niż rhythm() (autokorelacja całego
        sygnału) - przydatna, gdy masz już wykryte pojedyncze uderzenia/
        cykle (np. z zewnętrznego detektora QRS), a nie tylko surowy
        sygnał.

        peak_indices: rosnąco posortowane indeksy próbek ze szczytami
                      (np. załamki R)
        t:            opcjonalnie, znaczniki czasu tych próbek (jeśli
                      brak, używane są same indeksy)

        Zwraca dict: intervals (odstępy), mean_interval, cv (współczynnik
        zmienności = std/mean - im WYŻSZY, tym bardziej nieregularny
        rytm), n_intervals.
        """
        peak_indices = np.asarray(peak_indices)
        if len(peak_indices) < 2:
            return {"intervals": [], "mean_interval": None, "cv": None, "n_intervals": 0}

        if t is not None:
            t = np.asarray(t, dtype=float)
            times = t[peak_indices]
        else:
            times = peak_indices.astype(float)

        intervals = np.diff(times)
        mean_interval = float(np.mean(intervals))
        cv = float(np.std(intervals) / mean_interval) if mean_interval != 0 else None

        return {
            "intervals": intervals.tolist(),
            "mean_interval": mean_interval,
            "cv": cv,
            "n_intervals": len(intervals),
        }

    def detect_peaks(self, x, distance: int = 5, prominence_factor: float = 3.0):
        """
        Prosty detektor lokalnych maksimów (np. załamki R w EKG, cykle
        oddechu) - lokalne maksimum, które jest wyraźnie wyższe od
        poziomu bazowego, z minimalnym odstępem `distance` próbek między
        kolejnymi szczytami (zapobiega wykrywaniu kilku "szczytów" na
        jednym załamku R z powodu szumu).

        POPRAWKA (znaleziona przy testowaniu na syntetycznym EKG):
        próg bazowany na MAD (median + prominence_factor*MAD) zawodzi,
        gdy prawdziwe szczyty są RZADKIE względem długości sygnału (np.
        ~5% próbek to załamki R, reszta to poziom bazowy) - w takiej
        sytuacji mediana i MAD są liczone głównie z samego szumu
        tła (bo stanowi >50% próbek), więc MAD wychodzi w skali szumu,
        NIE w skali różnicy szum-vs-szczyt. Zweryfikowano empirycznie na
        syntetycznym EKG (RR=20 próbek, szum std=0.02, szczyty=1.0):
        MAD dawał próg ~0.024 (praktycznie w skali samego szumu) -
        pojedyncza próbka szumu 0.035 przechodziła próg i była fałszywie
        zgłaszana jako "szczyt" między prawdziwymi załamkami R.
        Odchylenie standardowe całego sygnału (`std(x)`) jest tu dużo
        odporniejszą miarą - uwzględnia realny kontrast szczyt/tło nawet
        gdy szczyty są rzadkie (dawało próg ~0.33 - prawidłowo powyżej
        szumu, poniżej prawdziwych szczytów). Naprawiono: prog liczony
        zawsze na bazie std(x), nie MAD; podniesiono też domyślny
        prominence_factor z 1.5 do 3.0 dla dodatkowego marginesu
        bezpieczeństwa.
        """
        x = np.asarray(x, dtype=float)
        n = len(x)
        if n < 3:
            return np.array([], dtype=int)

        med = np.median(x)
        threshold = med + prominence_factor * np.std(x)

        candidates = []
        for i in range(1, n - 1):
            if x[i] > x[i - 1] and x[i] >= x[i + 1] and x[i] > threshold:
                candidates.append(i)
        # brzegi (pierwsza/ostatnia próbka) - dopuszczalne jako szczyt,
        # jeśli jednostronnie wyższe od sąsiada i powyżej progu
        if n >= 2 and x[0] > x[1] and x[0] > threshold:
            candidates.append(0)
        if n >= 2 and x[-1] > x[-2] and x[-1] > threshold:
            candidates.append(n - 1)

        if not candidates:
            return np.array([], dtype=int)

        # egzekwuj minimalny odstęp - zachłannie, od najwyższego szczytu
        candidates.sort(key=lambda i: -x[i])
        kept = []
        for c in candidates:
            if all(abs(c - k) >= distance for k in kept):
                kept.append(c)
        kept.sort()
        return np.array(kept, dtype=int)

    def envelope_drop(self, x, window: int, factor: float = 3.0, step: int = None):
        """
        Wykrywa NAGŁY SPADEK zmienności (obwiedni) sygnału - odwrotność
        typowego wykrywania "za dużo się dzieje": tu szukamy okien, gdzie
        nagle "za mało się dzieje" względem reszty nagrania.

        DLACZEGO TA FUNKCJA ISTNIEJE (znalezione empirycznie przy
        budowie demo): `anomalies()` i `twist()` działają na WARTOŚCI
        próbek - dla sygnału oscylującego (np. oddech, sinusoida wokół
        0), wartości w epizodzie "spłaszczenia" (np. bezdech - brak
        ruchu oddechowego) mieszczą się w zupełnie NORMALNYM zakresie
        wartości, jakie i tak przyjmuje zdrowa oscylacja (sinus i tak
        przechodzi przez okolice 0 dwa razy na cykl) - MAD-z pojedynczych
        próbek nie odróżnia "chwilowe 0 w trakcie oscylacji" od "trwałe
        0 bo brak oddechu". Zweryfikowano na syntetycznym `resp_apnea`:
        `anomalies()` i `twist()` dawały 0 wykryć w całym 20-sekundowym
        epizodzie bezdechu, mimo oczywistego (dla oka) spłaszczenia
        wykresu.

        Metoda: lokalne odchylenie standardowe w przesuwnych oknach
        (rolling std), potem MAD-z znormalizowany PO WSZYSTKICH oknach -
        okna ze std dramatycznie niższym niż typowe (z < -factor) są
        zwracane jako podejrzane o "utratę zmienności" (bezdech, asystolia
        w EKG, cisza bioelektryczna w EEG - w zależności od typu sygnału).

        window: rozmiar okna w próbkach (dobierz tak, by pokrywał
                kilka cykli typowego sygnału - np. dla oddechu ~15/min
                przy fs=5Hz, window=fs*10 pokrywa ~2.5 cyklu)
        step:   krok przesuwania okna (domyślnie window//4)

        Zwraca: listę (start_idx, end_idx) dla okien z wykrytym spadkiem
        obwiedni (posklejanych, jeśli sąsiadują).
        """
        x = np.asarray(x, dtype=float)
        n = len(x)
        if window < 4 or n < window * 2:
            return []
        step = step or max(1, window // 4)

        starts = list(range(0, n - window + 1, step))
        stds = np.array([np.std(x[s:s + window]) for s in starts])

        z = _mad_z(stds)
        flagged = np.where(z < -factor)[0]
        if len(flagged) == 0:
            return []

        # sklej sąsiadujące/zachodzące na siebie okna w ciągłe zakresy
        ranges = []
        cur_start = starts[flagged[0]]
        cur_end = starts[flagged[0]] + window
        for fi in flagged[1:]:
            s, e = starts[fi], starts[fi] + window
            if s <= cur_end:
                cur_end = max(cur_end, e)
            else:
                ranges.append((cur_start, cur_end))
                cur_start, cur_end = s, e
        ranges.append((cur_start, cur_end))
        return ranges


class TIMDRBioFusion:
    """
    Fuzja WIELU kanałów fizjologicznych (EKG, EEG, puls, oddech) w jeden
    ogólny wskaźnik "coś jest nie tak" E(t) - używana WYŁĄCZNIE do
    anomalii/twist na poziomie całego pacjenta, NIGDY do rhythm() (patrz
    docstring modułu - fuzja różnych naturalnych częstotliwości przed
    analizą rytmu nie ma sensu i tworzy artefakty).
    """

    def __init__(self):
        self._engine = TIMDRBioSignal()

    def fuse(self, **channels) -> np.ndarray:
        """
        channels: dowolna liczba kanałów jako kwargs, np.
                  fuse(ecg=ecg_arr, eeg=eeg_arr, pulse=pulse_arr, resp=resp_arr)
                  Wszystkie muszą mieć tę samą długość.

        Zwraca E(t) = sqrt(sum(z_i(t)^2)) po kanałach, gdzie z_i to
        MAD-z każdego kanału z osobna (każdy kanał ma swoją własną skalę
        - nie da się bezpośrednio sumować mV EKG z Hz EEG bez normalizacji).
        """
        if not channels:
            raise ValueError("fuse() wymaga przynajmniej jednego kanału")

        arrays = {name: np.asarray(vals, dtype=float) for name, vals in channels.items()}
        lengths = {len(v) for v in arrays.values()}
        if len(lengths) > 1:
            raise ValueError(f"Kanały mają różne długości: { {k: len(v) for k, v in arrays.items()} }")

        zs = [np.abs(_mad_z(v)) for v in arrays.values()]
        return np.sqrt(np.sum(np.square(zs), axis=0))

    def anomalies(self, E: np.ndarray, factor: float = 3.0) -> np.ndarray:
        """Anomalie na już-połączonym E(t) - E jest zawsze nieujemne
        (norma), więc próg jest jednostronny (>factor*mediana+MAD), nie
        symetryczny jak w _mad_z."""
        E = np.asarray(E, dtype=float)
        if len(E) == 0:
            return np.array([], dtype=int)
        med = np.median(E)
        mad = np.median(np.abs(E - med))
        if mad == 0:
            span = np.max(E) - np.min(E)
            scale = span / 4 if span != 0 else 1.0
        else:
            scale = mad / 0.6745
        threshold = med + factor * scale
        return np.where(E > threshold)[0]
