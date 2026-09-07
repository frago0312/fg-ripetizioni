from django import template

register = template.Library()


@register.filter
def durata_fmt(valore):
    """Converte ore decimali in formato leggibile: 1.5 → '1h 30min'."""
    try:
        ore = float(valore)
    except (TypeError, ValueError):
        return valore
    h = int(ore)
    m = int(round((ore - h) * 60))
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}min"


@register.filter
def phone_wa(numero):
    """Formatta un numero di telefono per un link WhatsApp (rimuove spazi e +)."""
    if not numero:
        return ''
    return numero.replace(' ', '').replace('+', '')
