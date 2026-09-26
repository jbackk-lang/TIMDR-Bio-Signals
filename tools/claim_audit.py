"""TIMDR-AI-Core: audyt twierdzeń w README (v0.2).

Każde twierdzenie z README ma kartę: dokładny cytat, pliki źródłowe i funkcję, która przelicza wartość z surowych
wyników. Silnik sprawdza: dowód (R1), pokrycie liczb (R3), świeżość hashy (R4), kompletność (R5), kotwicę czasu w gicie
(R6) i sformułowania (R7). Tylko biblioteka standardowa; karty mogą używać NumPy/pandas.
Opis reguł i format karty: CLAIM_AUDIT.md w TIMDR-AI-Core. Repozytoria wendorują ten plik (tools/claim_audit.py).

v0.2 (po pilotażu MAST w TIMDR-fusion-tools): R5 z osobnym wzorcem wymaganym dla każdego wyzwalacza;
R6 z opcjonalnym wzorcem ujawnienia (ograniczenie opisane w README = UJAWNIONE zamiast NIEROZSTRZYGNIĘTE).

Użycie: python claim_audit.py sciezka/do/claims_xxx.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

__version__ = "0.2"

POTWIERDZONE, SPRZECZNE, NIEROZSTRZYGNIETE, UDOKUMENTOWANE = ("POTWIERDZONE", "SPRZECZNE", "NIEROZSTRZYGNIĘTE",
                                                               "UDOKUMENTOWANE")
UJAWNIONE = "UJAWNIONE"


@dataclass
class Result:
    verdict: str
    value: str
    reason: str = ""


@dataclass
class Claim:
    id: str
    quote: str
    check: Callable[[], Result]
    sources: list[str] = field(default_factory=list)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(text: str) -> str:
    return " ".join(text.split())


def extract(text: str, start: str, end: str) -> str:
    """Fragment od linii pasujacej do `start` (wlacznie) do pierwszej pozniejszej linii pasujacej do `end` (wylacznie)."""
    lines = text.splitlines()
    i = next(k for k, l in enumerate(lines) if re.search(start, l))
    j = next((k for k in range(i + 1, len(lines)) if re.search(end, lines[k])), len(lines))
    return "\n".join(lines[i:j])


NUM = re.compile(r"(?<![A-Za-z_/.\d])\d+(?:[.,]\d+)?(?![A-Za-z_\d])")


def numbers(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in NUM.finditer(text)]


def git_first_commit(repo: Path, path: Path) -> tuple[str, int] | None:
    """Pierwszy commit, ktory dodal plik (hash, czas unix). Tylko odczyt - nie dotyka indeksu."""
    out = subprocess.run(["git", "-C", str(repo), "log", "--diff-filter=A", "--format=%h %ct", "--",
                          str(path.relative_to(repo))], capture_output=True, text=True).stdout.split()
    return (out[-2], int(out[-1])) if len(out) >= 2 else None


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Dwustronny dokladny test Fishera dla [[a, b], [c, d]]."""
    from math import comb
    r1, c1, n = a + b, a + c, a + b + c + d
    denom = comb(n, c1)
    p_obs = comb(r1, a) * comb(n - r1, c1 - a) / denom
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return min(1.0, sum(comb(r1, x) * comb(n - r1, c1 - x) / denom for x in range(lo, hi + 1)
                        if comb(r1, x) * comb(n - r1, c1 - x) / denom <= p_obs * (1 + 1e-9)))


def within(stated: float, actual: float, *, approx: bool, pct: bool = False, decimals: int = 0) -> bool:
    """Regula R2 z pre-rejestracji."""
    if not approx:
        return round(actual, decimals) == round(stated, decimals)
    if pct:
        return abs(actual - stated) <= (1.0 if decimals > 0 else 2.0)
    return abs(actual - stated) <= 0.15 * abs(stated)


