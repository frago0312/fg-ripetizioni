from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.http import urlencode
from datetime import timedelta
from django.utils import timezone


class Impostazioni(models.Model):
    """Configurazione globale dell'app (tariffa base oraria)."""
    tariffa_base = models.DecimalField(max_digits=5, decimal_places=2, default=10.00,
                                       help_text="Prezzo all'ora base")

    def __str__(self):
        return f"Configurazione (Tariffa: {self.tariffa_base}€)"

    class Meta:
        verbose_name_plural = "Impostazioni"


class GiornoChiusura(models.Model):
    """Periodo di chiusura in cui non si accettano prenotazioni."""
    data_inizio = models.DateField(help_text="Primo giorno di chiusura")
    data_fine = models.DateField(help_text="Ultimo giorno di chiusura", blank=True, null=True)
    motivo = models.CharField(max_length=100, blank=True, help_text="Es. Vacanze Estive")

    def save(self, *args, **kwargs):
        if not self.data_fine:
            self.data_fine = self.data_inizio
        super().save(*args, **kwargs)

    def __str__(self):
        if self.data_inizio == self.data_fine:
            return f"{self.data_inizio.strftime('%d/%m')} - {self.motivo}"
        return f"{self.data_inizio.strftime('%d/%m')} al {self.data_fine.strftime('%d/%m')} - {self.motivo}"

    class Meta:
        verbose_name_plural = "Giorni di Chiusura"
        ordering = ['-data_inizio']


class Lezione(models.Model):
    """Una singola sessione di ripetizioni, con prezzo calcolato automaticamente."""

    LUOGO_SCELTE = [
        ('BASE', '🏠 Online / Casa Mia (Tariffa Base)'),
        ('RUFINA', '🚶 Rufina Paese (+2€)'),
        ('FASCIA_15', '🚗 Entro 15 min - Montebonello/Scopeti/Pomino (+4€)'),
        ('FASCIA_30', '🚗 Entro 30 min - Pontassieve/Sieci/Dicomano/Londa (+8€)'),
        ('ALTRO', '❓ Altro (Contattami)'),
    ]

    STATO_SCELTE = [
        ('RICHIESTA', 'In attesa di conferma'),
        ('CONFERMATA', 'Confermata'),
        ('RIFIUTATA', 'Rifiutata'),
        ('CANCELLATA', 'Cancellata dallo studente'),
    ]

    EXTRA_PER_LUOGO = {
        'RUFINA': Decimal('2.00'),
        'FASCIA_15': Decimal('4.00'),
        'FASCIA_30': Decimal('8.00'),
    }

    studente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lezioni')
    data_inizio = models.DateTimeField(help_text="Giorno e ora inizio")
    durata_ore = models.DecimalField(max_digits=3, decimal_places=1, default=1.0,
                                     help_text="Durata in ore (minimo 1h, poi ogni 0.5h)")
    luogo = models.CharField(max_length=20, choices=LUOGO_SCELTE, default='BASE')
    stato = models.CharField(max_length=20, choices=STATO_SCELTE, default='RICHIESTA')
    materia = models.CharField(max_length=100, blank=True, null=True,
                               help_text="Es. Matematica, Fisica (anche più di una)")
    prezzo = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    pagata = models.BooleanField(default=False)
    note = models.TextField(blank=True, null=True)

    @property
    def data_fine(self):
        """Calcola e ritorna l'orario di fine lezione."""
        return self.data_inizio + timedelta(hours=float(self.durata_ore))

    def _calcola_prezzo(self):
        """Calcola il prezzo in base alla tariffa dello studente (o globale) e al luogo."""
        try:
            tariffa_base = self.studente.profilo.tariffa_specifica or None
        except AttributeError:
            tariffa_base = None

        if tariffa_base is None:
            config = Impostazioni.objects.first()
            tariffa_base = config.tariffa_base if config else Decimal('10.00')

        extra = self.EXTRA_PER_LUOGO.get(self.luogo, Decimal('0'))
        return tariffa_base * Decimal(str(self.durata_ore)) + extra

    def save(self, *args, **kwargs):
        if self.pk is None or self.prezzo is None:
            self.prezzo = self._calcola_prezzo()
        super().save(*args, **kwargs)

    def get_google_calendar_url(self):
        """Genera il link per aggiungere la lezione a Google Calendar."""
        inizio_locale = timezone.localtime(self.data_inizio)
        fine_locale = timezone.localtime(self.data_fine)
        fmt = "%Y%m%dT%H%M%S"
        params = {
            'action': 'TEMPLATE',
            'text': f"Ripetizioni FG: {self.studente.first_name} {self.studente.last_name}",
            'dates': f"{inizio_locale.strftime(fmt)}/{fine_locale.strftime(fmt)}",
            'details': f"Note: {self.note or 'Nessuna nota'}",
            'location': self.get_luogo_display(),
            'sprop': 'website:https://francescogori03.eu.pythonanywhere.com',
            'ctz': 'Europe/Rome',
        }
        return f"https://calendar.google.com/calendar/render?{urlencode(params)}"

    def __str__(self):
        return f"{self.studente.username} - {self.data_inizio.strftime('%d/%m %H:%M')}"

    class Meta:
        verbose_name_plural = "Lezioni"
        ordering = ['-data_inizio']


class Disponibilita(models.Model):
    """Fascia oraria disponibile per un dato giorno della settimana."""

    GIORNI = [
        (0, 'Lunedì'), (1, 'Martedì'), (2, 'Mercoledì'),
        (3, 'Giovedì'), (4, 'Venerdì'), (5, 'Sabato'), (6, 'Domenica')
    ]
    giorno = models.IntegerField(choices=GIORNI, unique=True)
    ora_inizio = models.TimeField(help_text="Ora di inizio disponibilità (es. 14:30)")
    ora_fine = models.TimeField(help_text="Ora di fine disponibilità (es. 19:00)")

    def __str__(self):
        return f"{self.get_giorno_display()} ({self.ora_inizio.strftime('%H:%M')} - {self.ora_fine.strftime('%H:%M')})"

    class Meta:
        verbose_name_plural = "Disponibilità"
        ordering = ['giorno']


class Profilo(models.Model):
    """Dati aggiuntivi associati a ogni utente (telefono, scuola, tariffa personalizzata)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profilo')
    telefono = models.CharField(max_length=20, blank=True, null=True,
                                help_text="Utile per urgenze (WhatsApp)")
    indirizzo = models.CharField(max_length=255, blank=True, null=True,
                                 help_text="Indirizzo completo (se vengo io da te)")
    scuola = models.CharField(max_length=100, blank=True, null=True,
                              help_text="Es. Liceo Scientifico, 4° Anno")
    tariffa_specifica = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        help_text="Se impostata, questa tariffa vince su quella globale."
    )

    def __str__(self):
        return f"Profilo di {self.user.username}"

    class Meta:
        verbose_name_plural = "Profili"


@receiver(post_save, sender=User)
def crea_o_salva_profilo(sender, instance, created, **kwargs):
    """Assicura che ogni User abbia sempre un Profilo associato."""
    if created:
        Profilo.objects.create(user=instance)
    else:
        try:
            instance.profilo.save()
        except Profilo.DoesNotExist:
            Profilo.objects.create(user=instance)