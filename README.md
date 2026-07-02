# FG-Ripetizioni - CRM & Piattaforma Gestionale per Tutoraggio

Una piattaforma web full-stack sviluppata in **Django** per l'automazione e la gestione a 360 gradi di un'attività di ripetizioni private. Il sistema gestisce in autonomia le prenotazioni, il calendario, le tariffe dinamiche e le comunicazioni via email tra docente e studenti.

🔗 **[Visita l'App in Produzione](https://francescogori03.eu.pythonanywhere.com/)**

> **Vuoi testare l'applicazione?**  
> Puoi accedere con queste credenziali ospite per esplorare le funzionalità:
> - **Username:** `recruiter`
> - **Password:** `DemoTutor_2026!` 

## Funzionalità Principali

Il progetto è strutturato in due macro-aree per separare le logiche e le autorizzazioni:

### Area Studente (Frontend Interattivo)
- **Prenotazione Intelligente (HTMX):** Gli studenti possono prenotare lezioni (online o a domicilio). Gli slot orari vengono calcolati e caricati dinamicamente via API tramite HTMX, mostrando **solo gli orari effettivamente liberi**, tenendo conto di lezioni già fissate, orari di lavoro del docente e ferie.
- **Dashboard Personale:** Un'interfaccia riepilogativa dove l'allievo può aggiornare il proprio profilo (anno scolastico, indirizzo), visualizzare lo storico delle lezioni passate, controllare lo stato delle richieste pendenti e monitorare il saldo totale da pagare.

### Area Docente (Pannello di Controllo Amministrativo)
- **Gestione Calendario Avanzata:** Impostazione degli orari di disponibilità settimanale (es. 14:30 - 19:00) e inserimento di giorni di chiusura/vacanza per bloccare le prenotazioni in quei periodi.
- **Approvazione e Integrazione Calendar:** Le richieste arrivano in stato "In attesa". All'accettazione, viene generato in automatico un link per aggiungere comodamente l'evento su Google Calendar.
- **Tariffe e Billing Dinamico:** Il calcolo del prezzo della lezione è automatizzato: `(Tariffa oraria base o personalizzata * Durata) + Eventuale costo di trasferta (basato su km/minuti)`.
- **Gestione Pagamenti:** Dashboard mensile con i profitti e raggruppamento delle lezioni non saldate per ogni singolo studente, con la possibilità di segnarle come pagate con un click.

### Automazioni e Notifiche
Sistema di template email automatizzato per mantenere una comunicazione fluida:
- Alert al docente per ogni nuova richiesta di prenotazione.
- Notifica allo studente di conferma o rifiuto della lezione.
- Invio automatico di resoconti formali per sollecitare i pagamenti arretrati.

## Stack Tecnologico
- **Backend:** Python, Django
- **Frontend:** HTML, CSS, JavaScript, HTMX (per chiamate asincrone e UI reattiva)
- **Database:** SQLite
