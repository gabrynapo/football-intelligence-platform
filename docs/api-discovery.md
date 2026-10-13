# Verifica API-Football Free

Ricerca documentale e verifica autenticata: **13 ottobre 2026**.

## Esito osservato

Verifica completata alle **15:00 Europe/Rome (13:00 UTC)**:

- `/status`: HTTP 200, chiave valida, account **Free attivo**, limite di 100
  richieste/giorno e 10/minuto.
- `/leagues?id=39&season=2026`: HTTP 200 con errore applicativo `plan`:
  `Free plans do not have access to this season, try from 2022 to 2024.`
- Arresto dopo 2 chiamate: squadre, calendario, classifica e statistiche non
  interrogati. Nessuna prova è stata effettuata sulle annate 2022–2024.

**Decisione tecnica:** API-Football Free, con questo account, non consente di
procedere con la stagione richiesta 2026/27. La disponibilità nel catalogo e la
copertura dei singoli endpoint restano non verificate a causa del diniego.
Il campo `season_in_catalog: false` del report indica che non è stata osservata
metadata della stagione; in presenza di `access_denied` non ne dimostra l'assenza.

Evidenza locale, esclusa da Git:
`reports/coverage-2026-20261013T130054888886Z.json` e relativo Markdown.
Un precedente tentativo nell'ambiente isolato era fallito per trasporto:
il ledger conserva **3 tentativi complessivi**, inclusa quella chiamata fallita.
Non è disponibile un valore aggiornato affidabile della quota residua dopo il
diniego, perché la risposta non conteneva gli header di quota.

La chiave precedentemente inserita in `.env.example` è stata spostata nel file
locale `.env`, ignorato da Git. Il probe continua a leggere esclusivamente la
variabile d'ambiente `API_FOOTBALL_KEY`; non carica `.env` automaticamente.

## Contratto della fonte

Provider: API-SPORTS diretto; base URL `https://v3.football.api-sports.io`;
header `x-apisports-key`, valore da `API_FOOTBALL_KEY`. League ID Premier League:
`39`. Stagione: `2026`. L'ID Brighton viene risolto dalla lista delle squadre
di quella stagione, senza presupporre la partecipazione o un ID non verificato.

