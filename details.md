# Freie-Räume-App — Technische Details

Statische HTML-Übersicht, die pro Tag und Raum zeigt, zu welchen Uhrzeiten
Seminarräume der **DHBW Villingen-Schwenningen** frei sind. Schwester-App
zu `../rapla-counter/`, aber eigenständig und unabhängig.

## Projektstruktur

```
Freie-Räume-App/
├── app.py              # Rapla-Parser + Raumextraktion + Slot-Berechnung
├── collect_rooms.py    # CLI: Räume aus Rapla sammeln → rooms.json
├── generate_static.py  # CLI: Statische Quartalsseite erzeugen
├── rooms.json          # Halbautomatisch gepflegte Raumliste
├── Raumliste.md        # Menschenlesbare Referenz-Raumliste (auto-generiert)
├── docs/
│   └── index.html      # Generierter Output
├── requirements.txt    # beautifulsoup4, requests
└── details.md          # diese Datei
```

Kein Flask. Keine Live-Server. Nur CLI-Skripte und statische Ausgabe.

## Datenquelle

Die DHBW nutzt **Rapla** als Stundenplansystem. Die Daten werden über eine
öffentliche Kalender-URL abgerufen:

```
https://rapla.dhbw.de/rapla/calendar?key=...&salt=...&day=D&month=M&year=Y
```

Seit 2026-07 verwendet diese App einen **eigenen** Rapla-Kalender-Link
("DHBW-VS Raumbelegung Parkplatz (Habla)"), unabhängig vom Link in
`rapla-counter`. Dieser Kalender zeigt zusätzlich zu regulären
Kursbuchungen auch Ad-hoc-Raumreservierungen (z.B. mündliche Prüfungen),
ist aber strukturell identisch (`table.week_table`, `week_block`-Zellen,
`<span class="resource">`) — der Parser musste dafür nicht angepasst
werden, nur `RAPLA_BASE` in `app.py`.

**Wichtig:** Der `key=`-Parameter läuft halbjährlich ab und muss in
`app.py` (Konstante `RAPLA_BASE`) unabhängig von `rapla-counter/app.py`
aktualisiert werden.

## Raumextraktion

Der bestehende Parser in `rapla-counter/app.py` extrahiert pro `week_block`
nur Start-/Endzeit. Diese App erweitert den Parser um `extract_rooms_from_block()`,
das die Raumnamen aus den `<span class="resource">`-Elementen holt und per
Heuristik von Kursgruppen und Dozenten abgrenzt.

### Beobachtete HTML-Struktur eines week_blocks

```html
<td class="week_block" rowspan="9" style="...">
    <a href="#327">
        08:00 - 10:15<br>
        Kursname + Dozent
    </a>
    <br>
    <span class="resource">VS-SXX24H</span>                       <!-- Kursgruppe -->
    <br>
    <span class="resource">C 2.21 Hörsaal (Sozialwesen)</span>    <!-- Raum -->
</td>
```

Alle `resource`-Spans enthalten Kursgruppen, Studierende und Räume durcheinander
und sind nicht typisiert. Die Unterscheidung erfolgt per Raumnamen-Heuristik.

### Heuristik für Raumnamen

Ein Eintrag ist genau dann ein Raum, wenn:
1. Er **nicht** mit `VS-` oder `VS ` beginnt (das sind Kursgruppen/Studierende), **und**
2. Er entweder einer der Sonderräume (`Aula`, `Mensa`) ist, **oder**
3. Er mit dem Präfix `[Buchstabe] [optional -]Ziffer(n)(.Ziffer(n))?` beginnt
   (Regex `ROOM_PREFIX_RE = r"^[A-Z]\s-?\d+(?:\.\d+)?(?:\s|$)"`).

