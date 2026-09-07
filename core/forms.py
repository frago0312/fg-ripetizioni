from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Lezione, Disponibilita, Profilo, GiornoChiusura, Impostazioni
import datetime
from django.utils import timezone
from datetime import timedelta


class RegistrazioneForm(UserCreationForm):
    """Form di registrazione con email, nome e cognome obbligatori."""
    email = forms.EmailField(required=True, label="Indirizzo Email")
    first_name = forms.CharField(required=True, label="Nome")
    last_name = forms.CharField(required=True, label="Cognome")

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class PrenotazioneForm(forms.ModelForm):
    """Form per prenotare una lezione. Gli slot orari vengono caricati via HTMX dopo la scelta della data."""

    data = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'hx-get': '/htmx/get-orari/',
            'hx-target': '#id_ora',
            'hx-trigger': 'change',
            'hx-indicator': '#loading-spinner',
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
        fields = ['durata_ore', 'luogo', 'materia', 'note']
        widgets = {
            'durata_ore': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': '1.0',
                'max': '6.0',
                'hx-get': '/htmx/anteprima-prezzo/',
                'hx-target': '#anteprima-prezzo',
                'hx-include': '[name="luogo"]',
                'hx-trigger': 'change',
            }),
            'luogo': forms.Select(attrs={
                'class': 'form-select',
                'hx-get': '/htmx/anteprima-prezzo/',
                'hx-target': '#anteprima-prezzo',
                'hx-include': '[name="durata_ore"]',
                'hx-trigger': 'change',
            }),
            'materia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Es. Matematica, Fisica',
            }),
            'note': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Argomenti specifici o informazioni utili...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'data' in self.data and 'ora' in self.data:
            self.fields['ora'].choices = [(self.data['ora'], self.data['ora'])]

    def clean(self):
        cleaned_data = super().clean()
        data_scelta = cleaned_data.get("data")
        ora_scelta = cleaned_data.get("ora")
        durata = cleaned_data.get("durata_ore")

        if data_scelta and ora_scelta and durata:
            if float(durata) < 1.0:
                raise forms.ValidationError("La durata minima è 1 ora.")

            inizio_richiesto = datetime.datetime.strptime(f"{data_scelta} {ora_scelta}", "%Y-%m-%d %H:%M")
            inizio_richiesto = timezone.make_aware(inizio_richiesto)

            if inizio_richiesto < timezone.now():
                raise forms.ValidationError("Non puoi prenotare una lezione nel passato.")

            giorno_sett = inizio_richiesto.weekday()
            try:
                disp = Disponibilita.objects.get(giorno=giorno_sett)
            except Disponibilita.DoesNotExist:
                raise forms.ValidationError("In questo giorno non faccio lezione.")

            ora_inizio_disp = timezone.make_aware(datetime.datetime.combine(data_scelta, disp.ora_inizio))
            ora_fine_disp = timezone.make_aware(datetime.datetime.combine(data_scelta, disp.ora_fine))
            fine_richiesta = inizio_richiesto + timedelta(hours=float(durata))

            if inizio_richiesto < ora_inizio_disp or fine_richiesta > ora_fine_disp:
                raise forms.ValidationError(
                    f"Orario fuori dalla mia disponibilità ({disp.ora_inizio.strftime('%H:%M')} - {disp.ora_fine.strftime('%H:%M')})"
                )

            conflitti = Lezione.objects.filter(
                stato__in=['RICHIESTA', 'CONFERMATA'],
                data_inizio__lt=fine_richiesta,
            ).exclude(pk=self.instance.pk if self.instance else None)

            for lezione in conflitti:
                fine_lezione = lezione.data_inizio + timedelta(hours=float(lezione.durata_ore))
                if inizio_richiesto < fine_lezione and fine_richiesta > lezione.data_inizio:
                    raise forms.ValidationError(
                        f"Orario già occupato da un'altra lezione ({lezione.data_inizio.strftime('%H:%M')})."
                    )

            cleaned_data['data_inizio_calcolata'] = inizio_richiesto

        return cleaned_data

    def save(self, commit=True):
        lezione = super().save(commit=False)
        lezione.data_inizio = self.cleaned_data['data_inizio_calcolata']
        if commit:
            lezione.save()
        return lezione


class ProfiloForm(forms.ModelForm):
    """Form per aggiornare i dati del profilo studente."""
    class Meta:
        model = Profilo
        fields = ['telefono', 'indirizzo', 'scuola']
        widgets = {
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+39 ...'}),
            'indirizzo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Via Roma 1, Firenze'}),
            'scuola': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Scuola e Classe'}),
        }


class ChiusuraForm(forms.ModelForm):
    """Form per aggiungere un periodo di chiusura (ferie, festività)."""
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
            self.add_error('data_fine', "La data fine non può essere prima dell'inizio.")
        return cleaned_data


class DisponibilitaForm(forms.ModelForm):
    """Form per impostare la disponibilità oraria di un giorno della settimana."""
    class Meta:
        model = Disponibilita
        fields = ['giorno', 'ora_inizio', 'ora_fine']
        widgets = {
            'giorno': forms.Select(attrs={'class': 'form-select'}),
            'ora_inizio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'ora_fine': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }


class ImpostazioniForm(forms.ModelForm):
    """Form per modificare la tariffa oraria base globale."""
    class Meta:
        model = Impostazioni
        fields = ['tariffa_base']
        widgets = {
            'tariffa_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.50'}),
        }
