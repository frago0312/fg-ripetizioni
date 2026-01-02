from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
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
def dashboard_docente(request):
    config_obj = Impostazioni.objects.first()

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

    return render(request, 'core/dashboard_docente.html', {
        'richieste': richieste,
        'future': future,
        'guadagno': guadagno,
        'form_chiusura': form_chiusura,
        'chiusure_future': chiusure_future,
        'form_disp': form_disp,
        'disponibilita_list': disponibilita_list,
        'form_tariffa': form_tariffa,
    })


@staff_member_required
def elimina_disponibilita(request, disp_id):
    disp = Disponibilita.objects.get(id=disp_id)
    disp.delete()
    messages.success(request, "Orario rimosso dalla settimana.")
    return redirect('dashboard_docente')


@staff_member_required
def elimina_chiusura(request, chiusura_id):
    chiusura = GiornoChiusura.objects.get(id=chiusura_id)
    chiusura.delete()
    messages.success(request, "Riapertura effettuata (chiusura cancellata).")
    return redirect('dashboard_docente')


@staff_member_required
def gestisci_lezione(request, lezione_id, azione):
    lezione = Lezione.objects.get(id=lezione_id)

    if azione == 'accetta':
        lezione.stato = 'CONFERMATA'
        lezione.save()

        # ORA È MOLTO PIÙ PULITO:
        # Richiamo il metodo del modello invece di calcolare il link qui
        if lezione.studente.email:
            invia_email_custom(
                soggetto='✅ Lezione Confermata',
                destinatari=[lezione.studente.email],
                template_name='conferma_lezione.html',
                context={
                    'lezione': lezione,
                    'link_calendar': lezione.get_google_calendar_url() # Metodo nuovo
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