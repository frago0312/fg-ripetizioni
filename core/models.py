from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


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
    # Ora accettiamo 1.5 (un'ora e mezza)
    durata_ore = models.DecimalField(max_digits=3, decimal_places=1, default=1.0,
                                     help_text="Durata in ore (es. 1.5 per un'ora e mezza)")
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
        TARIFFA_BASE = 10.00

        extra = 0
        if self.luogo == 'RUFINA':
            extra = 2.00
        elif self.luogo == 'FASCIA_15':
            extra = 4.00
        elif self.luogo == 'FASCIA_30':
            extra = 8.00
        elif self.luogo == 'ALTRO':
            extra = 0

        # Converto in Decimal per fare calcoli precisi con le mezze ore
        costo_ore = Decimal(TARIFFA_BASE) * Decimal(self.durata_ore)
        self.prezzo = costo_ore + Decimal(extra)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.studente.username} - {self.data_inizio.strftime('%d/%m %H:%M')}"

    class Meta:
        verbose_name_plural = "Lezioni"
        ordering = ['-data_inizio']