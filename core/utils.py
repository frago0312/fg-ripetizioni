from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


def invia_email_custom(soggetto, destinatari, template_name, context):
    """
    Funzione centralizzata per inviare email HTML + Text.
    """
    # 1. Renderizza l'HTML usando i dati (context)
    html_content = render_to_string(f'emails/{template_name}', context)

    # 2. Crea la versione solo testo (rimuovendo i tag HTML)
    text_content = strip_tags(html_content)

    # 3. Prepara il messaggio
    msg = EmailMultiAlternatives(
        subject=soggetto,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinatari if isinstance(destinatari, list) else [destinatari]
    )

    # 4. Allega la versione HTML
    msg.attach_alternative(html_content, "text/html")

    # 5. Invia
    msg.send(fail_silently=True)