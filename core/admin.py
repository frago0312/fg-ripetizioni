from django.contrib import admin
from django.core.mail import send_mail
from django.conf import settings
from .models import Lezione


@admin.register(Lezione)
class LezioneAdmin(admin.ModelAdmin):
    list_display = ('studente', 'data_inizio', 'luogo', 'prezzo', 'stato', 'pagata')
    list_filter = ('stato', 'pagata', 'data_inizio')
    list_editable = ('stato', 'pagata')

    def save_model(self, request, obj, form, change):
        if change:
            old_obj = Lezione.objects.get(pk=obj.pk)

            # SE CONFERMI
            if old_obj.stato != 'CONFERMATA' and obj.stato == 'CONFERMATA':
                if obj.studente.email:
                    send_mail(
                        '✅ Lezione Confermata - FG Ripetizioni',
                        f'Ciao {obj.studente.first_name}, lezione confermata!\n\nData: {obj.data_inizio.strftime("%d/%m ore %H:%M")}\nLuogo: {obj.get_luogo_display()}\nImporto: € {obj.prezzo:.2f}\n\nA presto!',
                        settings.DEFAULT_FROM_EMAIL,
                        [obj.studente.email],
                        fail_silently=True
                    )

            # SE RIFIUTI
            if old_obj.stato != 'RIFIUTATA' and obj.stato == 'RIFIUTATA':
                if obj.studente.email:
                    send_mail(
                        '❌ Lezione Rifiutata - FG Ripetizioni',
                        f'Ciao {obj.studente.first_name}, non riesco per la lezione del {obj.data_inizio.strftime("%d/%m ore %H:%M")}.\n\nScrivimi per concordare un altro orario!',
                        settings.DEFAULT_FROM_EMAIL,
                        [obj.studente.email],
                        fail_silently=True
                    )

        super().save_model(request, obj, form, change)