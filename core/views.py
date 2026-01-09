from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
import csv

from .forms import (
    PrenotazioneForm, RegistrazioneForm, ProfiloForm,
    ChiusuraForm, DisponibilitaForm, ImpostazioniForm
)
from .models import Lezione, Disponibilita, Profilo, GiornoChiusura, Impostazioni
from .utils import invia_email_custom


@login_required
def dashboard(request):
    lezioni = Lezione.objects.filter(studente=request.user) \
        .select_related('studente', 'studente__profilo') \
        .order_by('-data_inizio')

    da_pagare = lezioni.filter(stato='CONFERMATA', pagata=False).aggregate(Sum('prezzo'))['prezzo__sum'] or 0

    return render(request, 'core/dashboard.html', {
        'lezioni': lezioni,
        'da_pagare': da_pagare
    })


@login_required
def prenota(request):
    if request.method == 'POST':
        form = PrenotazioneForm(request.POST)
        if form.is_valid():
            lezione = form.save(commit=False)
            lezione.studente = request.user
            lezione.save()

            invia_email_custom(
                soggetto=f"Nuova Lezione: {request.user.username}",
                destinatari=[settings.EMAIL_HOST_USER],
                template_name='nuova_richiesta.html',
                context={'lezione': lezione}
            )

            messages.success(request, 'Richiesta inviata! Riceverai una mail di conferma.')
            return redirect('dashboard')
    else:
        form = PrenotazioneForm()

    return render(request, 'core/prenota.html', {'form': form})


def registrazione(request):
    if request.method == 'POST':
        form = RegistrazioneForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account creato! Ora puoi accedere.')
            return redirect('login')
    else:
        form = RegistrazioneForm()

    return render(request, 'registration/register.html', {'form': form})


def get_orari_disponibili(request):
    data_str = request.GET.get('data')
    if not data_str:
        return HttpResponse("<option value=''>Seleziona prima una data</option>")

    try:
        data_scelta = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponse("<option value=''>Data non valida</option>")

    chiusura = GiornoChiusura.objects.filter(
        data_inizio__lte=data_scelta,
        data_fine__gte=data_scelta
    ).first()

    if chiusura:
        return HttpResponse(f"<option value=''>Non disponibile: {chiusura.motivo or 'Chiuso'}</option>")

    giorno_settimana = data_scelta.weekday()

    try:
        disp = Disponibilita.objects.get(giorno=giorno_settimana)
    except Disponibilita.DoesNotExist:
        return HttpResponse("<option value=''>Nessuna lezione in questo giorno</option>")

    orari_possibili = []
    ora_corrente = datetime.combine(data_scelta, disp.ora_inizio)
    ora_fine = datetime.combine(data_scelta, disp.ora_fine)

    while ora_corrente < ora_fine:
        orari_possibili.append(ora_corrente)
        ora_corrente += timedelta(minutes=30)

    lezioni_giorno = Lezione.objects.filter(
        data_inizio__date=data_scelta,
        stato__in=['RICHIESTA', 'CONFERMATA']
    )

    orari_liberi = []
    for orario in orari_possibili:
        occupato = False
        inizio_slot = timezone.make_aware(orario)

        for lezione in lezioni_giorno:
            lezione_inizio = lezione.data_inizio
            durata = float(lezione.durata_ore) if lezione.durata_ore else 1.0
            lezione_fine = lezione_inizio + timedelta(hours=durata)

            if lezione_inizio <= inizio_slot < lezione_fine:
                occupato = True
                break

        if not occupato:
            str_orario = orario.strftime("%H:%M")
            orari_liberi.append(f"<option value='{str_orario}'>{str_orario}</option>")

    if not orari_liberi:
        return HttpResponse("<option value=''>Tutto occupato!</option>")

    return HttpResponse("".join(orari_liberi))


