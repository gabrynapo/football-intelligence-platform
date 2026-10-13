# football-data.org: verifica alternativa

## Esito autenticato del 13 ottobre 2026

Esecuzione conclusa alle **15:15 Europe/Rome**, senza errori, con 4 chiamate:

| Endpoint | Risultato osservato |
| --- | --- |
| Competizione | Premier League, ID 2021, stagione corrente 2026/27 |
| Squadre | 20; Brighton & Hove Albion FC ID 397 |
| Partite | 380, di cui 60 FINISHED con punteggi presenti; 38 Brighton |
| Classifica | 20 righe TOTAL; Brighton 3°, 13 punti dopo 6 gare, GF 18 / GA 5 |

Prossima gara Brighton restituita: Brighton–Crystal Palace, **18 ottobre 2026,
15:00 Europe/Rome** (13:00 UTC). È un'osservazione al momento del probe,
non un calendario garantito immutabile.

Report locale: `reports/football-data-2026-20261013T131541706329Z.json`.
Un tentativo precedente era fallito per trasporto nell'ambiente isolato: il ledger
conta 5 tentativi totali, mentre l'esecuzione riuscita ne ha effettuati 4.
L'ultimo header indicava 7 richieste disponibili nella finestra al minuto.

**Decisione:** procedere con football-data.org per l'MVP descrittivo 2026/27.
Il conteggio del calendario è coerente con una stagione a 20 squadre, ma controlli
su duplicati, accoppiamenti e qualità verranno eseguiti nell'ingestione.
Le stagioni elencate nel catalogo non provano accesso gratuito allo storico:
questa verifica resta separata. Nessuna pipeline completa è stata implementata.

Il provider dichiara la Premier League nel piano gratuito, con risultati ritardati
e un limite di 10 chiamate/minuto. Fonte: [copertura](https://www.football-data.org/coverage)
e [piani](https://www.football-data.org/pricing). Non dedurre l'accesso a ogni stagione
dalla copertura commerciale; serve una verifica autenticata.

## Contratto e controlli

Base URL `https://api.football-data.org/v4`, header `X-Auth-Token` da
`FOOTBALL_DATA_TOKEN`. Riferimento: [documentazione della competizione](https://docs.football-data.org/general/v4/competition.html).

| Chiamata | Evidenza |
| --- | --- |
| `/competitions/PL` | Identità della competizione e stagioni nel catalogo |
| `/competitions/PL/teams?season=2026` | Squadre della stagione e ID Brighton |
| `/competitions/PL/matches?season=2026` | Calendario, risultati valorizzati, prossima gara Brighton |
| `/competitions/PL/standings?season=2026` | Classifica TOTAL e riepilogo Brighton |

Massimo 4 tentativi, nessun retry/redirect o richiesta a stagioni alternative.
Il probe confronta anno restituito e anno richiesto. `empty` non prova un diniego;
`partial` indica una discrepanza fra conteggio dichiarato e righe restituite.
Numero di righe e valori non null richiedono comunque una successiva verifica
di qualità: nessun report del probe certifica da solo la completezza del calendario.

Ogni chiamata è distanziata di almeno 6,1 secondi tramite stato persistente locale.
Lock e contatore separati in `.state/football-data/`; limite locale prudenziale
di 80 tentativi/giorno, che **non è un limite contrattuale dichiarato dal provider**.
Gli header di quota disponibili sono salvati nel report. Quota minuto esaurita,
429, diniego o risposta invalida fermano il probe; nessun retry automatico.
Altri consumer dello stesso account non sono coordinati da questo lock locale.

Non viene interrogato un endpoint di abbonamento: il report non certifica il
nome del piano account. La sola risposta della competizione non dimostra accesso
allo storico. Nessuna verifica di xG, tiri, possesso o dati necessari al training
è implicita nelle quattro chiamate. Gli ID di football-data.org sono distinti
da quelli di API-SPORTS e richiedono un mapping esplicito.

Esecuzione: `python scripts/check_football_data.py --season 2026 --env-file .env`.
Codici previsti: 0 probe concluso (leggere gli esiti), 2 token/configurazione mancante,
3 interruzione con report parziale quando possibile. Il token non è salvato nel report.
