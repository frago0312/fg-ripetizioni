from django.contrib import admin
from django.conf import settings
from .models import Lezione, Disponibilita, Profilo, GiornoChiusura, Impostazioni
from .utils import invia_email_custom


@admin.register(Impostazioni)
class ImpostazioniAdmin(admin.ModelAdmin):
    list_display = ('tariffa_base',)


@admin.register(Disponibilita)
class DisponibilitaAdmin(admin.ModelAdmin):
    list_display = ('get_giorno_display', 'ora_inizio', 'ora_fine')
    ordering = ('giorno', 'ora_inizio')


@admin.register(Profilo)
class ProfiloAdmin(admin.ModelAdmin):
    list_display = ('user', 'telefono', 'scuola')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'telefono')


@admin.register(GiornoChiusura)
class GiornoChiusuraAdmin(admin.ModelAdmin):
    list_display = ('data_inizio', 'data_fine', 'motivo')
    ordering = ('-data_inizio',)


@admin.register(Lezione)
class LezioneAdmin(admin.ModelAdmin):
    list_display = ('id', 'studente', 'data_inizio', 'luogo', 'prezzo', 'stato', 'pagata')

    list_display_links = ('id', 'data_inizio')

    list_filter = ('stato', 'pagata', 'data_inizio')

    list_editable = ('studente', 'stato', 'pagata')

    search_fields = ('studente__username', 'studente__first_name', 'studente__last_name')

    def save_model(self, request, obj, form, change):
        if change:
            # Recupero l'istanza vecchia per confrontare lo stato (Old vs New)
            try:
                old_obj = Lezione.objects.get(pk=obj.pk)
            except Lezione.DoesNotExist:
                old_obj = None

            if old_obj and obj.studente.email:

                # Check cambio stato -> CONFERMATA
                if old_obj.stato != 'CONFERMATA' and obj.stato == 'CONFERMATA':
                    invia_email_custom(
                        soggetto='✅ Lezione Confermata - FG Ripetizioni',
                        destinatari=[obj.studente.email],
                        template_name='conferma_lezione.html',
                        # Link calendar vuoto perché generarlo qui è superfluo
                        context={'lezione': obj, 'link_calendar': ''}
                    )

                # Check cambio stato -> RIFIUTATA
                elif old_obj.stato != 'RIFIUTATA' and obj.stato == 'RIFIUTATA':
                    invia_email_custom(
                        soggetto='❌ Lezione Rifiutata - FG Ripetizioni',
                        destinatari=[obj.studente.email],
                        template_name='rifiuto_lezione.html',
                        context={'lezione': obj}
                    )

        super().save_model(request, obj, form, change)