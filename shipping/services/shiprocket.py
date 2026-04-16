# shipping/services/shiprocket.py

import requests
from django.conf import settings
from django.core.cache import cache

BASE_URL = settings.SHIPROCKET_BASE_URL

def get_token():
    res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": settings.SHIPROCKET_EMAIL,
        "password": settings.SHIPROCKET_PASSWORD
    })

    data = res.json()
    print("SHIPROCKET LOGIN RESPONSE:", data)

    if "token" not in data:
        raise Exception(f"Shiprocket login failed: {data}")

    return data["token"]


def create_shipment(order):
    token = get_token()

    payload = {
        "order_id": str(order.id),
        "order_date": str(order.created_at),
        "pickup_location": "Primary",
        "billing_customer_name": order.user.first_name,
        "billing_address": order.address,
        "billing_pincode": order.pincode,
        "billing_city": order.city,
        "billing_state": order.state,
        "billing_country": "India",
        "billing_phone": order.phone,
        "order_items": [
            {
                "name": item.product.name,
                "sku": item.product.id,
                "units": item.quantity,
                "selling_price": str(item.price)
            } for item in order.items.all()
        ],
        "payment_method": "Prepaid",
        "sub_total": str(order.total)
    }

    headers = {"Authorization": f"Bearer {token}"}

    return requests.post(
        f"{BASE_URL}/orders/create/adhoc",
        json=payload,
        headers=headers
    ).json()


# from shipping.tasks import process_shipping
#
# def create_shipping(self, request, queryset):
#     for order in queryset:
#         print("ADMIN ACTION HIT:", order.id)   # DEBUG
#         process_shipping.delay(order.id)
#
#     self.message_user(request, "🚚 Shipping process started!")