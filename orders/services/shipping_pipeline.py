from django.db import transaction
from .shiprocket import (
    create_order,
    generate_awb,
    generate_label,
    request_pickup,
    check_serviceability
)


def process_shipping(order):
    """
    FULL AUTOMATION PIPELINE (PRODUCTION LEVEL)
    """

    print("🚀 PIPELINE STARTED")

    # 1. Create Shiprocket Order
    ship = create_order(order)

    shipment_id = ship.get("shipment_id")
    order.shiprocket_shipment_id = shipment_id
    order.shiprocket_order_id = ship.get("order_id")
    order.save()

    print("📦 Shipment Created:", shipment_id)

    # 2. Auto courier selection (basic logic)
    try:
        service = check_serviceability(order.address.pincode)

        courier_list = service.get("data", {}).get("available_courier_companies", [])

        if courier_list:
            best = min(courier_list, key=lambda x: x.get("rate", 999999))
            courier_id = best.get("courier_company_id")
            order.courier_name = best.get("courier_name")
            order.save()

            # 3. AWB generate
            awb = generate_awb(shipment_id, courier_id)
            print("📦 AWB:", awb)

            if awb.get("awb_code"):
                order.awb_code = awb["awb_code"]

    except Exception as e:
        print("⚠ Courier/AWB issue:", str(e))

    # 4. Label
    try:
        label = generate_label(shipment_id)
        print("📄 Label Generated")
    except:
        pass

    # 5. Pickup request
    try:
        pickup = request_pickup(shipment_id)
        print("🚚 Pickup Requested")
    except:
        pass

    order.save()

    return ship