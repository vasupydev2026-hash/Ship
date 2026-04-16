# shipping/urls.py

from django.urls import path
from .views import track_shipment

urlpatterns = [
    path('track/<str:awb_code>/', track_shipment, name='track_shipment'),
]