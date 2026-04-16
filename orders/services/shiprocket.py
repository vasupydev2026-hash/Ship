import requests
from django.conf import settings
from django.core.cache import cache
from orders.models import OrderItem

BASE_URL = settings.SHIPROCKET_BASE_URL


# ---------------------------
# 1. AUTH TOKEN (CACHED)
# ---------------------------
from django.core.cache import cache
import requests
from django.conf import settings

BASE_URL = settings.SHIPROCKET_BASE_URL


def get_shiprocket_token(force_refresh=False):
    if not force_refresh:
        token = cache.get("shiprocket_token")
        if token:
            return token

    # 🔐 Generate new token
    url = f"{BASE_URL}/auth/login"

    payload = {
        "email": settings.SHIPROCKET_EMAIL,
        "password": settings.SHIPROCKET_PASSWORD
    }

    res = requests.post(url, json=payload)
    data = res.json()

    print("🔐 Shiprocket Auth:", data)

    if "token" not in data:
        raise Exception(f"Shiprocket Auth Failed: {data}")

    token = data["token"]

    # Cache for 23 hours
    cache.set("shiprocket_token", token, timeout=60 * 60 * 23)

    return token
# ---------------------------
# 2. CREATE ORDER (FIXED)
# ---------------------------
def create_order(order):
    token = get_shiprocket_token()

    url = f"{BASE_URL}/orders/create/adhoc"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    address = order.address
    user = order.user

    # ---------------- NAME SAFE SPLIT ----------------
    name = address.fullname or "User"
    name_parts = name.split()

    first_name = name_parts[0]
    last_name = name_parts[-1] if len(name_parts) > 1 else "NA"

    # ---------------- ORDER ITEMS ----------------
    items = OrderItem.objects.filter(order=order)

    order_items = [
        {
            "name": i.product.name,
            "sku": f"SKU-{i.product.id}",
            "units": i.quantity,
            "selling_price": float(i.price)
        }
        for i in items
    ]

    # ---------------- BASE PAYLOAD ----------------
    payload = {
        "order_id": str(order.order_code),
        "order_date": order.created_at.strftime("%Y-%m-%d %H:%M"),
        "pickup_location": "Primary",

        # ---------------- BILLING ----------------
        "billing_customer_name": first_name,
        "billing_last_name": last_name,
        "billing_address": address.address1,
        "billing_address_2": address.address2 or "",
        "billing_city": address.city,
        "billing_pincode": str(address.pincode),
        "billing_state": address.state,
        "billing_country": address.country,
        "billing_email": user.email,
        "billing_phone": str(address.mobile)[-10:],

        # ---------------- SHIPPING ----------------
        "shipping_is_billing": True,

        # ---------------- ITEMS ----------------
        "order_items": order_items,

        # ---------------- IMPORTANT FIX ----------------
        "sub_total": float(order.total_amount),

        # ---------------- DIMENSIONS (MANDATORY) ----------------
        "length": 10,
        "breadth": 10,
        "height": 10,
        "weight": 0.5,
    }

    # ---------------- PAYMENT LOGIC ----------------
    if order.payment_method.lower() == "cod":
        payload["payment_method"] = "COD"
        payload["cod_amount"] = float(order.total_amount)
    else:
        payload["payment_method"] = "Prepaid"

    print("🚀 SHIPROCKET REQUEST:", payload)

    try:
        res = requests.post(url, json=payload, headers=headers)

        print("🚀 STATUS:", res.status_code)
        print("🚀 RESPONSE:", res.text)

        data = res.json()

        # ---------------- SAFE ERROR HANDLING ----------------
        if res.status_code != 200:
            print("❌ Shiprocket Failed:", data)
            return {"success": False, "response": data}

        return data

    except Exception as e:
        print("❌ Shiprocket Exception:", str(e))
        return {"success": False, "error": str(e)}

# ---------------------------
# 3. SERVICEABILITY
# ---------------------------
def check_serviceability(pincode, weight=0.5):
    token = get_shiprocket_token()

    url = f"{BASE_URL}/courier/serviceability/"

    headers = {"Authorization": f"Bearer {token}"}

    params = {
        "pickup_postcode": "560001",
        "delivery_postcode": pincode,
        "cod": 1,
        "weight": weight
    }

    return requests.get(url, params=params, headers=headers).json()

# ---------------------------
# 4. AWB GENERATION
# ---------------------------
def generate_awb(shipment_id, courier_id):
    token = get_shiprocket_token()

    url = f"{BASE_URL}/courier/assign/awb"

    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "shipment_id": shipment_id,
        "courier_id": courier_id
    }

    return requests.post(url, json=payload, headers=headers).json()


# ---------------------------
# 5. LABEL
# ---------------------------
def generate_label(shipment_id):
    token = get_shiprocket_token()

    url = f"{BASE_URL}/courier/generate/label"

    headers = {"Authorization": f"Bearer {token}"}

    return requests.post(url, json={"shipment_id": shipment_id}, headers=headers).json()


# ---------------------------
# 6. PICKUP
# ---------------------------
def request_pickup(shipment_id):
    token = get_shiprocket_token()

    url = f"{BASE_URL}/courier/generate/pickup"

    headers = {"Authorization": f"Bearer {token}"}

    return requests.post(url, json={"shipment_id": shipment_id}, headers=headers).json()


# ---------------------------
# 7. TRACKING
# ---------------------------
def track_awb(awb):
    token = get_shiprocket_token()

    url = f"{BASE_URL}/courier/track/awb/{awb}"

    headers = {"Authorization": f"Bearer {token}"}

    return requests.get(url, headers=headers).json()