@login_required
def profilo_view(request):
    try:
        profilo = request.user.profilo
    except Profilo.DoesNotExist:
        profilo = Profilo.objects.create(user=request.user)

    if request.method == 'POST':
        form = ProfiloForm(request.POST, instance=profilo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dati aggiornati con successo!')
            return redirect('dashboard')
    else:
        form = ProfiloForm(instance=profilo)

    return render(request, 'core/profilo.html', {'form': form})


@staff_member_required
@staff_member_required
def dashboard_docente(request):
    config_obj = Impostazioni.objects.first()

    # --- (FORMS HANDLING: Tariffa, Ferie, Disponibilita - Keep existing code) ---
    if request.method == 'POST' and 'btn_tariffa' in request.POST:
        form_tariffa = ImpostazioniForm(request.POST, instance=config_obj)
        if form_tariffa.is_valid():
            form_tariffa.save()
            messages.success(request, "Tariffa oraria aggiornata!")
            return redirect('dashboard_docente')
    else:
        form_tariffa = ImpostazioniForm(instance=config_obj)

    if request.method == 'POST' and 'btn_chiusura' in request.POST:
        form_chiusura = ChiusuraForm(request.POST)
        if form_chiusura.is_valid():
            form_chiusura.save()
            messages.success(request, "Periodo di chiusura aggiunto!")
            return redirect('dashboard_docente')
    else:
        form_chiusura = ChiusuraForm()

    if request.method == 'POST' and 'btn_disponibilita' in request.POST:
        form_disp = DisponibilitaForm(request.POST)
        if form_disp.is_valid():
            giorno = form_disp.cleaned_data['giorno']
            Disponibilita.objects.update_or_create(
                giorno=giorno,
                defaults={
                    'ora_inizio': form_disp.cleaned_data['ora_inizio'],
                    'ora_fine': form_disp.cleaned_data['ora_fine']
                }
            )
            messages.success(request, "Orario settimanale aggiornato!")
            return redirect('dashboard_docente')
    else:
        form_disp = DisponibilitaForm()

    # --- DATA LOADING ---
    oggi = timezone.now()

    richieste = Lezione.objects.filter(stato='RICHIESTA') \
        .select_related('studente', 'studente__profilo') \
        .order_by('data_inizio')

    future = Lezione.objects.filter(stato='CONFERMATA', data_inizio__gte=oggi) \
        .select_related('studente', 'studente__profilo') \
        .order_by('data_inizio')

    inizio_mese = timezone.now().date().replace(day=1)
    guadagno = Lezione.objects.filter(
        stato='CONFERMATA',
        data_inizio__gte=inizio_mese,
        pagata=True
    ).aggregate(Sum('prezzo'))['prezzo__sum'] or 0

    chiusure_future = GiornoChiusura.objects.filter(data_fine__gte=oggi.date()).order_by('data_inizio')
    disponibilita_list = Disponibilita.objects.all().order_by('giorno')

    # --- FIXED GROUPING LOGIC ---
    # The .order_by() is crucial here to remove the default model ordering (by date)
    # causing the duplicates.
    studenti_debitori_ids = Lezione.objects.filter(
        stato='CONFERMATA', pagata=False
    ).order_by().values_list('studente', flat=True).distinct()

    lista_pagamenti = []

    for s_id in studenti_debitori_ids:
        studente = User.objects.get(id=s_id)

        # Get specific unpaid lessons for this student
        lezioni_da_pagare = Lezione.objects.filter(
            studente=studente,
            stato='CONFERMATA',
            pagata=False
        )

        # Calculate totals
        totale_s = lezioni_da_pagare.aggregate(Sum('prezzo'))['prezzo__sum'] or 0
        conta_s = lezioni_da_pagare.count()

        lista_pagamenti.append({
            'studente': studente,
            'numero_lezioni': conta_s,
            'totale': totale_s
        })

    return render(request, 'core/dashboard_docente.html', {
        'richieste': richieste,
        'future': future,
        'guadagno': guadagno,
        'form_chiusura': form_chiusura,
        'chiusure_future': chiusure_future,
        'form_disp': form_disp,
        'disponibilita_list': disponibilita_list,
        'form_tariffa': form_tariffa,
        'lista_pagamenti': lista_pagamenti,
    })

@staff_member_required
def elimina_disponibilita(request, disp_id):
    disp = get_object_or_404(Disponibilita, id=disp_id)
    disp.delete()
    messages.success(request, "Orario rimosso dalla settimana.")
    return redirect('dashboard_docente')


@staff_member_required
def elimina_chiusura(request, chiusura_id):
    chiusura = get_object_or_404(GiornoChiusura, id=chiusura_id)
    chiusura.delete()
    messages.success(request, "Riapertura effettuata (chiusura cancellata).")
    return redirect('dashboard_docente')


@staff_member_required
def gestisci_lezione(request, lezione_id, azione):
    lezione = get_object_or_404(Lezione, id=lezione_id)

    if azione == 'accetta':
        lezione.stato = 'CONFERMATA'
        lezione.save()

        if lezione.studente.email:
            invia_email_custom(
                soggetto='✅ Lezione Confermata',
                destinatari=[lezione.studente.email],
                template_name='conferma_lezione.html',
                context={
                    'lezione': lezione,
                    'link_calendar': lezione.get_google_calendar_url()
                }
            )
        messages.success(request, "Lezione confermata e mail inviata!")

    elif azione == 'rifiuta':
        lezione.stato = 'RIFIUTATA'
        lezione.save()

        if lezione.studente.email:
            invia_email_custom(
                soggetto='❌ Aggiornamento Lezione',
                destinatari=[lezione.studente.email],
                template_name='rifiuto_lezione.html',
                context={'lezione': lezione}
            )
        messages.warning(request, "Lezione rifiutata.")

    elif azione == 'pagata':
        # Questo gestisce il pagamento di una SINGOLA lezione (dal calendario)
        lezione.pagata = True
        lezione.save()
        messages.success(request, "Pagamento registrato.")

    return redirect('dashboard_docente')


@staff_member_required
def export_lezioni_csv(request):
    data_dal = request.GET.get('dal')
    data_al = request.GET.get('al')

    response = HttpResponse(content_type='text/csv')
    filename = "lezioni_export"
    if data_dal: filename += f"_dal_{data_dal}"
    if data_al: filename += f"_al_{data_al}"
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Data', 'Ora', 'Studente', 'Durata', 'Prezzo', 'Stato', 'Pagata', 'Note'])

    lezioni = Lezione.objects.filter(stato='CONFERMATA')

    if data_dal:
        lezioni = lezioni.filter(data_inizio__date__gte=data_dal)
    if data_al:
        lezioni = lezioni.filter(data_inizio__date__lte=data_al)

    lezioni = lezioni.order_by('-data_inizio')

    for lezione in lezioni:
        writer.writerow([
            lezione.data_inizio.strftime("%d/%m/%Y"),
            lezione.data_inizio.strftime("%H:%M"),
            f"{lezione.studente.first_name} {lezione.studente.last_name}",
            str(lezione.durata_ore).replace('.', ','),
            f"{lezione.prezzo}".replace('.', ','),
            lezione.get_stato_display(),
            "SI" if lezione.pagata else "NO",
            lezione.note or ""
        ])

    return response


# --- NUOVA FUNZIONE PER I PAGAMENTI RAGGRUPPATI ---
@staff_member_required
def gestione_pagamenti(request, studente_id, azione):
    studente = get_object_or_404(User, id=studente_id)

    # Recuperiamo tutte le lezioni CONFERMATE ma NON PAGATE di questo studente
    lezioni_da_pagare = Lezione.objects.filter(
        studente=studente,
        stato='CONFERMATA',
        pagata=False
    ).order_by('data_inizio')

    if not lezioni_da_pagare:
        messages.warning(request, f"Nessuna lezione da pagare per {studente.first_name}.")
        return redirect('dashboard_docente')

    # Calcolo il totale
    totale = lezioni_da_pagare.aggregate(Sum('prezzo'))['prezzo__sum'] or 0

    if azione == 'invia_riepilogo':
        if studente.email:
            invia_email_custom(
                soggetto=f'Riepilogo Lezioni da Saldare - {studente.first_name}',
                destinatari=[studente.email],
                template_name='riepilogo_pagamenti.html',  # Assicurati di creare questo file
                context={
                    'lezioni': lezioni_da_pagare,
                    'totale': totale,
                    'studente': studente
                }
            )
            messages.success(request, f"Riepilogo inviato a {studente.email} con totale € {totale}!")
        else:
            messages.error(request, "Lo studente non ha un'email salvata.")

    elif azione == 'segna_pagato':
        # Aggiorna tutte le lezioni in una volta sola
        numero_lezioni = lezioni_da_pagare.update(pagata=True)
        messages.success(request,
                         f"Segnate come pagate {numero_lezioni} lezioni per {studente.first_name}. Incasso di € {totale} registrato!")

    return redirect('dashboard_docente')