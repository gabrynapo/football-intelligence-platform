# Football Intelligence Platform

Portfolio end-to-end di Data Engineering, Football Analytics e Machine Learning:
Premier League **2026/27**, dashboard inizialmente focalizzata sul **Brighton**.

**Fase attuale: dashboard Streamlit con dati reali.** Sono implementati i probe API,
il frontend Brighton, un client con cache persistente e test offline/di interfaccia.
PostgreSQL, pipeline schedulata, dbt e modelli predittivi restano fasi successive.

## Avvia la dashboard

Il token football-data.org deve essere in `FOOTBALL_DATA_TOKEN` nell'ambiente
oppure nel file locale `.env`, ignorato da Git. Dal repository, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dashboard]"
.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
```

Aprire **http://127.0.0.1:8501**. Se l'ambiente virtuale è già pronto, basta l'ultimo
comando. Su Linux/macOS usare `.venv/bin/python` al posto di `.venv\Scripts\python.exe`.

- Selezione stagione e indicatori: punti, posizione, media punti, gol fatti/subiti.
- Grafici interattivi: punti cumulati, gol per gara, forma sulle ultime 5 partite.
- Rendimento casa/trasferta, ultimo risultato e prossima partita.
- Calendario filtrabile con esportazione CSV, classifica con Brighton evidenziato.
- Confronto fino a quattro stagioni a parità di partite giocate.

**Verificati con il tuo account il 13 ottobre 2026:** 2026/27 (6 risultati Brighton),
2025/26 e 2024/25 (38 risultati Brighton ciascuna). Le altre stagioni del catalogo
restano da verificare: un diniego viene mostrato senza inventare dati.

La cache locale dura un'ora per risultati/classifiche e 24 ore per il catalogo;
filtrare tabelle e cambiare scheda non causa nuove chiamate entro questi intervalli.
Il pulsante di aggiornamento ha un intervallo minimo di 60 secondi. Le richieste
sono distanziate di almeno 6,1 secondi e condividono il ledger con il probe.
Nessuna schedulazione o chiamata a pagamento viene attivata.
[Funzionamento e limiti della dashboard](docs/dashboard.md).

Il piano API-Football Free dichiara 100 richieste/giorno ma limita le stagioni.
**Verifica autenticata del 13 ottobre 2026: accesso al 2026/27 negato dal piano
Free.** La chiave funziona e l'account è attivo; `/leagues?id=39&season=2026`
restituisce una restrizione di piano e suggerisce le stagioni dal 2022 al 2024.
Queste annate non sono state ancora provate. **football-data.org è stato invece
verificato con successo per il 2026/27** ed è la fonte scelta per il prossimo MVP.
`season=2026` identifica la stagione 2026/27. Non basta che esista nel catalogo,
né che `coverage` sia positivo: servono risposte reali per gli endpoint necessari.
Fonti e limiti: [verifica API](docs/api-discovery.md).

## Alternativa: football-data.org

Verifica autenticata del **13 ottobre 2026**: 4 risposte HTTP 200, 20 squadre,
380 partite (60 concluse con punteggio), 38 gare Brighton e classifica TOTAL con
20 righe. ID Brighton su questo provider: **397**. Verificati successivamente anche
i risultati 2025/26 e 2024/25 per il confronto in dashboard. Le statistiche avanzate
restano da verificare; il database resta da implementare.

È disponibile un secondo probe indipendente, con al massimo **4 chiamate**:
competizione Premier League, squadre, partite e classifica. Controlla il filtro
stagione e restituisce conteggi, presenza Brighton e prossima partita osservata.
L'accesso reale viene registrato nel report, senza dedurlo dalla sola lista stagioni.

Inserire il token del nuovo provider in `.env` (escluso da Git), su una riga separata:

```dotenv
FOOTBALL_DATA_TOKEN=il_token_del_nuovo_provider
```

```powershell
python scripts/check_football_data.py --dry-run
python scripts/check_football_data.py --season 2026 --env-file .env
```

`--env-file` legge solo `FOOTBALL_DATA_TOKEN`; una variabile d'ambiente già
impostata ha precedenza. Non usa mai `API_FOOTBALL_KEY` per il nuovo servizio.
Report JSON in `reports/football-data-2026-<timestamp>.json`; dettagli e limiti
in [football-data.org discovery](docs/football-data-discovery.md).

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

`.env.example` descrive la variabile; **il probe API-Football non carica `.env`**.
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
scripts/check_football_data.py   # probe alternativo football-data.org
src/football_intelligence/
  api.py                        # HTTP, quota, classificazione errori
  probe.py                      # verifica dipendenze e report
  football_data.py              # client e probe football-data.org v4
tests/test_probe.py              # risposte sintetiche; zero richieste reali
reports/                        # report locali ignorati da Git
.state/                         # ledger e lock locali, creati all'esecuzione
.env.example
pyproject.toml
```

Il frontend è in `app/streamlit_app.py` e i grafici in `app/charts.py`.
`src/football_intelligence/dashboard_data.py` gestisce cache e accesso ai dati;
`analytics.py` contiene i calcoli testabili indipendentemente da Streamlit.
La struttura dei moduli futuri e le milestone sono in [architettura](docs/architecture.md).

La cartella iniziale non era un repository Git: per pubblicarla, inizializzare
Git e collegare un repository GitHub scelto dall'autore. Nessun remote o push
è stato creato automaticamente. I workflow saranno attivi dopo la pubblicazione.
