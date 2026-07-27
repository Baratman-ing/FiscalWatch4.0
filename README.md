# Fiscal Watch 4.0

Monitor gratuito di fonti istituzionali su Transizione 4.0, Transizione 5.0, iperammortamento, beni strumentali e argomenti collegati.

## Come funziona

- legge feed RSS o pagine HTML configurate;
- individua i link non ancora visti;
- assegna un punteggio in base alle parole chiave;
- apre una GitHub Issue quando trova nuovi documenti rilevanti;
- conserva lo storico in `data/seen.json`.

La prima esecuzione inizializza lo storico e non genera notifiche arretrate. Dalla seconda esecuzione vengono segnalati soltanto i nuovi contenuti.

## Installazione su GitHub

1. Crea un repository pubblico vuoto.
2. Carica tutti i file di questo progetto.
3. In `Settings > Actions > General`, abilita i permessi di lettura e scrittura per `GITHUB_TOKEN`.
4. Apri la scheda `Actions`, seleziona `Fiscal Watch 4.0` e avvia `Run workflow`.
5. Esegui una seconda volta per verificare il meccanismo incrementale.

Il workflow programmato parte ogni giorno alle 06:15 UTC, cioè alle 08:15 in Italia con ora legale e alle 07:15 con ora solare.

## Configurazione

Modifica `config.yml` per:

- aggiungere o rimuovere fonti;
- cambiare parole chiave;
- modificare il punteggio minimo;
- aggiungere sorgenti RSS impostando `type: rss`.

Esempio RSS:

```yaml
- name: "Nome feed"
  type: rss
  url: "https://esempio.it/feed.xml"
```

## Esecuzione locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fiscal_watch.py
```

Su Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python fiscal_watch.py
```

## Limiti

Il filtro analizza titolo, testo vicino al collegamento e URL. Non apre né analizza il contenuto completo dei PDF. Questo mantiene il sistema semplice e completamente gratuito, ma può produrre falsi positivi o perdere documenti con titoli generici.
