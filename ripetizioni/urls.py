from django.contrib import admin
from django.urls import path, include
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth: Login/Logout standard di Django + Register custom
    path('accounts/', include('django.contrib.auth.urls')),
    path('register/', views.registrazione, name='register'),

    # Area Studente
    path('', views.dashboard, name='dashboard'),
    path('prenota/', views.prenota, name='prenota'),
    path('profilo/', views.profilo_view, name='profilo'),

    # API interne (usate da HTMX nel form prenotazione)
    path('htmx/get-orari/', views.get_orari_disponibili, name='get_orari'),

    # Area Docente
    path('dashboard-docente/', views.dashboard_docente, name='dashboard_docente'),

    # Action URLs (Logic only, redirect immediato)
    path('gestisci-lezione/<int:lezione_id>/<str:azione>/', views.gestisci_lezione, name='gestisci_lezione'),
    path('elimina-chiusura/<int:chiusura_id>/', views.elimina_chiusura, name='elimina_chiusura'),
    path('elimina-disponibilita/<int:disp_id>/', views.elimina_disponibilita, name='elimina_disponibilita'),
    path('gestione-pagamenti/<int:studente_id>/<str:azione>/', views.gestione_pagamenti, name='gestione_pagamenti'),
]