from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings

# IMPORTA IL NUOVO FORM DI REGISTRAZIONE
from .forms import PrenotazioneForm, RegistrazioneForm
from .models import Lezione


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