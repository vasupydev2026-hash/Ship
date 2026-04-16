# shipping/models.py

from django.db import models
from orders.models import Order

class Shipment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)

    shiprocket_order_id = models.CharField(max_length=100, null=True)
    shipment_id = models.CharField(max_length=100, null=True)

    courier_name = models.CharField(max_length=100, null=True)
    courier_id = models.IntegerField(null=True)

    awb_code = models.CharField(max_length=100, null=True)
    tracking_url = models.URLField(null=True)

    status = models.CharField(max_length=50, default="created")

    created_at = models.DateTimeField(auto_now_add=True)



# shipping/models.py

class ShipmentEvent(models.Model):
    shipment = models.ForeignKey("Shipment", on_delete=models.CASCADE)
    status = models.CharField(max_length=50)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.shipment.order} - {self.status}"