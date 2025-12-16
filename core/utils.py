from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def invia_email_custom(soggetto, destinatari, template_name, context):
    """
    Wrapper per inviare mail HTML + Plain Text in modo pulito.
    """
    html_content = render_to_string(f'emails/{template_name}', context)
    text_content = strip_tags(html_content) # La versione testuale è fondamentale per non finire nello spam

    msg = EmailMultiAlternatives(
        subject=soggetto,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        # Comodità: accetto sia una lista ['a@b.it'] che una stringa singola 'a@b.it'
        to=destinatari if isinstance(destinatari, list) else [destinatari]
    )

    msg.attach_alternative(html_content, "text/html")

    # Se l'SMTP ha problemi temporanei, meglio fallire silenziosamente che mostrare Error 500 all'utente
    msg.send(fail_silently=True)