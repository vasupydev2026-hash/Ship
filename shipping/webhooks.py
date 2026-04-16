# shipping/webhooks.py

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from .models import Shipment


@csrf_exempt
def shiprocket_webhook(request):
    data = json.loads(request.body)

    awb = data.get("awb")
    status = data.get("current_status")

    shipment = Shipment.objects.filter(awb_code=awb).first()

    if shipment:
        shipment.status = status
        shipment.save()

    return JsonResponse({"status": "ok"})