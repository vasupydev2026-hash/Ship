# shipping/urls.py

from django.urls import path
from .views import track_shipment,shipment_status_api,agent_location_api

urlpatterns = [
    path('track/<str:awb_code>/', track_shipment, name='track_shipment'),
    path('api/track/<str:awb_code>/', shipment_status_api),
    path('api/location/<str:awb_code>/', agent_location_api),

]