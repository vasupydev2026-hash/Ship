from django.shortcuts import render, get_object_or_404
from .models import Shipment, ShipmentEvent

def track_shipment(request, awb_code):  # ✅ MUST accept awb_code
    shipment = get_object_or_404(Shipment, awb_code=awb_code)

    events = ShipmentEvent.objects.filter(
        shipment=shipment
    ).order_by('created_at')

    return render(request, 'shipping/track.html', {
        'shipment': shipment,
        'events': events
    })