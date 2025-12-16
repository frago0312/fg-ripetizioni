from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver

class Impostazioni(models.Model):
    tariffa_base = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, help_text="Prezzo all'ora base")

    def __str__(self):
        return f"Configurazione (Tariffa: {self.tariffa_base}€)"

    class Meta:
        verbose_name_plural = "Impostazioni"

class GiornoChiusura(models.Model):
    data_inizio = models.DateField(help_text="Primo giorno di chiusura")
    data_fine = models.DateField(help_text="Ultimo giorno di chiusura", blank=True, null=True)
    motivo = models.CharField(max_length=100, blank=True, help_text="Es. Vacanze Estive")

    def save(self, *args, **kwargs):
        # UX: Se l'utente lascia vuota la fine, assumo sia una chiusura di un solo giorno
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
    LUOGO_SCELTE = [
        ('BASE', '🏠 Online / Casa Mia (Tariffa Base)'),
        ('RUFINA', '🚶 Rufina Paese (+2€)'),
        ('FASCIA_15', '🚗 Entro 15 min - Montebonello/Scopeti/Pomino (+4€)'),
        ('FASCIA_30', '🚗 Entro 30 min - Pontassieve/Sieci/Dicomano/Londa (+8€)'),
        ('ALTRO', '❓ Altro (Contattami)'),
    ]

    studente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lezioni')
    data_inizio = models.DateTimeField(help_text="Giorno e ora inizio")
    durata_ore = models.DecimalField(max_digits=3, decimal_places=1, default=1.0, help_text="Durata in ore (es. 1.5 per un'ora e mezza)")
    luogo = models.CharField(max_length=20, choices=LUOGO_SCELTE, default='BASE')

    STATO_SCELTE = [
        ('RICHIESTA', 'In attesa di conferma'),
        ('CONFERMATA', 'Confermata'),
        ('RIFIUTATA', 'Rifiutata'),
    ]
    stato = models.CharField(max_length=20, choices=STATO_SCELTE, default='RICHIESTA')

    prezzo = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    pagata = models.BooleanField(default=False)
    note = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        # Snapshot del prezzo: calcolo il costo solo alla creazione (o se manca).
        # In questo modo, se alzo la tariffa in futuro, le vecchie lezioni restano invariate.
        if self.pk is None or self.prezzo is None:
            config = Impostazioni.objects.first()
            tariffa_base_db = config.tariffa_base if config else Decimal(10.00)

            extra = 0
            if self.luogo == 'RUFINA':
                extra = 2.00
            elif self.luogo == 'FASCIA_15':
                extra = 4.00
            elif self.luogo == 'FASCIA_30':
                extra = 8.00

            costo_ore = tariffa_base_db * Decimal(self.durata_ore)
            self.prezzo = costo_ore + Decimal(extra)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.studente.username} - {self.data_inizio.strftime('%d/%m %H:%M')}"

    class Meta:
        verbose_name_plural = "Lezioni"
        ordering = ['-data_inizio']

class Disponibilita(models.Model):
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
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profilo')
    telefono = models.CharField(max_length=20, blank=True, null=True, help_text="Utile per urgenze (WhatsApp)")
    indirizzo = models.CharField(max_length=255, blank=True, null=True, help_text="Indirizzo completo (se vengo io da te)")
    scuola = models.CharField(max_length=100, blank=True, null=True, help_text="Es. Liceo Scientifico, 4° Anno")

    def __str__(self):
        return f"Profilo di {self.user.username}"

    class Meta:
        verbose_name_plural = "Profili"

# Garanzia di consistenza: ogni User DEVE avere un Profilo.
# Lo creo automaticamente sia al signup che in caso di salvataggi da admin/shell.
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profilo.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    try:
        instance.profilo.save()
    except Profilo.DoesNotExist:
        Profilo.objects.create(user=instance)