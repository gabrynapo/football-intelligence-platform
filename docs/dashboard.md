# Dashboard Brighton

Frontend Streamlit in italiano, alimentato da football-data.org. Nessun dato
dimostrativo viene inserito nell'interfaccia: le fixture sintetiche esistono solo
nei test. L'app ascolta su `127.0.0.1:8501`, senza esporre il server alla rete locale.

## Interfaccia

La barra laterale seleziona una stagione del catalogo dal 2017 in avanti.
La presenza nel catalogo non certifica il diritto di accesso. Panoramica mostra
punti, posizione del provider, punti/gara, gol, ultimi risultati, prossimo incontro,
grafici cumulativi e rendimento casa/trasferta. Partite permette filtri locali
e download CSV; Classifica mostra la tabella TOTAL del provider.

Confronto stagioni richiede al massimo tre annate aggiuntive, solo dopo il submit
del form. La selezione della stagione principale azzera il confronto visualizzato.
Le curve usano il numero di gare giocate, non la giornata nominale: recuperi e
rinvii non alterano l'ordine temporale dei risultati. Una stagione in corso resta
parziale e non viene proiettata a 38 partite.

## Dati, calcoli e credenziali

La dashboard legge `FOOTBALL_DATA_TOKEN` dall'ambiente, con fallback al `.env`
locale. Nessun input per credenziali viene esposto nell'interfaccia. Le risposte
passano attraverso `DashboardSource`: questa interfaccia sarà sostituibile con
query PostgreSQL senza riscrivere i grafici.

Una partita entra nelle metriche solo se FINISHED, con entrambi i punteggi interi
non negativi e kickoff passato con timezone. Gare future, rinviate, in corso e
punteggi nulli non generano punti. I punteggi sono normalizzati dal punto di vista
Brighton, sia in casa che in trasferta. Risultati duplicati Brighton interrompono
il riepilogo. I punti sono calcolati dai risultati; differenze con la classifica
sono segnalate e possono riflettere aggiornamenti o rettifiche.

Cache JSON in `data/cache/football-data/`, esclusa da Git, separata per account
tramite hash del token. TTL: un'ora per partite/classifiche; 24 ore per catalogo.
Rifiuti del provider sono memorizzati per evitare richieste ripetute sui widget.
Il refresh manuale rispetta un cooldown di 60 secondi. Se il refresh fallisce,
una copia precedente può essere mostrata con avviso esplicito e timestamp.

Il lock, il contatore locale da 80 tentativi/giorno e l'intervallo di 6,1 secondi
usano la stessa directory del probe: `.state/football-data/`. Il limite giornaliero
è una nostra scelta prudenziale, non un limite contrattuale football-data.org.
429 e quota al minuto esaurita impediscono ulteriori chiamate della dashboard
durante il periodo di reset. Non ci sono retry automatici. Le altre macchine
che condividono il token non sono coordinate da questo ledger locale.

Questa è una fase intermedia con caricamento su richiesta: non implementa ancora
ingestione raw, orchestrazione, PostgreSQL/dbt o snapshot storici point-in-time.
L'accesso a risultati storici non basta a certificare un backtest senza leakage.
Non ci sono xG o probabilità predittive; la forma mobile è descrittiva.

## Verifica del 13 ottobre 2026

| Stagione | Gare Brighton concluse | Punti dai risultati | GF | GS |
| --- | --- | --- | --- | --- |
| 2026/27 | 6 | 13 | 18 | 5 |
| 2025/26 | 38 | 53 | 52 | 46 |
| 2024/25 | 38 | 61 | 66 | 59 |

Osservazioni restituite dall'API al momento della verifica, non valori statici
codificati nell'app. La classifica 2026/27 contiene 20 righe.

Verifica separata delle classifiche storiche: 2025/26, 2024/25 e 2023/24
restituiscono 20 righe; per 2022/23 il token riceve HTTP 403 (accesso negato).
Questo controllo non prova la disponibilità delle classifiche precedenti.
La scheda Classifica distingue ora un diniego HTTP, un errore di connessione e
una risposta senza righe, riportando l'annata selezionata. Il pulsante
«Ricarica classifica» aggiorna solo la classifica, rispettando il cooldown.

Test: `.venv\Scripts\python.exe -m unittest discover -s tests -v`.
I test offline verificano punteggi casa/trasferta, null e stati non conclusi,
duplicati, cache, refresh, dinieghi, quota e interazione Streamlit tramite AppTest.
Sono stati inoltre eseguiti avvio e confronto con le tre stagioni reali usando
AppTest. La sessione non dispone di un browser controllabile per una verifica
visiva via screenshot; i grafici e le tabelle sono stati verificati a livello di
rendering Streamlit e valori prodotti.

Fonti di implementazione: [Streamlit Plotly](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart),
[football-data.org policy](https://docs.football-data.org/general/v4/policies.html).
