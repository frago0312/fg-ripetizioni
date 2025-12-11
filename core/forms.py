from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Lezione
import datetime
from django.utils import timezone
from datetime import timedelta

# --- 1. CONFIGURAZIONE DISPONIBILITÀ (0=Lun, 6=Dom) ---
ORARI_SETTIMANALI = {
    0: ['14:30', '15:00', '15:30', '16:00', '16:30', '17:00', '17:30', '18:00', '18:30', '19:00'],
    1: ['09:00', '09:30', '10:00', '10:30', '11:00', '11:30', '14:00', '14:30', '15:00', '15:30'],
    2: ['14:30', '15:00', '15:30', '16:00', '16:30', '17:00', '17:30', '18:00', '18:30'],
    3: ['14:30', '15:00', '15:30', '16:00', '16:30', '17:00', '17:30', '18:00', '18:30'],
    4: ['14:30', '15:00', '15:30', '16:00', '16:30', '17:00', '17:30', '18:00'],
}

TUTTI_ORARI = sorted(list(set([ora for lista in ORARI_SETTIMANALI.values() for ora in lista])))
SCELTE_ORARI = [(ora, ora) for ora in TUTTI_ORARI]


# --- 2. NUOVO FORM REGISTRAZIONE (CON EMAIL OBBLIGATORIA) ---
class RegistrazioneForm(UserCreationForm):
    # Sovrascriviamo i campi per renderli obbligatori e tradotti in italiano
    email = forms.EmailField(required=True, label="Indirizzo Email")
    first_name = forms.CharField(required=True, label="Nome")
    last_name = forms.CharField(required=True, label="Cognome")

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']


# --- 3. FORM PRENOTAZIONE (CON LOGICA ORARI) ---
class PrenotazioneForm(forms.ModelForm):
    data = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Giorno Desiderato"
    )
    ora = forms.ChoiceField(
        choices=SCELTE_ORARI,
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

    def clean(self):
        cleaned_data = super().clean()
        data_scelta = cleaned_data.get("data")
        ora_scelta = cleaned_data.get("ora")
        durata = cleaned_data.get("durata_ore")

        if data_scelta and ora_scelta and durata:
            orario_str = f"{data_scelta} {ora_scelta}"
            inizio_richiesto = datetime.datetime.strptime(orario_str, "%Y-%m-%d %H:%M")
            inizio_richiesto = timezone.make_aware(inizio_richiesto)
            fine_richiesta = inizio_richiesto + timedelta(hours=float(durata))

            if inizio_richiesto < timezone.now():
                raise forms.ValidationError("Non puoi prenotare nel passato!")

            weekday = inizio_richiesto.weekday()

            if weekday not in ORARI_SETTIMANALI:
                raise forms.ValidationError("In questo giorno non faccio lezione.")

            if ora_scelta not in ORARI_SETTIMANALI[weekday]:
                raise forms.ValidationError(f"Alle {ora_scelta} non sono disponibile. Controlla gli orari.")

            conflitti = Lezione.objects.filter(
                stato__in=['RICHIESTA', 'CONFERMATA'],
                data_inizio__lt=fine_richiesta,
            )

            for lezione in conflitti:
                fine_lezione = lezione.data_inizio + timedelta(hours=float(lezione.durata_ore))
                if inizio_richiesto < fine_lezione and fine_richiesta > lezione.data_inizio:
                    raise forms.ValidationError(
                        f"Orario occupato ({lezione.data_inizio.strftime('%H:%M')} - {fine_lezione.strftime('%H:%M')}).")

            cleaned_data['data_inizio_calcolata'] = inizio_richiesto

        return cleaned_data

    def save(self, commit=True):
        lezione = super().save(commit=False)
        lezione.data_inizio = self.cleaned_data['data_inizio_calcolata']
        if commit:
            lezione.save()
        return lezione