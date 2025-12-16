from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Lezione, Disponibilita, Profilo, GiornoChiusura, Impostazioni
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
            # HTMX: quando cambi la data, ricarico la select delle ore
            'hx-get': '/htmx/get-orari/',
            'hx-target': '#id_ora',
            'hx-trigger': 'change',
            'hx-indicator': '#loading-spinner'
        }),
        label="Giorno Desiderato"
    )

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
        # Fix per Django: se non popolo le choices nel POST, la validazione fallisce
        # perché il valore scelto non esiste nella lista vuota iniziale.
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

            # 1. Controllo se quel giorno della settimana lavoro
            giorno_sett = inizio_richiesto.weekday()
            try:
                disp = Disponibilita.objects.get(giorno=giorno_sett)
            except Disponibilita.DoesNotExist:
                raise forms.ValidationError("In questo giorno non faccio lezione (controlla Admin).")

            # 2. Controllo range orario (es. non sforare dopo le 20:00)
            ora_inizio_disp = timezone.make_aware(datetime.datetime.combine(data_scelta, disp.ora_inizio))
            ora_fine_disp = timezone.make_aware(datetime.datetime.combine(data_scelta, disp.ora_fine))

            fine_richiesta = inizio_richiesto + timedelta(hours=float(durata))

            if inizio_richiesto < ora_inizio_disp or fine_richiesta > ora_fine_disp:
                raise forms.ValidationError(f"Orario fuori disponibilità ({disp.ora_inizio} - {disp.ora_fine})")

            # 3. Controllo incroci (Overlap)
            # Cerco lezioni che finiscono DOPO il mio inizio e iniziano PRIMA della mia fine
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


class ChiusuraForm(forms.ModelForm):
    class Meta:
        model = GiornoChiusura
        fields = ['data_inizio', 'data_fine', 'motivo']
        widgets = {
            'data_inizio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_fine': forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'placeholder': 'Opzionale'}),
            'motivo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Es. Ferie'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        inizio = cleaned_data.get("data_inizio")
        fine = cleaned_data.get("data_fine")

        if fine and fine < inizio:
            self.add_error('data_fine', "La data fine non può essere prima dell'inizio!")


class DisponibilitaForm(forms.ModelForm):
    class Meta:
        model = Disponibilita
        fields = ['giorno', 'ora_inizio', 'ora_fine']
        widgets = {
            'giorno': forms.Select(attrs={'class': 'form-select'}),
            'ora_inizio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'ora_fine': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }


class ImpostazioniForm(forms.ModelForm):
    class Meta:
        model = Impostazioni
        fields = ['tariffa_base']
        widgets = {
            'tariffa_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50'}),
        }