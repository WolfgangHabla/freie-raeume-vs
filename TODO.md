# TODO — Freie-Räume-App

## Spezielle Rapla-Links für bestimmte Räume

**Hintergrund:** Aktuell nutzt die App genau einen Rapla-Kalender-Link
(`RAPLA_BASE` in `app.py`, `key=...&salt=-888929980`). Manche Räume sind
darüber vermutlich nicht vollständig oder nicht korrekt abgebildet und
haben eigene Rapla-URLs (z.B. raumspezifische Kalender, andere
Hochschulen/Standorte, Sonderbuchungen).

**Aufgabe:**
- Welche Räume sind betroffen? → Liste mit Raumname + zugehöriger Rapla-URL
  pflegen
- Schema überlegen: separates Feld in `rooms.json` (`rapla_url` pro Raum)?
  Oder zweite Datenquelle parallel parsen und mergen?
- `parse_rapla_week_rooms()` in `app.py` so erweitern, dass für Räume mit
  eigenem Link der raumspezifische Kalender abgefragt wird (zusätzlich
  zur globalen Abfrage) und Events sauber zugeordnet werden
- Ggf. Reihenfolge/Priorität klären, wenn ein Raum sowohl im globalen als
  auch im speziellen Link auftaucht (Duplikate vermeiden)

**Offene Fragen für später:**
- Welche Räume genau brauchen das?
- Sind es interne DHBW-VS-Räume oder externe (HFU, andere DHBW-Standorte)?
- Liegen die Spezial-Links bereits irgendwo gesammelt vor?
