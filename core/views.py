import csv
import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    PrenotazioneForm, RegistrazioneForm, ProfiloForm,
    ChiusuraForm, DisponibilitaForm, ImpostazioniForm
)
from .models import Lezione, Disponibilita, Profilo, GiornoChiusura, Impostazioni
from .utils import invia_email_custom

logger = logging.getLogger(__name__)

LIMITE_CANCELLAZIONE_ORE = 48


def _parse_data_filtro(valore):
    """Converte una stringa 'YYYY-MM-DD' in date, o None se assente/non valida."""
    if not valore:
        return None
    try:
        return datetime.strptime(valore, "%Y-%m-%d").date()
    except ValueError:
        return None


def landing(request):
    """Pagina pubblica di presentazione del servizio."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def registrazione(request):
    """Registrazione nuovo studente. Invia email di benvenuto al completamento."""
    if request.method == 'POST':
        form = RegistrazioneForm(request.POST)
        if form.is_valid():
            user = form.save()
            try:
                invia_email_custom(
                    soggetto='Benvenuto in FG Ripetizioni!',
                    destinatari=[user.email],
                    template_name='benvenuto.html',
                    context={'user': user}
                )
            except Exception:
                logger.exception("Errore invio email di benvenuto a %s", user.email)
            messages.success(request, 'Account creato! Ora puoi accedere.')
            return redirect('login')
    else:
        form = RegistrazioneForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def dashboard(request):
    """Dashboard studente: mostra lezioni, saldo da pagare e prossima lezione."""
    lezioni = Lezione.objects.filter(studente=request.user).select_related('studente__profilo')

    da_pagare = lezioni.filter(stato='CONFERMATA', pagata=False).aggregate(Sum('prezzo'))['prezzo__sum'] or 0
    prossima = lezioni.filter(stato='CONFERMATA', data_inizio__gte=timezone.now()).order_by('data_inizio').first()

    return render(request, 'core/dashboard.html', {
        'lezioni': lezioni,
        'da_pagare': da_pagare,
        'prossima': prossima,
        'ora_limite_cancellazione': timezone.now() + timedelta(hours=LIMITE_CANCELLAZIONE_ORE),
    })


@login_required
def prenota(request):
    """Form di prenotazione lezione per lo studente."""
    if request.method == 'POST':
        form = PrenotazioneForm(request.POST)
        if form.is_valid():
            inizio = form.cleaned_data['data_inizio_calcolata']
            fine = inizio + timedelta(hours=float(form.cleaned_data['durata_ore']))

            with transaction.atomic():
                # Riverifica (lockando le righe del giorno) che nessun altro abbia
                # prenotato lo stesso slot nel frattempo, per chiudere la finestra di
                # race condition tra la validazione del form e il salvataggio.
                conflitti = Lezione.objects.select_for_update().filter(
                    stato__in=['RICHIESTA', 'CONFERMATA'],
                    data_inizio__date=inizio.date(),
                    data_inizio__lt=fine,
                )
                occupato = any(
                    inizio < (l.data_inizio + timedelta(hours=float(l.durata_ore))) and fine > l.data_inizio
                    for l in conflitti
                )
                if occupato:
                    messages.error(request, "Spiacente, questo orario è stato appena prenotato da un altro utente. Scegline un altro.")
                    return redirect('prenota')

                lezione = form.save(commit=False)
                lezione.studente = request.user
                lezione.save()
            try:
                invia_email_custom(
                    soggetto=f"Nuova Richiesta: {request.user.get_full_name() or request.user.username}",
                    destinatari=[settings.EMAIL_HOST_USER],
                    template_name='nuova_richiesta.html',
                    context={'lezione': lezione}
                )
            except Exception:
                logger.exception("Errore invio email nuova richiesta per lezione %s", lezione.pk)
            messages.success(request, 'Richiesta inviata! Riceverai una mail di conferma.')
            return redirect('dashboard')
    else:
        form = PrenotazioneForm()
    return render(request, 'core/prenota.html', {'form': form, 'oggi': timezone.now().date()})


@login_required
def cancella_lezione(request, lezione_id):
    """Permette allo studente di cancellare la propria lezione se mancano più di 48h all'inizio."""
    lezione = get_object_or_404(Lezione, id=lezione_id, studente=request.user)

    if lezione.stato not in ['RICHIESTA', 'CONFERMATA']:
        messages.error(request, "Questa lezione non può essere cancellata.")
        return redirect('dashboard')

    ore_mancanti = (lezione.data_inizio - timezone.now()).total_seconds() / 3600
    if ore_mancanti < LIMITE_CANCELLAZIONE_ORE:
        messages.error(request, f"Non puoi cancellare una lezione a meno di {LIMITE_CANCELLAZIONE_ORE}h dall'inizio.")
        return redirect('dashboard')

    lezione.stato = 'CANCELLATA'
    lezione.save()

    try:
        invia_email_custom(
            soggetto=f"Lezione Cancellata: {request.user.get_full_name() or request.user.username}",
            destinatari=[settings.EMAIL_HOST_USER],
            template_name='cancellazione_lezione.html',
            context={'lezione': lezione}
        )
    except Exception:
        logger.exception("Errore invio email cancellazione per lezione %s", lezione.pk)

    messages.success(request, "Lezione cancellata con successo.")
    return redirect('dashboard')


