# Football Intelligence Platform

Portfolio end-to-end di Data Engineering, Football Analytics e Machine Learning:
Premier League **2026/27**, dashboard inizialmente focalizzata sul **Brighton**.

**Fase attuale: architettura e verifica della fonte.** Sono implementati soltanto
il probe API, i suoi test offline e la CI dei test. Database, pipeline, dbt,
dashboard e modelli sono progettati, non ancora implementati.

Il piano API-Football Free dichiara 100 richieste/giorno ma limita le stagioni.
**Verifica autenticata del 13 ottobre 2026: accesso al 2026/27 negato dal piano
Free.** La chiave funziona e l'account è attivo; `/leagues?id=39&season=2026`
restituisce una restrizione di piano e suggerisce le stagioni dal 2022 al 2024.
Queste annate non sono state ancora provate. La pipeline 2026/27 resta sospesa
in attesa di una decisione sulla fonte o sulla stagione della demo.
`season=2026` identifica la stagione 2026/27. Non basta che esista nel catalogo,
né che `coverage` sia positivo: servono risposte reali per gli endpoint necessari.
Fonti e limiti: [verifica API](docs/api-discovery.md).

## Avvio senza dipendenze esterne

Python 3.11 o superiore; comandi dalla radice del repository:

```powershell
python scripts/check_api_coverage.py --dry-run
python -m unittest discover -s tests -v
```

Per la verifica reale serve una chiave di un account **diretto API-SPORTS Free**,
ottenuta dal [dashboard del provider](https://dashboard.api-football.com/).
Il client non supporta RapidAPI. Impostare `API_FOOTBALL_KEY` nell'ambiente
del processo; non inserire il token nel codice, in chat o negli argomenti CLI.
Esempio PowerShell senza registrarlo nella cronologia:

```powershell
$apiKeyInput = Read-Host 'API-Football key' -AsSecureString
$env:API_FOOTBALL_KEY = [System.Net.NetworkCredential]::new('', $apiKeyInput).Password
python scripts/check_api_coverage.py --season 2026
Remove-Item Env:\API_FOOTBALL_KEY
Remove-Variable apiKeyInput
```

`.env.example` descrive la variabile; **i file `.env` non vengono caricati**.
La variabile deve essere esportata nella stessa sessione che avvia Python.
Non serve installare PostgreSQL, dbt o Streamlit in questa fase.

Il probe esegue al massimo **7 tentativi**, distanziati di almeno 6,1 secondi,
incluso `/status` nel budget conservativo. È possibile restringerlo con
`--max-requests 3`. Scrive report JSON e Markdown con timestamp UTC in `reports/`.
Non pubblica dati, non avvia schedulazioni e non scarica tutte le pagine.
Un secondo avvio ripete la verifica e consuma nuova quota; riutilizzare il report.

Codici di uscita: `0` verifica conclusa (anche con risposte vuote o controlli
saltati), `2` configurazione mancante/non valida, `3` interruzione con evidenze
parziali quando disponibili. **Exit 0 non significa piattaforma fattibile.**
Leggere `outcome`, `coverage_declared`, contatori e campi non null nel JSON.

## Struttura implementata

```text
.github/workflows/ci.yml         # soli test offline, nessun secret/API
docs/
  architecture.md               # flusso dati, schema logico, ML e roadmap
  api-discovery.md              # endpoint, interpretazione e decisione go/no-go
scripts/check_api_coverage.py    # entrypoint dal checkout
src/football_intelligence/
  api.py                        # HTTP, quota, classificazione errori
  probe.py                      # verifica dipendenze e report
tests/test_probe.py              # risposte sintetiche; zero richieste reali
reports/                        # report locali ignorati da Git
.state/                         # ledger e lock locali, creati all'esecuzione
.env.example
pyproject.toml
```

La struttura dei moduli futuri e le milestone sono in
[architettura](docs/architecture.md). Le dipendenze future verranno aggiunte
quando servono, senza includere oggi una piattaforma incompleta.

La cartella iniziale non era un repository Git: per pubblicarla, inizializzare
Git e collegare un repository GitHub scelto dall'autore. Nessun remote o push
è stato creato automaticamente. I workflow saranno attivi dopo la pubblicazione.
