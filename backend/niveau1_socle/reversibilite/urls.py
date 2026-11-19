from django.urls import path

from .vues import TelechargerExport

urlpatterns = [path("<str:jeton>/", TelechargerExport.as_view())]
