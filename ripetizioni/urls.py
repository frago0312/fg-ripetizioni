from django.contrib import admin
from django.urls import path, include
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth standard di Django + registrazione custom
    path('accounts/', include('django.contrib.auth.urls')),
    path('register/', views.registrazione, name='register'),

    # Pagina pubblica
    path('', views.landing, name='landing'),

    # Area Studente
    path('dashboard/', views.dashboard, name='dashboard'),
    path('prenota/', views.prenota, name='prenota'),
    path('profilo/', views.profilo_view, name='profilo'),
    path('cancella-lezione/<int:lezione_id>/', views.cancella_lezione, name='cancella_lezione'),

    # Endpoint HTMX (GET, non mutanti)
    path('htmx/get-orari/', views.get_orari_disponibili, name='get_orari'),
    path('htmx/anteprima-prezzo/', views.anteprima_prezzo, name='anteprima_prezzo'),

    # Area Docente
    path('dashboard-docente/', views.dashboard_docente, name='dashboard_docente'),
    path('export-storico/', views.export_storico_csv, name='export_storico'),

    # Action URL (POST-only, verificato con @require_POST in views)
    path('gestisci-lezione/<int:lezione_id>/<str:azione>/', views.gestisci_lezione, name='gestisci_lezione'),
    path('elimina-chiusura/<int:chiusura_id>/', views.elimina_chiusura, name='elimina_chiusura'),
    path('elimina-disponibilita/<int:disp_id>/', views.elimina_disponibilita, name='elimina_disponibilita'),
    path('gestione-pagamenti/<int:studente_id>/<str:azione>/', views.gestione_pagamenti, name='gestione_pagamenti'),
]