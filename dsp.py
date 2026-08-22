"""
dsp.py — filtracja, wykrywanie QRS (Pan-Tompkins) i widmo mocy dla
TIMDR-Bio-Signals.
=============================================================================
Patrz bio_core.py dla pełnego zastrzeżenia medycznego - dotyczy również
tego modułu. Wszystkie algorytmy tutaj to standardowe, podręcznikowe
metody DSP zastosowane do sygnałów fizjologicznych w celach badawczo-
-edukacyjnych, NIE certyfikowana implementacja kliniczna.

Zawiera:
  butter_bandpass_filter(x, fs, low, high, order)
      Filtr Butterwortha pasmowoprzepustowy, zerofazowy (filtfilt) - do
      analizy OFFLINE (cała historia sygnału dostępna na raz). Zerowa
      faza = brak przesunięcia w czasie wykrytych zdarzeń względem
      oryginału, ale wymaga całego sygnału (NIE nadaje się do
      przetwarzania na żywo próbka-po-próbce).

  CausalBandpassFilter
      Ten sam filtr Butterwortha, ale KAUZALNY (scipy.signal.lfilter z
      utrzymywanym stanem `zi` między wywołaniami) - do przetwarzania
      strumieniowego/na żywo, gdzie kolejne porcje danych przychodzą
      stopniowo i nie wolno "zaglądać w przyszłość". Wprowadza
      niewielkie opóźnienie fazowe (rząd = połowa rzędu filtra x okres
      próbkowania), co jest nieuniknioną ceną kauzalności - patrz
      README, sekcja "Filtracja offline vs strumieniowa".

  pan_tompkins_qrs(x, fs)
      Klasyczny algorytm Pan-Tompkins (1985) do wykrywania zespołów QRS
      w EKG: filtr pasmowoprzepustowy 5-15 Hz -> pochodna -> podniesienie
      do kwadratu -> całkowanie w przesuwnym oknie -> adaptacyjny próg
      z okresem refrakcji. Zwraca indeksy załamków R (zmapowane z powrotem
      na ORYGINALNY, niefiltrowany sygnał - lokalne maksimum w oknie
      wokół szczytu sygnału całkowanego).

  power_spectrum(x, fs, nperseg=None)
      Widmo mocy metodą Welcha (scipy.signal.welch) - uśrednione po
      nakładających się oknach, więc dużo mniej szumu wariancji niż
      surowe |FFT|^2 na całym sygnale na raz. Zwraca częstotliwości,
      moc oraz częstotliwość/moc dominującą.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, lfilter, lfilter_zi, welch


def butter_bandpass_coeffs(fs: float, low: float, high: float, order: int = 4):
    """Współczynniki (b, a) filtra Butterwortha pasmowoprzepustowego.
    `low`/`high` w Hz, muszą spełniać 0 < low < high < fs/2 (Nyquist)."""
    nyq = fs / 2.0
    if not (0 < low < high < nyq):
        raise ValueError(
            f"Nieprawidłowe pasmo [{low}, {high}] Hz dla fs={fs} Hz "
            f"(wymagane 0 < low < high < Nyquist={nyq} Hz)"
        )
    low_n = low / nyq
    high_n = high / nyq
    b, a = butter(order, [low_n, high_n], btype="band")
    return b, a


def butter_bandpass_filter(x, fs: float, low: float, high: float, order: int = 4) -> np.ndarray:
    """Zerofazowa filtracja pasmowoprzepustowa (offline, filtfilt).
    Wymaga sygnału dłuższego niż ~3x rząd filtra (ograniczenie filtfilt
    dot. długości paddingu) - dla krótkich sygnałów zwraca oryginał
    niezmieniony zamiast rzucać wyjątkiem (patrz test)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < max(order * 3 + 1, 15):
        return x.copy()
    b, a = butter_bandpass_coeffs(fs, low, high, order)
    return filtfilt(b, a, x)