**Hinweis:** Vor der Heuristik-Prüfung werden Klammer-Zusätze entfernt
(`_clean_room_name()` in `app.py`). Rapla hängt an Raumnamen gerne
Fachbereichs-Kürzel und Anmerkungen in Klammern an (`(Sozialwesen)`, `(IB)`,
`(Bank) (auch als PC-Raum nutzbar)`, sogar URLs in Klammern). Diese
Zusätze sind redundant und werden per Regex `\s*\([^)]*\)` entfernt; der
kanonische Schlüssel ist der Name **ohne** Klammern.

Beispiele erkannter Räume (nach Cleaning):
- `C 3.24 Hörsaal`
- `D 108 Hörsaal`
- `B 201 Hörsaal`
- `C -1.23 Gutenberg Tiefenhörsaal` (Untergeschoss)
- `D 014 Hörsaal`

Der **gesäuberte Text** ist der kanonische Schlüssel in `rooms.json`.
Zusätzlich wird ein `short_name` heuristisch extrahiert (`C 3.24` aus
`C 3.24 Hörsaal`) für die kompakte Anzeige.

### Filter

Der Parser überspringt folgende Einträge (damit sie nicht als Raumbelegung
zählen):

- Einträge mit `online` im Zelltext (Online-Veranstaltungen belegen keinen
  physischen Raum)
- Einträge mit `Ausflug` oder `Exkursion` im Zelltext (Studierende sind nicht
  am Campus)

An gesetzlichen Feiertagen in Baden-Württemberg werden alle Räume als
`holiday` markiert, auch wenn Rapla Einträge anzeigt (Feiertagsberechnung per
Anonymous-Gregorian-Algorithmus, 12 BW-Feiertage).

## rooms.json

Format:

```json
{
  "rooms": [
    {
      "name": "C 3.24 Hörsaal (Sozialwesen)",
      "short_name": "C 3.24",
      "building": "C",
      "floor": 3,
      "include": true
    }
  ],
  "last_collected": "2026-04-11",
  "sources_weeks": 4
}
```

- `name`: kanonischer Schlüssel (Rapla-Name **ohne** Klammer-Zusätze)
- `short_name`: heuristisch aus `name` extrahiert
- `building`, `floor`: heuristisch aus `name` abgeleitet, manuell überschreibbar
- `include`: `false` blendet einen Raum aus der Ausgabe aus (für False-Positives
  der Heuristik — derzeit keine bekannt)

### Raumliste.md (Referenz)

Zusätzlich zu `rooms.json` erzeugt `collect_rooms.py` eine menschenlesbare
`Raumliste.md` — nach Gebäude gruppiert, innerhalb jedes Gebäudes alphabetisch
bzw. numerisch sortiert. Dient als Nachschlagewerk, unabhängig von der HTML-
Seite. Wird bei jedem `collect_rooms.py`-Lauf überschrieben.

### Merge-Verhalten von `collect_rooms.py`

- **Neue Räume** werden mit Defaults eingefügt.
- **Bestehende Räume** behalten alle manuellen Felder (`include`,
  überschriebene `building`/`floor`).
- **Verschwundene Räume** bleiben in der Liste erhalten und werden nur im
  Diff gemeldet — so verliert man keine Seltenräume, die in einem bestimmten
  Quartal nicht belegt sind.

## Slot-Algorithmus

`compute_free_slots(busy_intervals, open_start, open_end, min_free_minutes)`
in `app.py` berechnet die freien Zeitfenster:

1. **Clip** alle Events auf `[open_start, open_end]` (Default: 08:00–20:00),
   verwerfe leere/ungültige Intervalle.
2. **Sort + Merge** überlappender Intervalle.
3. **Invertiere** zu freien Slots zwischen den Merges + vor erstem + nach
   letztem.
4. **Filter** Slots kürzer als `min_free_minutes` (Default: 15 Minuten),
   damit triviale Mikrolücken nicht angezeigt werden.

Edge-Cases:
- Events über Mitternacht (`start >= end`) werden verworfen.
- Duplikat-Events werden vom Merge automatisch absorbiert.