@login_required
def profilo_view(request):
    """Visualizza e aggiorna i dati del profilo studente."""
    profilo, _ = Profilo.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProfiloForm(request.POST, instance=profilo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dati aggiornati con successo!')
            return redirect('dashboard')
    else:
        form = ProfiloForm(instance=profilo)

    stats = Lezione.objects.filter(studente=request.user, stato='CONFERMATA').aggregate(
        totale_ore=Sum('durata_ore'),
        totale_pagato=Sum('prezzo', filter=Q(pagata=True))
    )

    return render(request, 'core/profilo.html', {
        'form': form,
        'stats': stats,
        'num_lezioni': Lezione.objects.filter(studente=request.user, stato='CONFERMATA').count(),
    })


@login_required
def get_orari_disponibili(request):
    """Endpoint HTMX: restituisce gli slot orari liberi per una data, ogni 15 minuti."""
    data_str = request.GET.get('data')
    if not data_str:
        return HttpResponse("<option value=''>Seleziona prima una data</option>")

    try:
        data_scelta = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponse("<option value=''>Data non valida</option>")

    if data_scelta < timezone.now().date():
        return HttpResponse("<option value=''>Data nel passato</option>")

    chiusura = GiornoChiusura.objects.filter(
        data_inizio__lte=data_scelta,
        data_fine__gte=data_scelta
    ).first()

    if chiusura:
        return HttpResponse(f"<option value=''>Non disponibile: {chiusura.motivo or 'Chiuso'}</option>")

    try:
        disp = Disponibilita.objects.get(giorno=data_scelta.weekday())
    except Disponibilita.DoesNotExist:
        return HttpResponse("<option value=''>Nessuna lezione in questo giorno</option>")

    orari_possibili = []
    ora_corrente = datetime.combine(data_scelta, disp.ora_inizio)
    ora_fine = datetime.combine(data_scelta, disp.ora_fine)

    while ora_corrente < ora_fine:
        orari_possibili.append(ora_corrente)
        ora_corrente += timedelta(minutes=15)

    lezioni_giorno = list(Lezione.objects.filter(
        data_inizio__date=data_scelta,
        stato__in=['RICHIESTA', 'CONFERMATA']
    ))

    orari_liberi = []
    for orario in orari_possibili:
        inizio_slot = timezone.make_aware(orario)
        occupato = any(
            lezione.data_inizio <= inizio_slot < lezione.data_fine
            for lezione in lezioni_giorno
        )
        if not occupato:
            str_orario = orario.strftime("%H:%M")
            orari_liberi.append(f"<option value='{str_orario}'>{str_orario}</option>")

    if not orari_liberi:
        return HttpResponse("<option value=''>Tutto occupato!</option>")

    return HttpResponse("".join(orari_liberi))


@login_required
def anteprima_prezzo(request):
    """Endpoint HTMX: calcola e restituisce il prezzo stimato per luogo e durata scelti."""
    from decimal import Decimal

    luogo = request.GET.get('luogo', 'BASE')
    try:
        durata = Decimal(request.GET.get('durata_ore', '1.0'))
    except Exception:
        durata = Decimal('1.0')

    tariffa_specifica = request.user.profilo.tariffa_specifica
    if tariffa_specifica is not None:
        tariffa_base = tariffa_specifica
    else:
        config = Impostazioni.objects.first()
        tariffa_base = config.tariffa_base if config else Decimal('10.00')

    extra = Lezione.EXTRA_PER_LUOGO.get(luogo, Decimal('0'))
    prezzo = tariffa_base * durata + extra

    return HttpResponse(
        f'<span class="badge badge-attesa">'
        f'Prezzo stimato: <strong>€ {prezzo:.2f}</strong></span>'
    )


@staff_member_required
def dashboard_docente(request):
    """Dashboard docente: panoramica richieste, lezioni, pagamenti e configurazione."""
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

    richieste = Lezione.objects.filter(stato='RICHIESTA').select_related('studente__profilo').order_by('data_inizio')
    future = Lezione.objects.filter(stato='CONFERMATA', data_inizio__gte=oggi).select_related('studente__profilo').order_by('data_inizio')

    inizio_mese = oggi.date().replace(day=1)
    guadagno = Lezione.objects.filter(stato='CONFERMATA', data_inizio__gte=inizio_mese, pagata=True).aggregate(Sum('prezzo'))['prezzo__sum'] or 0

    chiusure_future = GiornoChiusura.objects.filter(data_fine__gte=oggi.date()).order_by('data_inizio')
    disponibilita_list = Disponibilita.objects.all()

    from django.db.models import Count
    lista_pagamenti_qs = (
        Lezione.objects.filter(stato='CONFERMATA', pagata=False)
        .values('studente__id', 'studente__username', 'studente__first_name', 'studente__last_name', 'studente__email')
        .annotate(numero_lezioni=Count('id'), totale=Sum('prezzo'))
        .order_by('studente__first_name')
    )

    filtro_studente = request.GET.get('studente')
    filtro_dal = request.GET.get('dal')
    filtro_al = request.GET.get('al')
    data_dal = _parse_data_filtro(filtro_dal)
    data_al = _parse_data_filtro(filtro_al)
    if filtro_dal and not data_dal:
        messages.warning(request, "Data 'dal' non valida, filtro ignorato.")
    if filtro_al and not data_al:
        messages.warning(request, "Data 'al' non valida, filtro ignorato.")

    passate = Lezione.objects.filter(stato='CONFERMATA', data_inizio__lt=oggi).select_related('studente').order_by('-data_inizio')
    if filtro_studente:
        passate = passate.filter(studente_id=filtro_studente)
    if data_dal:
        passate = passate.filter(data_inizio__date__gte=data_dal)
    if data_al:
        passate = passate.filter(data_inizio__date__lte=data_al)

    totale_ore_passate = passate.aggregate(Sum('durata_ore'))['durata_ore__sum'] or 0
    totale_importo_passate = passate.aggregate(Sum('prezzo'))['prezzo__sum'] or 0

    studenti_con_lezioni = User.objects.filter(
        lezioni__stato='CONFERMATA', lezioni__data_inizio__lt=oggi
    ).distinct().order_by('first_name')

    return render(request, 'core/dashboard_docente.html', {
        'richieste': richieste,
        'future': future,
        'guadagno': guadagno,
        'form_chiusura': form_chiusura,
        'chiusure_future': chiusure_future,
        'form_disp': form_disp,
        'disponibilita_list': disponibilita_list,
        'form_tariffa': form_tariffa,
        'lista_pagamenti': lista_pagamenti_qs,
        'passate': passate,
        'totale_ore_passate': totale_ore_passate,
        'totale_importo_passate': totale_importo_passate,
        'studenti_con_lezioni': studenti_con_lezioni,
        'filtro_studente': filtro_studente,
        'filtro_dal': filtro_dal,
        'filtro_al': filtro_al,
        'num_richieste': richieste.count(),
    })


@staff_member_required
@require_POST
def elimina_disponibilita(request, disp_id):
    """Elimina una fascia di disponibilità settimanale."""
    disp = get_object_or_404(Disponibilita, id=disp_id)
    disp.delete()
    messages.success(request, "Orario rimosso dalla settimana.")
    return redirect('dashboard_docente')


@staff_member_required
@require_POST
def elimina_chiusura(request, chiusura_id):
    """Elimina un periodo di chiusura."""
    chiusura = get_object_or_404(GiornoChiusura, id=chiusura_id)
    chiusura.delete()
    messages.success(request, "Chiusura cancellata.")
    return redirect('dashboard_docente')


@staff_member_required
@require_POST
def gestisci_lezione(request, lezione_id, azione):
    """Accetta, rifiuta o segna come pagata una lezione (solo docente)."""
    lezione = get_object_or_404(Lezione, id=lezione_id)

    if azione in ('accetta', 'rifiuta') and lezione.stato != 'RICHIESTA':
        messages.error(request, "Questa lezione non è più in attesa di conferma.")
        return redirect('dashboard_docente')

    if azione == 'accetta':
        lezione.stato = 'CONFERMATA'
        lezione.save()
        if lezione.studente.email:
            try:
                invia_email_custom(
                    soggetto='✅ Lezione Confermata',
                    destinatari=[lezione.studente.email],
                    template_name='conferma_lezione.html',
                    context={'lezione': lezione, 'link_calendar': lezione.get_google_calendar_url()}
                )
            except Exception:
                logger.exception("Errore invio email conferma lezione %s", lezione.pk)
                messages.warning(request, "Lezione confermata, ma l'email non è stata inviata.")
        messages.success(request, "Lezione confermata e mail inviata!")

    elif azione == 'rifiuta':
        lezione.stato = 'RIFIUTATA'
        lezione.save()
        if lezione.studente.email:
            try:
                invia_email_custom(
                    soggetto='❌ Aggiornamento Lezione',
                    destinatari=[lezione.studente.email],
                    template_name='rifiuto_lezione.html',
                    context={'lezione': lezione}
                )
            except Exception:
                logger.exception("Errore invio email rifiuto lezione %s", lezione.pk)
                messages.warning(request, "Lezione rifiutata, ma l'email non è stata inviata.")
        messages.warning(request, "Lezione rifiutata.")

    elif azione == 'pagata':
        lezione.pagata = True
        lezione.save()
        messages.success(request, "Pagamento registrato.")

    return redirect('dashboard_docente')


@staff_member_required
@require_POST
def gestione_pagamenti(request, studente_id, azione):
    """Invia riepilogo pagamenti via email o segna tutte le lezioni di uno studente come pagate."""
    studente = get_object_or_404(User, id=studente_id)
    lezioni_da_pagare = Lezione.objects.filter(studente=studente, stato='CONFERMATA', pagata=False).order_by('data_inizio')

    if not lezioni_da_pagare.exists():
        messages.warning(request, f"Nessuna lezione da pagare per {studente.first_name}.")
        return redirect('dashboard_docente')

    totale = lezioni_da_pagare.aggregate(Sum('prezzo'))['prezzo__sum'] or 0

    if azione == 'invia_riepilogo':
        if studente.email:
            try:
                invia_email_custom(
                    soggetto=f'Riepilogo Lezioni da Saldare - {studente.first_name}',
                    destinatari=[studente.email],
                    template_name='riepilogo_pagamenti.html',
                    context={'lezioni': lezioni_da_pagare, 'totale': totale, 'studente': studente}
                )
                messages.success(request, f"Riepilogo inviato a {studente.email} (€ {totale}).")
            except Exception:
                logger.exception("Errore invio riepilogo pagamenti a %s", studente.email)
                messages.error(request, "Errore durante l'invio dell'email.")
        else:
            messages.error(request, "Lo studente non ha un'email salvata.")

    elif azione == 'segna_pagato':
        numero = lezioni_da_pagare.update(pagata=True)
        messages.success(request, f"Segnate {numero} lezioni pagate per {studente.first_name} (€ {totale}).")

    return redirect('dashboard_docente')


@staff_member_required
def export_storico_csv(request):
    """Esporta lo storico lezioni filtrato in formato CSV."""
    oggi = timezone.now()
    passate = Lezione.objects.filter(stato='CONFERMATA', data_inizio__lt=oggi).select_related('studente').order_by('-data_inizio')

    if request.GET.get('studente'):
        passate = passate.filter(studente_id=request.GET['studente'])
    data_dal = _parse_data_filtro(request.GET.get('dal'))
    data_al = _parse_data_filtro(request.GET.get('al'))
    if data_dal:
        passate = passate.filter(data_inizio__date__gte=data_dal)
    if data_al:
        passate = passate.filter(data_inizio__date__lte=data_al)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="storico_lezioni.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['Data', 'Studente', 'Materia', 'Durata (h)', 'Importo (€)', 'Pagata'])
    for lezione in passate:
        writer.writerow([
            lezione.data_inizio.strftime('%d/%m/%Y %H:%M'),
            lezione.studente.get_full_name() or lezione.studente.username,
            lezione.materia or '—',
            lezione.durata_ore,
            f"{lezione.prezzo:.2f}",
            'Sì' if lezione.pagata else 'No',
        ])

    return response
