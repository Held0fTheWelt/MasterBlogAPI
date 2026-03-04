# MasterBlog

Ein kleines Blog-System: Du kannst Beiträge lesen, suchen, sortieren und – wenn du angemeldet bist – neue schreiben, ändern oder löschen.

---

## Was ist das?

- **Backend:** Ein Server, der die Blog-Daten verwaltet und eine API bereitstellt (z. B. unter `http://localhost:5002`).
- **Frontend:** Eine einfache Webseite, auf der du die Beiträge siehst, suchst und neue eintragen kannst.
- **Datenbank:** Die Beiträge werden in einer Datei gespeichert (`data/masterblog.db`) und bleiben auch nach einem Neustart erhalten.

---

## Schnellstart

### 1. Voraussetzungen

- **Python** (Version 3.8 oder neuer) soll auf deinem Rechner installiert sein.

### 2. Abhängigkeiten installieren

Im Projektordner im Terminal ausführen:

```bash
pip install -r requirements.txt
```

Damit werden alle nötigen Python-Pakete installiert.

### 3. Datenbank anlegen (nur einmal nötig)

Damit der Server etwas anzeigen kann, braucht er eine Datenbank mit Testdaten. Dafür gibt es ein kleines Hilfsprogramm:

```bash
python backend/init_db.py
```

Es erstellt den Ordner `data/` (falls er noch nicht existiert) und legt darin die Datenbank mit zwei Beispiel-Beiträgen an. Du kannst diesen Befehl auch später nochmal ausführen, um die Daten wieder auf den Ausgangszustand zu setzen.

### 4. Server starten

```bash
python backend/backend_app.py
```

Der Server läuft dann unter **http://127.0.0.1:5002** (oder http://localhost:5002).

### 5. Frontend öffnen

Die Blog-Webseite findest du im Ordner `frontend/`. Öffne die Datei `frontend/templates/index.html` im Browser (per Doppelklick oder „Datei öffnen“). Dort kannst du die API-Adresse eintragen (z. B. `http://127.0.0.1:5002/api/v1`), auf „Load Posts“ klicken und die Beiträge ansehen, suchen und sortieren.

---

## Was kann die API?

- **Beiträge anzeigen** – alle oder einzeln, mit Autor und Datum.
- **Suchen** – nach Titel, Inhalt, Autor oder Datum.
- **Sortieren** – z. B. nach Titel oder Datum, auf- oder absteigend.
- **Neuen Beitrag anlegen** – nur mit Anmeldung (Token).
- **Beitrag ändern oder löschen** – ebenfalls nur mit Anmeldung.

Zum Anmelden und Testen der geschützten Aktionen eignen sich z.B. **Postman** oder die **API-Dokumentation** im Browser unter:

**http://127.0.0.1:5002/api/docs**

Dort siehst du alle Wege (Endpoints) der API und kannst sie ausprobieren. Über „Authorize“ kannst du dich mit Benutzername und Passwort anmelden und dann z. B. Beiträge anlegen oder löschen.

---

## Ordnerstruktur (kurz)

- **backend/** – Server-Code und Einstellungen; hier liegt auch `init_db.py` zum Anlegen der Datenbank.
- **frontend/** – Webseite (HTML, CSS, JavaScript) zum Anzeigen und Bedienen der Beiträge.
- **data/** – Hier wird die Datenbankdatei abgelegt (wird von `init_db.py` bzw. dem Server erstellt).
- **postman/** – Vordefinierte Anfragen für Postman zum Testen der API.

---

## Hinweise

- **Anmeldung:** Neue Nutzer legst du über die API an (z.B. in Postman: `POST …/api/v1/register` mit Benutzername und Passwort). Danach meldest du dich mit `POST …/api/v1/login` an und erhältst einen Token für geschützte Aktionen.
- **Port:** Der Server nutzt standardmäßig den Port **5002**. Wenn dieser schon belegt ist, musst du die Konfiguration anpassen oder einen anderen Port verwenden.

Bei Fragen einfach im Projekt nachschauen oder die API-Dokumentation unter `/api/docs` nutzen.