class CausalBandpassFilter:
    """Kauzalny filtr pasmowoprzepustowy Butterwortha z utrzymywanym
    stanem między wywołaniami `process()` - do przetwarzania danych
    napływających porcjami (streaming), gdzie filtfilt (patrz wyżej)
    nie może być użyty, bo wymagałby znajomości "przyszłych" próbek.

    Użycie:
        f = CausalBandpassFilter(fs=250, low=5, high=15, order=4)
        out1 = f.process(chunk1)
        out2 = f.process(chunk2)   # kontynuuje stan filtra z chunk1
    """

    def __init__(self, fs: float, low: float, high: float, order: int = 4):
        self.b, self.a = butter_bandpass_coeffs(fs, low, high, order)
        zi0 = lfilter_zi(self.b, self.a)
        # zi_skalowane do zerowego sygnału wejściowego na starcie
        self._zi = zi0 * 0.0

    def process(self, chunk) -> np.ndarray:
        chunk = np.asarray(chunk, dtype=float)
        if len(chunk) == 0:
            return chunk
        out, self._zi = lfilter(self.b, self.a, chunk, zi=self._zi)
        return out

    def reset(self):
        self._zi = self._zi * 0.0


def pan_tompkins_qrs(x, fs: float, refractory_s: float = 0.2):
    """
    Klasyczny algorytm Pan-Tompkins do wykrywania załamków R w EKG.

    Kroki (Pan & Tompkins, 1985):
      1. filtr pasmowoprzepustowy 5-15 Hz (offline, filtfilt) - usuwa
         dryf linii bazowej i wysokoczęstotliwościowy szum mięśniowy,
         zachowuje pasmo charakterystyczne dla zespołu QRS
      2. pochodna (np.gradient) - podkreśla strome zbocza QRS
      3. podniesienie do kwadratu - wszystko dodatnie, dodatkowo
         podkreśla duże wartości (QRS >> reszta)
      4. całkowanie w przesuwnym oknie ~150ms - "wygładza" pojedynczy
         zespół QRS w jedno gładkie wzniesienie (moving window integrator)
      5. adaptacyjny próg (mediana + k*MAD sygnału całkowanego) +
         okres refrakcji (żadne dwa uderzenia bliżej niż `refractory_s`,
         fizjologiczne ograniczenie - serce nie bije szybciej niż ~300-
         -400/min)
      6. mapowanie z powrotem: dla każdego wykrytego "wzniesienia" w
         sygnale całkowanym, prawdziwy załamek R to lokalne maksimum
         ORYGINALNEGO (niefiltrowanego) sygnału w małym oknie wokół niego
         - bo filtracja+całkowanie przesuwa/rozmywa dokładny czas szczytu.

    Zwraca: np.ndarray indeksów (w oryginalnym sygnale x) wykrytych
    załamków R, posortowane rosnąco.

    Różnica względem bio_core.detect_peaks(): detect_peaks to prosty,
    ogólny detektor lokalnych maksimów z progiem std(x) - działa na
    DOWOLNYM sygnale spiky-periodycznym (patrz demo.py, gdzie był
    używany dla czystego demo EKG). Pan-Tompkins jest SPECYFICZNY dla
    EKG (pasmo 5-15Hz dobrane pod charakterystykę QRS) i znacznie
    odporniejszy na dryf linii bazowej oraz szum spoza pasma QRS -
    właściwy wybór, gdy sygnał ma realistyczne zakłócenia (nie tylko
    czysty szum gaussowski jak w demo_scenarios.py).
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 8 or fs <= 0:
        return np.array([], dtype=int)

    nyq = fs / 2.0
    low, high = 5.0, min(15.0, nyq * 0.95)
    if low >= high:
        # fs zbyt niska dla klasycznego pasma Pan-Tompkins (potrzeba fs > ~11Hz)
        # - fallback: użyj bio_core.detect_peaks zamiast rzucać wyjątek
        from bio_core import TIMDRBioSignal
        return TIMDRBioSignal().detect_peaks(x, distance=max(1, int(0.3 * fs)))

    filtered = butter_bandpass_filter(x, fs, low, high, order=4)
    deriv = np.gradient(filtered)
    squared = deriv ** 2

    win = max(1, int(round(0.150 * fs)))  # ~150ms okno całkowania
    kernel = np.ones(win) / win
    integrated = np.convolve(squared, kernel, mode="same")

    med = np.median(integrated)
    mad = np.median(np.abs(integrated - med))
    scale = mad / 0.6745 if mad > 0 else (np.std(integrated) or 1.0)
    threshold = med + 2.5 * scale

    refractory = max(1, int(round(refractory_s * fs)))

    # znajdź lokalne maksima sygnału całkowanego powyżej progu,
    # egzekwując okres refrakcji zachłannie od najwyższego
    above = np.where(integrated > threshold)[0]
    if len(above) == 0:
        return np.array([], dtype=int)

    candidates = []
    for i in range(1, len(integrated) - 1):
        if integrated[i] > threshold and integrated[i] >= integrated[i - 1] and integrated[i] >= integrated[i + 1]:
            candidates.append(i)
    if not candidates:
        candidates = [int(above[np.argmax(integrated[above])])]

    candidates.sort(key=lambda i: -integrated[i])
    kept = []
    for c in candidates:
        if all(abs(c - k) >= refractory for k in kept):
            kept.append(c)
    kept.sort()

    # zmapuj każdy kandydat na lokalne maksimum ORYGINALNEGO sygnału
    # w oknie +/- refractory/2 wokół niego (koryguje przesunięcie
    # wprowadzone przez filtrację + całkowanie)
    half = max(1, refractory // 2)
    r_peaks = []
    for c in kept:
        lo = max(0, c - half)
        hi = min(n, c + half + 1)
        local_max = lo + int(np.argmax(x[lo:hi]))
        r_peaks.append(local_max)

    # deduplikuj (dwa kandydaty mogły zmapować się na ten sam szczyt)
    r_peaks = sorted(set(r_peaks))
    return np.array(r_peaks, dtype=int)


def power_spectrum(x, fs: float, nperseg: int | None = None) -> dict:
    """
    Widmo mocy metodą Welcha - dzieli sygnał na nakładające się okna
    (domyślnie ~1/4 długości sygnału, max 256 próbek), liczy periodogram
    każdego i uśrednia - dużo gładsze/mniej-szumowe widmo niż pojedyncze
    |FFT(x)|^2 na całym sygnale, kosztem rozdzielczości częstotliwościowej
    (kompromis akceptowalny dla identyfikacji DOMINUJĄCEJ częstotliwości,
    czyli głównego zastosowania tutaj - np. "czy w EEG jest wyraźne pasmo
    alfa ~8-12Hz", "jaka jest częstotliwość oddechu").

    Zwraca dict: freqs (lista Hz), power (lista, ta sama długość),
    dominant_freq (Hz, częstotliwość o największej mocy - pomijając
    składową stałą 0Hz), dominant_power.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 8 or fs <= 0:
        return {"freqs": [], "power": [], "dominant_freq": None, "dominant_power": None}

    if nperseg is None:
        # Domyślnie 1/4 długości sygnału (co najmniej 2 nakładające się okna
        # przy 50% overlap Welcha), ale nie mniej niż 8 i nie więcej niż 2048
        # - zbyt małe okno (np. stały cap 256 przy fs=250Hz i n=15000) daje
        # rozdzielczość częstotliwościową ~1Hz, co jest ZA GRUBE, by odróżnić
        # fundamentalną częstotliwość ~1.17Hz (70bpm) EKG/pulsu od jej
        # najbliższych harmonicznych - zweryfikowano empirycznie: przy
        # nperseg=256 dominant_freq dla zdrowego demo EKG (70bpm) wychodził
        # błędnie ~1.95Hz (2. harmoniczna), a przy nperseg>=1024 poprawnie
        # ~1.22Hz (blisko prawdziwych 1.1667Hz).
        nperseg = min(2048, max(8, n // 4))
    nperseg = min(nperseg, n)

    freqs, power = welch(x, fs=fs, nperseg=nperseg)

    # pomiń składową stałą (0Hz) przy szukaniu dominującej częstotliwości -
    # dryf linii bazowej/średnia niezerowa zdominowałaby wynik bez sensu
    # fizjologicznego
    nonzero = freqs > 0
    if not np.any(nonzero):
        dominant_freq, dominant_power = None, None
    else:
        idx = np.argmax(power[nonzero])
        dominant_freq = float(freqs[nonzero][idx])
        dominant_power = float(power[nonzero][idx])

    return {
        "freqs": freqs.tolist(),
        "power": power.tolist(),
        "dominant_freq": dominant_freq,
        "dominant_power": dominant_power,
    }
