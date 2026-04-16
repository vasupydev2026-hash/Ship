from celery import shared_task
from .services.shiprocket import create_order, generate_awb, generate_label, request_pickup
from .models import Order


@shared_task
def process_shiprocket_order(order_id):
    try:
        order = Order.objects.get(id=order_id)

        print("🚀 Creating Shiprocket order...")

        res = create_order(order)

        if not res.get("shipment_id"):
            print("❌ Shiprocket order failed:", res)
            return

        order.shiprocket_shipment_id = res.get("shipment_id")
        order.shiprocket_order_id = res.get("order_id")
        order.shipment_status = "created"
        order.save()

        # ---------------- AWB ----------------
        awb = generate_awb(
            shipment_id=res["shipment_id"],
            courier_id=res.get("courier_company_id", 1)
        )

        order.awb_code = awb.get("awb_code")
        order.shipment_status = "awb_generated"
        order.save()

        # ---------------- LABEL ----------------
        generate_label(res["shipment_id"])

        # ---------------- PICKUP ----------------
        request_pickup(res["shipment_id"])

        order.shipment_status = "pickup_requested"
        order.save()

        print("🚀 Shiprocket FULL PIPELINE COMPLETED")

    except Exception as e:
        print("❌ Shiprocket Pipeline Error:", str(e))