def run(spec) -> tuple[str, dict]:
    repo = Path(spec.REPO)
    readme = (repo / spec.README).read_text(encoding="utf-8")
    scopes = [norm(extract(readme, s, e)) for s, e in spec.SCOPES]
    scope_text = "\n".join(scopes)
    rows, findings = [], []

    # R1 + R2: karty
    spans = []
    for c in spec.CLAIMS:
        q = norm(c.quote)
        pos = scope_text.find(q)
        if pos < 0:
            rows.append((c, Result(NIEROZSTRZYGNIETE, "-", "cytat nie wystepuje w README (karta nieaktualna)")))
            continue
        spans.append((pos, pos + len(q)))
        try:
            r = c.check()
        except Exception as exc:  # karta, ktorej nie da sie policzyc, nie jest dowodem
            r = Result(NIEROZSTRZYGNIETE, "-", f"blad przeliczenia: {type(exc).__name__}: {exc}")
        rows.append((c, r))

    # R3: pokrycie liczb
    uncovered = [n for s, e, n in numbers(scope_text) if not any(a <= s and e <= b for a, b in spans)]
    if uncovered:
        findings.append(("R3 pokrycie", "NIEPOKRYTE", f"liczby bez karty: {', '.join(uncovered)}"))

    # R4: swiezosc
    for path, frozen in getattr(spec, "FROZEN", {}).items():
        now = sha256(repo / path)
        if now != frozen:
            findings.append(("R4 świeżość", NIEROZSTRZYGNIETE, f"{path}: hash {now[:12]} != zamrozony {frozen[:12]}"))
    if getattr(spec, "FROZEN", {}) and not any(f[0] == "R4 świeżość" for f in findings):
        findings.append(("R4 świeżość", POTWIERDZONE, f"{len(spec.FROZEN)} plikow zgodnych z zamrozonymi hashami"))

    # R5: kompletnosc
    for evidence_path, trigger, required, why in getattr(spec, "COMPLETENESS", []):
        text = (repo / evidence_path).read_text(encoding="utf-8")
        if not re.search(trigger, text):
            continue
        if re.search(required, scope_text, re.I):
            findings.append(("R5 kompletność", POTWIERDZONE, f"{why} - README to podaje"))
        else:
            findings.append(("R5 kompletność", "BRAK KOMPLETNOŚCI", f"{evidence_path}: {why}; README tego nie podaje"))

    # R6: kotwica czasu
    disclosure = getattr(spec, "ANCHOR_DISCLOSURE", None)
    for prereg, results in getattr(spec, "ANCHORS", []):
        a, b = git_first_commit(repo, repo / prereg), git_first_commit(repo, repo / results)
        if a is None or b is None:
            findings.append(("R6 kotwica", NIEROZSTRZYGNIETE, f"{prereg} lub {results} poza gitem"))
        elif a[1] < b[1]:
            findings.append(("R6 kotwica", POTWIERDZONE, f"{prereg} ({a[0]}) przed {results} ({b[0]})"))
        elif disclosure and re.search(disclosure, scope_text, re.I):
            findings.append(("R6 kotwica", UJAWNIONE, f"{prereg} i {results} w tym samym commicie ({a[0]} / {b[0]}); "
                                                      f"README opisuje to ograniczenie"))
        else:
            findings.append(("R6 kotwica", NIEROZSTRZYGNIETE, f"{prereg} i {results} w tym samym lub pozniejszym commicie "
                                                              f"({a[0]} / {b[0]}) - zamrozenie tylko deklarowane"))

    # R7: sformulowania
    for pat, neg, why in getattr(spec, "FORBIDDEN", []):
        for m in re.finditer(pat, scope_text, re.I):
            before = scope_text[max(0, m.start() - 40): m.start()]
            if not re.search(neg, before, re.I):
                findings.append(("R7a zakazane", SPRZECZNE, f"„{m.group()}”: {why}"))
    for pat, advice in getattr(spec, "ABSOLUTE", []):
        for m in re.finditer(pat, scope_text, re.I):
            findings.append(("R7b sformułowanie", "DO ZŁAGODZENIA", f"„{m.group()}”: {advice}"))

    return render(spec, rows, findings), {"rows": rows, "findings": findings}


def render(spec, rows, findings) -> str:
    count = {}
    for _, r in rows:
        count[r.verdict] = count.get(r.verdict, 0) + 1
    out = [f"# Audyt twierdzeń: {spec.TITLE}", "", f"Silnik: claim_audit v{__version__} (TIMDR-AI-Core).", "",
           f"Wygenerowano: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}; reguły: `{spec.PREREG}` "
           f"(sha256 {sha256(Path(spec.REPO) / spec.PREREG)[:12]}), karty: `{Path(spec.__file__).name}` "
           f"(sha256 {sha256(spec.__file__)[:12]}), README sha256 {sha256(Path(spec.REPO) / spec.README)[:12]}.", "",
           "Werdykty kart: " + ", ".join(f"{k} {v}" for k, v in sorted(count.items())) + ".", "",
           "## Twierdzenia", "", "| # | Twierdzenie (cytat z README) | Werdykt | Przeliczenie | Uwagi |", "| --- | --- | --- | --- | --- |"]
    for c, r in rows:
        out.append(f"| {c.id} | {norm(c.quote)} | {r.verdict} | {r.value} | {r.reason} |")
    out += ["", "## Reguły całego fragmentu", "", "| Reguła | Wynik | Szczegóły |", "| --- | --- | --- |"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in findings]
    return "\n".join(out) + "\n"


def load_spec(path):
    s = importlib.util.spec_from_file_location("claims_spec", path)
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    spec = load_spec(sys.argv[1])
    text, _ = run(spec)
    out = Path(spec.__file__).with_name(spec.OUTPUT)
    out.write_text(text, encoding="utf-8")
    print(text)