`build_day_free_rooms()` wendet den Algorithmus auf alle Räume an und gibt
einen der Statuswerte zurück:
- `holiday` — Feiertag
- `free_all_day` — ganz frei (Wochenende, keine Events, oder ganzer Slot)
- `busy_all_day` — durchgehend belegt
- `partial` — teilweise frei (Liste der Slots in `free`)

## HTML-Layout

- **Tag pro Screen**, nicht Matrix: Bei 40+ Räumen × 5 Tagen wäre eine flache
  Tabelle unlesbar.
- Zwei Dropdowns: **Woche** + **Tag**. Default = heute bzw. Montag der
  aktuellen Woche, falls im Datensatz enthalten.
- Tabelle: Zeilen = Räume alphabetisch, gruppiert nach Gebäude. Spalte = freie
  Slots als Chips.
- Chip-Styles:
  - Freier Slot: hellgrün
  - `ganztägig frei`: kräftiger grün
  - `ganztägig belegt`: grau
  - `Feiertag`: grau kursiv
- Komplettes Quartal als eingebettetes JSON (`const DATA = {...}`),
  JavaScript filtert clientseitig. Keine Netzwerkrequests aus dem Browser.

## CLI-Nutzung

### 1. Räume sammeln / aktualisieren

```bash
# Mit Quartal
python collect_rooms.py --quarter 2026-Q2

# Oder: N Wochen ab einem Start-Montag
python collect_rooms.py --weeks 12 --start 2026-04-20
```

Ausgabe: `rooms.json` wird erstellt/gemerged. Diff und unbekannte Zellen-Samples
werden ausgegeben — letztere zur Kalibrierung der Heuristik prüfen.

### 2. Statische Seite generieren

```bash
# Quartal
python generate_static.py --quarter 2026-Q2 --output docs/index.html

# Oder: N Wochen
python generate_static.py --weeks 3 --start 2026-04-20 --output docs/index.html
```

Generiert `docs/index.html` mit allen Wochendaten als eingebettetes JSON.
Die Datei ist eigenständig und kann lokal im Browser oder per GitHub Pages
gehostet werden.

## Wartung

- **Halbjährlich:** Rapla-Link (`RAPLA_BASE` in `app.py`) prüfen und ggf.
  aktualisieren. Der Key läuft jeweils vor SoSe (März) und WiSe (September) ab.
  Gleicher Key wie in `../rapla-counter/app.py` — beide Apps sollten
  zeitgleich aktualisiert werden.
- **Pro Semester:** `collect_rooms.py --quarter ...` ausführen, um neue oder
  umbenannte Räume zu erfassen. Den Diff prüfen, ggf. False-Positives auf
  `include: false` setzen.
- **Bei Bedarf:** `generate_static.py` neu ausführen und `docs/index.html`
  committen (falls GitHub Pages gehostet).

## Bekannte Einschränkungen

- **Keine externen Standorte:** Veranstaltungen in Horb, Ludwigsburg,
  HS Schmalenbach etc. werden nicht erfasst, weil diese Räume nicht in der
  VS-Heuristik landen.
- **Raum nur im Kurstext:** Vereinzelte Veranstaltungen geben den Raum als
  Fließtext im Kursnamen an (z.B. "Data Leverage Hr. Ritavan/ Raum Schmalenbach
  C121") statt als `resource`-Span. Diese werden nicht erkannt. Praktisch
  selten, kann bei Bedarf als zweiter Fallback nachgerüstet werden.
- **Keine Kapazität / Ausstattung:** `rooms.json` speichert nur Name und
  Gebäude/Etage. Kapazität, Technikausstattung etc. sind nicht erfasst.

## Nicht im MVP (mögliche Iteration 2)

- Matrix-Sicht (Räume × Wochentage)
- Suche/Filter nach Gebäude oder Raumnummer
- Kapazitätsmetadaten
- Export als CSV/ICS
- HFU-Integration (StarPlan) — derzeit nur DHBW
