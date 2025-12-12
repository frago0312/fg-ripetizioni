from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse
from datetime import datetime, timedelta, time
from django.utils import timezone

# IMPORTA IL NUOVO FORM DI REGISTRAZIONE
from .forms import PrenotazioneForm, RegistrazioneForm, ProfiloForm
from .models import Lezione, Disponibilita, Profilo


@login_required
def dashboard(request):
    lezioni = Lezione.objects.filter(studente=request.user).order_by('-data_inizio')
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

            # --- MAIL AL PROF (TE) ---
            try:
                soggetto = f"Nuova Lezione: {request.user.username}"
                messaggio = f"""
                Ciao Francesco!
                Nuova richiesta da: {request.user.first_name} {request.user.last_name} ({request.user.username})

                Data: {lezione.data_inizio.strftime('%d/%m/%Y %H:%M')}
                Durata: {lezione.durata_ore}h
                Zona: {lezione.get_luogo_display()}
                Note: {lezione.note}

                Accetta qui: https://francescogori03.eu.pythonanywhere.com/admin/
                """
                send_mail(soggetto, messaggio, settings.DEFAULT_FROM_EMAIL, [settings.EMAIL_HOST_USER],
                          fail_silently=True)
            except:
                pass  # Non blocchiamo se la mail fallisce

            messages.success(request, 'Richiesta inviata! Riceverai una mail di conferma.')
            return redirect('dashboard')
    else:
        form = PrenotazioneForm()

    return render(request, 'core/prenota.html', {'form': form})


def registrazione(request):
    if request.method == 'POST':
        # USIAMO IL NOSTRO FORM NUOVO
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

    giorno_settimana = data_scelta.weekday()

    # 1. Cerchiamo la tua disponibilità per quel giorno nel DB
    try:
        disp = Disponibilita.objects.get(giorno=giorno_settimana)
    except Disponibilita.DoesNotExist:
        return HttpResponse("<option value=''>Nessuna lezione in questo giorno</option>")

    # 2. Generiamo gli slot di 30 minuti
    orari_possibili = []
    ora_corrente = datetime.combine(data_scelta, disp.ora_inizio)
    ora_fine = datetime.combine(data_scelta, disp.ora_fine)

    while ora_corrente < ora_fine:
        orari_possibili.append(ora_corrente)
        ora_corrente += timedelta(minutes=30)

    # 3. Filtriamo quelli occupati
    # Troviamo le lezioni confermate o in richiesta per quel giorno
    lezioni_giorno = Lezione.objects.filter(
        data_inizio__date=data_scelta,
        stato__in=['RICHIESTA', 'CONFERMATA']
    )

    orari_liberi = []
    for orario in orari_possibili:
        occupato = False
        # Rendiamo l'orario timezone-aware per il confronto
        inizio_slot = timezone.make_aware(orario)
        fine_slot = inizio_slot + timedelta(hours=1.0)  # Supponiamo durata minima 1h per il check, ma affiniamo sotto

        for lezione in lezioni_giorno:
            # Calcoliamo inizio e fine della lezione esistente
            lezione_inizio = lezione.data_inizio
            # Se la lezione non ha durata, assumiamo 1h per sicurezza
            durata = float(lezione.durata_ore) if lezione.durata_ore else 1.0
            lezione_fine = lezione_inizio + timedelta(hours=durata)

            # Controllo sovrapposizione:
            # Uno slot è occupato se inizia PRIMA che l'altra finisca E finisce DOPO che l'altra inizi
            # Qui controlliamo solo l'inizio dello slot per semplicità
            if lezione_inizio <= inizio_slot < lezione_fine:
                occupato = True
                break

        if not occupato:
            # Formattiamo l'orario per l'HTML (HH:MM)
            str_orario = orario.strftime("%H:%M")
            orari_liberi.append(f"<option value='{str_orario}'>{str_orario}</option>")

    if not orari_liberi:
        return HttpResponse("<option value=''>Tutto occupato!</option>")

    return HttpResponse("".join(orari_liberi))


@login_required
def profilo_view(request):
    # Gestiamo il caso in cui un vecchio utente non abbia ancora il profilo
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