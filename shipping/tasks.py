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
@shared_task(bind=True, max_retries=3)
def process_shipping(self, order_id):
    print("🔥 TASK STARTED:", order_id)

    try:
        order = Order.objects.get(id=order_id)

        # ✅ Prevent duplicate shipments
        shipment, created = Shipment.objects.get_or_create(order=order)

        if created:
            print(f"✅ New shipment created for Order {order.id}")
        else:
            print(f"🔁 Updating existing shipment for Order {order.id}")

        shipment.shipment_id = f"MOCK-SHIP-{order.id}"
        shipment.awb_code = f"AWB{order.id}"
        shipment.status = "created"
        # ✅ Assign stable mock data
        shipment.courier_name = random.choice([
            "Delhivery", "BlueDart", "XpressBees"
        ])
        shipment.courier_id = random.randint(1000, 9999)

        # ✅ IMPORTANT: Stable AWB (no random for production logic)

        # ❌ Do NOT store full URL (generate dynamically in admin/view)

        shipment.save()

        print(f"✅ Shipment created for Order {order.id}")

        # ✅ Add first event
        add_event(shipment, "created", "Order placed")

        # ✅ Trigger async status updates (no sleep here)
        update_to_assigned.apply_async((shipment.id,), countdown=5)

    except Order.DoesNotExist:
        print(f"❌ Order {order_id} not found")
    except Exception as e:
        print("❌ ERROR:", str(e))
        raise self.retry(exc=e, countdown=5)


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