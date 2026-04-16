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


# shipping/views.py
from django.http import JsonResponse

def shipment_status_api(request, awb_code):
    shipment = get_object_or_404(Shipment, awb_code=awb_code)

    events = list(
        ShipmentEvent.objects.filter(shipment=shipment)
        .order_by('created_at')
        .values('status', 'description', 'created_at')
    )

    return JsonResponse({
        'status': shipment.status,
        'events': events
    })

def agent_location_api(request, awb_code):
    shipment = get_object_or_404(Shipment, awb_code=awb_code)

    agent = shipment.agent

    return JsonResponse({
        'lat': agent.latitude if agent else None,
        'lng': agent.longitude if agent else None
    })