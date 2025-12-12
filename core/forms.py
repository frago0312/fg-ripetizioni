from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Lezione, Disponibilita, Profilo
import datetime
from django.utils import timezone
from datetime import timedelta


class RegistrazioneForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Indirizzo Email")
    first_name = forms.CharField(required=True, label="Nome")
    last_name = forms.CharField(required=True, label="Cognome")

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']


class PrenotazioneForm(forms.ModelForm):
    data = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            # QUI STA LA MAGIA HTMX:
            'hx-get': '/htmx/get-orari/',
            'hx-target': '#id_ora',
            'hx-trigger': 'change'
        }),
        label="Giorno Desiderato"
    )

    # Inizialmente vuoto, verrà riempito da HTMX o dalla validazione
    ora = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Orario Inizio"
    )

    class Meta:
        model = Lezione
        fields = ['durata_ore', 'luogo', 'note']
        widgets = {
            'durata_ore': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0.5', 'max': '4'}),
            'luogo': forms.Select(attrs={'class': 'form-select'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Se c'è un input (POST), dobbiamo popolare le scelte dell'ora
        # altrimenti Django dice "Scelta non valida"
        if 'data' in self.data and 'ora' in self.data:
            self.fields['ora'].choices = [(self.data['ora'], self.data['ora'])]

    def clean(self):
        cleaned_data = super().clean()
        data_scelta = cleaned_data.get("data")
        ora_scelta = cleaned_data.get("ora")
        durata = cleaned_data.get("durata_ore")

        if data_scelta and ora_scelta and durata:
            orario_str = f"{data_scelta} {ora_scelta}"
            inizio_richiesto = datetime.datetime.strptime(orario_str, "%Y-%m-%d %H:%M")
            inizio_richiesto = timezone.make_aware(inizio_richiesto)

            # Validazione: Controlla se il giorno è disponibile nel DB
            giorno_sett = inizio_richiesto.weekday()
            try:
                disp = Disponibilita.objects.get(giorno=giorno_sett)
            except Disponibilita.DoesNotExist:
                raise forms.ValidationError("In questo giorno non faccio lezione (controlla Admin).")

            # Controllo range orario
            ora_inizio_disp = datetime.datetime.combine(data_scelta, disp.ora_inizio)
            ora_fine_disp = datetime.datetime.combine(data_scelta, disp.ora_fine)

            # Rendiamo offset-aware per il confronto
            ora_inizio_disp = timezone.make_aware(ora_inizio_disp)
            ora_fine_disp = timezone.make_aware(ora_fine_disp)

            fine_richiesta = inizio_richiesto + timedelta(hours=float(durata))

            if inizio_richiesto < ora_inizio_disp or fine_richiesta > ora_fine_disp:
                raise forms.ValidationError(f"Orario fuori disponibilità ({disp.ora_inizio} - {disp.ora_fine})")

            # Controllo sovrapposizioni
            conflitti = Lezione.objects.filter(
                stato__in=['RICHIESTA', 'CONFERMATA'],
                data_inizio__lt=fine_richiesta,
            )

            for lezione in conflitti:
                fine_lezione = lezione.data_inizio + timedelta(hours=float(lezione.durata_ore))
                if inizio_richiesto < fine_lezione and fine_richiesta > lezione.data_inizio:
                    raise forms.ValidationError(
                        f"Orario occupato da un'altra lezione ({lezione.data_inizio.strftime('%H:%M')}).")

            cleaned_data['data_inizio_calcolata'] = inizio_richiesto

        return cleaned_data

    def save(self, commit=True):
        lezione = super().save(commit=False)
        lezione.data_inizio = self.cleaned_data['data_inizio_calcolata']
        if commit:
            lezione.save()
        return lezione


class ProfiloForm(forms.ModelForm):
    class Meta:
        model = Profilo
        fields = ['telefono', 'indirizzo', 'scuola']
        widgets = {
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+39 ...'}),
            'indirizzo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Via Roma 1, Firenze'}),
            'scuola': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Scuola e Classe'}),
        }