Le [tariffe ufficiali](https://www.api-football.com/pricing/) indicano 100
richieste/giorno e restrizioni sulle stagioni del piano Free. Non pubblicano lì
una lista contrattuale delle annate ammesse: nessuna garanzia sul 2026/27.
La [guida ufficiale](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
spiega stagione come anno iniziale, league ID, struttura delle risposte e filtri.
La [documentazione di riferimento](https://www.api-football.com/documentation-v3)
resta il riferimento per i contratti degli endpoint.

La [guida ufficiale alla quota](https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage)
riporta 10 richieste/minuto per Free e raccomanda di verificare coverage,
paginazione e header. I limiti ricevuti dall'account restano decisivi.
Coverage indica supporto dichiarato per competizione/stagione; non garantisce
che ogni partita contenga ogni statistica né prova il diritto di accesso Free.

## Sequenza del probe

| # | Endpoint e parametri | Evidenza ricercata |
| --- | --- | --- |
| 1 | `/status` | Account attivo Free, consumo e limite; dati personali scartati |
| 2 | `/leagues?id=39&season=2026` | Stagione nel catalogo e coverage dichiarata |
| 3 | `/teams?league=39&season=2026` | Squadre restituite, identificazione univoca Brighton |
| 4 | `/fixtures?league=39&season=2026` | Calendario, conteggio FT, risultati non null, partite Brighton |
| 5 | `/standings?league=39&season=2026` | Numero di righe nella classifica annidata |
| 6 | `/teams/statistics?league=39&season=2026&team=<id>` | Partite giocate e gol aggregati Brighton |
| 7 | `/fixtures/statistics?fixture=<id>` | Tipi di statistiche valorizzate/null per una partita Brighton FT |

Il campione è la partita Brighton conclusa più recente restituita, con kickoff
passato e punteggi presenti. Nessuna chiamata aggiuntiva per trovare il campione.
Se non esiste viene registrato `skipped`, non un errore o assenza di copertura.
La coverage dichiarata viene confrontata con evidenze reali: anche un flag false
non viene considerato una prova definitiva senza tentare l'endpoint rilevante.
Lineups, eventi, giocatori, quote e previsioni del provider sono fuori dall'MVP.
Le probabilità future verranno prodotte dal nostro modello, non da `/predictions`.

## Interpretazione

| Outcome | Significato |
| --- | --- |
| `data_returned` | Risposta non vuota; controllare campi, conteggi e null |
| `partial` | Esistono più pagine; solo la prima è stata osservata |
| `empty` | Nessun dato restituito; non prova una restrizione del piano |
| `access_denied` | HTTP 401/403 oppure messaggio di accesso/piano nell'envelope |
| `api_error` | Errore applicativo anche con HTTP 200; leggere il messaggio |
| `rate_limited` | Quota/rate limit; il probe si ferma senza retry |
| `http_error` / `transport_error` / `invalid_response` | Verifica inconcludente |
| `skipped` | Manca una dipendenza, ad esempio una partita Brighton conclusa |
| `not_checked` | Arresto prima del controllo; nessuna conclusione sull'endpoint |

La classificazione dei messaggi è euristica; il report conserva errori redatti
per interpretazione manuale. Un 403 non dimostra da solo che il problema sia
la stagione. `data_returned` con tutti i valori null non abilita una funzionalità.
Il JSON mantiene conteggi e tipi non null del campione, non i payload integrali.
Un solo campione non dimostra la completezza stagionale. Non sono dati di training.

## Protezione della quota

- Massimo 7 tentativi per esecuzione; nessun retry, redirect o paging automatico.
- Ogni tentativo viene prenotato su disco prima dell'I/O, anche se fallisce.
- Ledger locale `.state/quota.json`: massimo 80 tentativi per data UTC; non cancellarlo
  per rilanciare il probe. Il margine lascia spazio a consumi non pianificati.
- Lock `.state/probe.lock` impedisce due esecuzioni contemporanee nel checkout.
  Dopo un crash rimuoverlo solo dopo aver verificato che nessun probe sia attivo.
- `/status` apre ogni esecuzione. Quota da header e, per status, da `requests`;
  senza quota verificabile si ferma. Si ferma prima di consumare la riserva di 10.
- Header normalizzati senza distinzione maiuscole/minuscole; i limiti al minuto
  possono aumentare l'intervallo. Quota minuto esaurita: arresto, non attesa/retry.
- Risposta con diniego, 429, errore HTTP o formato invalido: niente ulteriori chiamate.
- Nessun token nei log/report, nessun account/email salvato, timeout 20 secondi.

**Limite operativo:** il ledger è locale, non coordina altri computer, dashboard
o applicazioni che usano lo stesso account. Gli header sono istantanee, non
prenotazioni globali. Usare un solo consumer durante la verifica. Anche la prima
chiamata `/status` deve raggiungere il provider per conoscere la quota account.
Non si può garantire globalmente il limite in presenza di consumatori concorrenti.
La futura pipeline userà un unico scheduler e un ledger PostgreSQL condiviso.
Non presumere che la cache effimera di GitHub Actions sia un ledger affidabile.

## Decisione dopo la verifica

1. **Dati fondamentali disponibili:** confermare squadra/stagione, calendario e
   risultati; valutare completezza e null. Il prossimo passo è ingestione raw.
2. **Risultati sì, statistiche no:** avviare un MVP con punti/gol e modello sui
   risultati, rendendo esplicite le metriche mancanti.
3. **2026/27 vietato al Free:** fermare la pipeline per questa stagione. Decidere
   esplicitamente se usare una stagione storica consentita come demo, valutare
   un'altra fonte gratuita con licenza adeguata, o rinviare l'aggiornamento live.
   Non sostituire automaticamente l'annata né interpretare il diniego come zero partite.
4. **Risposte vuote o errori tecnici:** report inconcludente; consultare dashboard e
   messaggio prima di ripetere la chiamata. Niente tentativi sulle altre annate a cascata.

La disponibilità dello storico per l'addestramento è un controllo separato:
solo dopo questa fase, provare poche annate esplicitamente selezionate, con lo
stesso budget. Il report del 2026/27 non prova che ci siano dati sufficienti per ML.
Le condizioni di uso/redistribuzione vanno valutate prima di pubblicare dati o loghi:
[termini del provider](https://www.api-football.com/terms). Per xG/xGA futuri,
registrare separatamente fonte, versione, copertura e licenza.
