# shipping/tasks.py

import random
from celery import shared_task
from django.utils import timezone
from orders.models import Order
from shipping.models import Shipment, ShipmentEvent


# =========================================================
# 📌 Helper: Add tracking event
# =========================================================
def add_event(shipment, status, description):
    ShipmentEvent.objects.create(
        shipment=shipment,
        status=status,
        description=description
    )


# =========================================================
# 🚚 CREATE SHIPMENT (MAIN TASK)
# =========================================================
# shipping/tasks.py
from celery import shared_task
import time

@shared_task
def process_shipping(shipment_id):
    shipment = Shipment.objects.get(id=shipment_id)

    steps = [
        ("assigned", "Order assigned to courier"),
        ("shipped", "Package shipped"),
        ("out_for_delivery", "Out for delivery"),
        ("delivered", "Package delivered"),
    ]

    for status, desc in steps:
        time.sleep(10)  # simulate delay

        shipment.status = status
        shipment.save()

        ShipmentEvent.objects.create(
            shipment=shipment,
            status=status,
            description=desc
        )
# =========================================================
# 📦 STEP 1 → ASSIGNED
# =========================================================
@shared_task
def update_to_assigned(shipment_id):
    shipment = Shipment.objects.get(id=shipment_id)

    shipment.status = "assigned"
    shipment.save()

    add_event(shipment, "assigned", "Courier assigned")

    print("📦 Assigned")

    # Next step
    update_to_shipped.apply_async((shipment.id,), countdown=5)


# =========================================================
# 🚚 STEP 2 → SHIPPED
# =========================================================
@shared_task
def update_to_shipped(shipment_id):
    shipment = Shipment.objects.get(id=shipment_id)

    shipment.status = "shipped"
    shipment.save()

    add_event(shipment, "shipped", "Package shipped")

    print("🚚 Shipped")

    # Next step
    update_to_delivered.apply_async((shipment.id,), countdown=5)


# =========================================================
# ✅ STEP 3 → DELIVERED
# =========================================================
@shared_task
def update_to_delivered(shipment_id):
    shipment = Shipment.objects.get(id=shipment_id)

    shipment.status = "delivered"
    shipment.save()

    add_event(shipment, "delivered", "Package delivered")

    print("✅ Delivered")