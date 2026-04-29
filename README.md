# Freie Räume DHBW Villingen-Schwenningen

Übersicht zu welchen Uhrzeiten welche Räume an der DHBW VS frei sind.

**Live-Seite:** https://wolfganghabla.github.io/freie-raeume-vs/

Datenquelle: [Rapla DHBW](https://rapla.dhbw.de/), automatisch täglich
aktualisiert um 06:00 (Europe/Berlin) via GitHub Actions.

## Lokal generieren

    pip install -r requirements.txt
    python generate_static.py --quarter 2026-Q2 --output docs/index.html

## Räume nachsammeln

    python collect_rooms.py --weeks 4 --start 2026-04-20

Erzeugt/aktualisiert `rooms.json` und die menschenlesbare `Raumliste.md`.

Siehe [`details.md`](details.md) für technische Doku (Rapla-Parser,
Raum-Heuristik, Slot-Algorithmus).
