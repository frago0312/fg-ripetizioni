from django.contrib import admin
from django.core.mail import send_mail
from django.conf import settings
from .models import Lezione, Disponibilita, Profilo

# 1. Gestione Disponibilità (Orari)
@admin.register(Disponibilita)
class DisponibilitaAdmin(admin.ModelAdmin):
    list_display = ('get_giorno_display', 'ora_inizio', 'ora_fine')
    ordering = ('giorno', 'ora_inizio')

# 2. Gestione Profilo Studente (NUOVO)
# Ti permette di vedere telefono e scuola direttamente dall'Admin
@admin.register(Profilo)
class ProfiloAdmin(admin.ModelAdmin):
    list_display = ('user', 'telefono', 'scuola')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'telefono')

# 3. Gestione Lezioni (con invio Mail)
@admin.register(Lezione)
class LezioneAdmin(admin.ModelAdmin):
    list_display = ('studente', 'data_inizio', 'luogo', 'prezzo', 'stato', 'pagata')
    list_filter = ('stato', 'pagata', 'data_inizio')
    list_editable = ('stato', 'pagata')
    search_fields = ('studente__username', 'studente__first_name', 'studente__last_name')

    def save_model(self, request, obj, form, change):
        if change:
            try:
                old_obj = Lezione.objects.get(pk=obj.pk)
            except Lezione.DoesNotExist:
                old_obj = None

            if old_obj:
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