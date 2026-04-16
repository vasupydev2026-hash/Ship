from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from cartPage.models import CartItem,TaxesAndCharges
from address.models import Address  # adjust paths if needed
from decimal import Decimal, ROUND_HALF_UP
import json
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from decimal import Decimal, ROUND_HALF_UP
from django.http import HttpResponse
from django.template.loader import get_template
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from .models import Order

def download_invoice(request, order_code):
    # Fetch order
    order = Order.objects.select_related(
        "address", "user"
    ).prefetch_related("items").get(order_code=order_code)

    items = order.items.exclude(status__in=["cancelled", "returned"])

    # Render HTML template to string
    html_string = render_to_string("orders/invoice.html", {
        "order": order,
        "items": items
    })

    # Generate PDF
    html = HTML(string=html_string)
    pdf = html.write_pdf()

    # Create response
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="invoice_{order.order_code}.pdf"'
    )

    return response



@login_required
def confirm_order(request):

    # --------------------------------------------------
    # STEP 1: AJAX POST FROM CART PAGE
    # (ONLY STORE DATA — NO ORDER CREATION)
    # --------------------------------------------------
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            selected_items = data.get("selected_items", [])
            selected_address_id = data.get("selected_address")
            payment_method = data.get("payment_method")

            if not selected_items or not payment_method:
                return JsonResponse({"error": "Invalid data"}, status=400)

            # Store in session
            request.session["selected_items"] = selected_items
            request.session["selected_address"] = selected_address_id
            request.session["payment_method"] = payment_method

            # ALWAYS redirect to confirm page
            return JsonResponse({
                "redirect_url": reverse("confirm_order")
            })

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    # --------------------------------------------------
    # STEP 2: CONFIRM ORDER PAGE (GET)
    # --------------------------------------------------
    selected_items = request.session.get("selected_items")
    selected_address_id = request.session.get("selected_address")
    payment_method = request.session.get("payment_method")

    if not selected_items:
        return redirect("cart")

    cart_items = CartItem.objects.filter(
        user=request.user,
        id__in=selected_items
    )

    if not cart_items.exists():
        return redirect("cart")

    # ---------------- PRICE CALCULATION ----------------
    tax_obj = TaxesAndCharges.objects.first()
    tax_rate = Decimal(tax_obj.tax) if tax_obj else Decimal("0.00")
    delivery_charge = Decimal(tax_obj.delivery_charges) if tax_obj else Decimal("0.00")
    min_free_delivery = Decimal(tax_obj.min_amount_for_free_delivery) if tax_obj else Decimal("0.00")

    subtotal = sum(Decimal(item.product.price) * item.quantity for item in cart_items)
    taxes = (subtotal * tax_rate / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if subtotal >= min_free_delivery:
        delivery_charge = Decimal("0.00")

    total_price = (subtotal + taxes + delivery_charge).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    print("🟡 CONFIRM PAGE DATA:", total_price, taxes, delivery_charge)

    # ---------------- ADDRESS ----------------
    selected_address = Address.objects.filter(
        user=request.user,
        id=selected_address_id
    ).first() or Address.objects.filter(
        user=request.user,
        is_default=True
    ).first()

    context = {
        "cart_items": cart_items,
        "subtotal": subtotal,
        "taxes": taxes,
        "delivery_charge": delivery_charge,
        "total_price": total_price,
        "selected_address": selected_address,
        "payment_method": payment_method,
    }

    return render(request, "orders/confirm_order.html", context)


from django.contrib.auth.decorators import login_required
from orders.services.shipping_pipeline import process_shipping
from django.db import transaction
from django.shortcuts import redirect
from django.contrib import messages
from decimal import Decimal
from .utils import generate_order_code, send_order_confirmation_email
from .services.shipping_pipeline import process_shipping
from .tasks import process_shiprocket_order
from django.db import transaction
@login_required
@transaction.atomic
def place_confirm_order(request):

    if request.method != "POST":
        return redirect("cart")

    user = request.user

    # -----------------------------
    # SESSION DATA
    # -----------------------------
    selected_items = request.session.get("selected_items", [])
    selected_address_id = request.session.get("selected_address")
    payment_method = request.session.get("payment_method")

    if not selected_items or payment_method != "cod":
        messages.error(request, "Invalid order request.")
        return redirect("cart")

    # -----------------------------
    # ADDRESS
    # -----------------------------
    address = Address.objects.filter(user=user, id=selected_address_id).first()

    if not address:
        messages.error(request, "Delivery address not found.")
        return redirect("cart")

    # -----------------------------
    # CART ITEMS
    # -----------------------------
    cart_items = CartItem.objects.select_related("product", "size").filter(
        user=user,
        id__in=selected_items
    )

    if not cart_items.exists():
        messages.error(request, "Cart items not found.")
        return redirect("cart")

    # -----------------------------
    # PRICE CALCULATION
    # -----------------------------
    tax_obj = TaxesAndCharges.objects.last()

    tax_rate = Decimal(tax_obj.tax) if tax_obj else Decimal("0.00")
    delivery_charge = Decimal(tax_obj.delivery_charges) if tax_obj else Decimal("0.00")
    min_free_delivery = Decimal(tax_obj.min_amount_for_free_delivery) if tax_obj else Decimal("0.00")

    subtotal = sum(Decimal(str(item.price)) * item.quantity for item in cart_items)

    taxes = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    if subtotal >= min_free_delivery:
        delivery_charge = Decimal("0.00")

    total_amount = (subtotal + taxes + delivery_charge).quantize(Decimal("0.01"))

    print("🔥 COD ORDER DATA:", total_amount, taxes, delivery_charge)

    # -----------------------------
    # TRANSACTION START
    # -----------------------------
    with transaction.atomic():

        # -----------------------------
        # CREATE ORDER
        # -----------------------------
        order = Order.objects.create(
            user=user,
            address=address,
            order_code=generate_order_code(),
            payment_method="cod",
            payment_status="pending",
            status="confirmed",
            total_amount=total_amount,
            tax_amount=taxes,
            delivery_charges=delivery_charge,
            grand_total=total_amount,
        )

        # -----------------------------
        # ORDER ITEMS + STOCK UPDATE
        # -----------------------------
        for item in cart_items:
            stock = ProductStock.objects.select_for_update().get(
                product=item.product,
                size=item.size
            )

            stock.stock -= item.quantity
            stock.save()

            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                quantity=item.quantity,
                price=item.price,
                size=item.size,
            )

        # -----------------------------
        # CLEAR CART
        # -----------------------------
        cart_items.delete()

        # -----------------------------
        # 🚚 SHIPPING PIPELINE (IMPORTANT FIX)
        # -----------------------------
        transaction.on_commit(lambda: process_shipping(order.id))
    # -----------------------------
    # EMAIL
    # -----------------------------
    send_order_confirmation_email(order)

    # -----------------------------
    # CLEAR SESSION
    # -----------------------------
    for key in ["selected_items", "selected_address", "payment_method"]:
        request.session.pop(key, None)

    return redirect("order_success")

@login_required
def payment_success(request):
    request.session.pop("payment_method", None)
    return redirect("order_success")



@login_required
def order_success(request):
    tax_per = TaxesAndCharges.tax
    latest_order = (
        Order.objects
        .filter(user=request.user)
        .order_by("-created_at")
        .first()
    )

    if not latest_order:
        return redirect("home")

    return render(request, "orders/order_success.html", {
        "order": latest_order,
        "tax_per":tax_per
    })


from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
import razorpay
from datetime import datetime

from cartPage.models import CartItem
from orders.models import Order, OrderItem
from orders.utils import send_order_confirmation_email
from app.models import Product, Size, ProductStock

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
import razorpay

client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

@login_required
def razorpay_payment(request):
    if request.method != "POST":
        return redirect("cart/cart/")

    user = request.user

    # -----------------------------
    # SESSION DATA
    # -----------------------------
    selected_items = request.session.get("selected_items", [])
    selected_address_id = request.session.get("selected_address")

    if not selected_items or not selected_address_id:
        return redirect("cart/cart/")

    # -----------------------------
    # FETCH DATA
    # -----------------------------
    cart_items = CartItem.objects.select_related(
        "product", "size"
    ).filter(user=user, id__in=selected_items)

    if not cart_items.exists():
        return redirect("cartPage:cartPage")

    selected_address = Address.objects.filter(
        id=selected_address_id,
        user=user
    ).first()

    if not selected_address:
        return redirect("confirm_order")

    # -----------------------------
    # PRICE CALCULATION
    # -----------------------------
    tax_obj = TaxesAndCharges.objects.first()
    tax_rate = Decimal(tax_obj.tax) if tax_obj else Decimal("0.00")
    delivery_charge = Decimal(tax_obj.delivery_charges) if tax_obj else Decimal("0.00")
    min_free_delivery = Decimal(tax_obj.min_amount_for_free_delivery) if tax_obj else Decimal("0.00")
    subtotal = sum(Decimal(item.price) * item.quantity for item in cart_items)
    tax_amount = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    if subtotal >= min_free_delivery:
        delivery_charge = Decimal("0.00")

    grand_total = (subtotal + tax_amount + delivery_charge).quantize(Decimal("0.01"))
    amount_paise = int(grand_total * 100)

    # -----------------------------
    # CREATE RAZORPAY ORDER (ONLY)
    # -----------------------------

    razorpay_order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": 1
    })

    # -----------------------------
    # STORE TEMP DATA
    # -----------------------------
    request.session["razorpay_order_id"] = razorpay_order["id"]
    request.session["payable_amount"] = str(grand_total)

    # -----------------------------
    # RENDER PAYMENT PAGE
    # -----------------------------
    return render(request, "orders/razorpay_payment.html", {
        "cart_items": cart_items,
        "selected_address": selected_address,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "delivery_charge": delivery_charge,
        "grand_total": grand_total,
        "razorpay_order_id": razorpay_order["id"],
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "amount_paise": amount_paise,
        "user": user,
    })



# ------------------- Payment Success Handler -------------------

import requests
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone
from decimal import Decimal
import razorpay
from .services.shiprocket import create_order as shiprocket_create_order

from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from decimal import Decimal


from .utils import generate_order_code, send_order_confirmation_email
from .services.shiprocket import create_order as shiprocket_create_order

import razorpay


client = razorpay.Client(auth=("YOUR_KEY", "YOUR_SECRET"))

from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

import razorpay
from .utils import generate_order_code, send_order_confirmation_email
from .services.shiprocket import create_order as shiprocket_create_order

client = razorpay.Client(auth=("YOUR_KEY", "YOUR_SECRET"))


# -------------------------------
# 🚚 SHIPROCKET PUSH FUNCTION
# -------------------------------

def push_shiprocket_order(order_id):

    try:
        order = Order.objects.get(id=order_id)

        print("🚚 Sending order to Shiprocket...")

        ship_res = shiprocket_create_order(order)

        print("🚚 Shiprocket Response:", ship_res)

        # FIX: Shiprocket sometimes returns shipment_id or data.shipment_id
        shipment_id = ship_res.get("shipment_id") or ship_res.get("data", {}).get("shipment_id")

        if shipment_id:
            order.shiprocket_shipment_id = shipment_id
            order.save()

        else:
            print("⚠️ No shipment_id returned:", ship_res)

    except Exception as e:
        print("❌ Shiprocket Error:", str(e))

@csrf_exempt
@transaction.atomic
def razorpay_payment_success(request):

    if request.method != "POST":
        return redirect("cartPage:cartPage")

    user = request.user

    razorpay_payment_id = request.POST.get("razorpay_payment_id")
    razorpay_order_id = request.POST.get("razorpay_order_id")
    razorpay_signature = request.POST.get("razorpay_signature")

    # -------------------------------
    # ❌ PAYMENT FAILED
    # -------------------------------
    if not razorpay_payment_id:
        return render(request, "orders/payment_failed.html", {
            "reason": "Payment cancelled by user"
        })

    # -------------------------------
    # 🔐 VERIFY PAYMENT
    # -------------------------------
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature
        })
    except razorpay.errors.SignatureVerificationError:
        return render(request, "orders/payment_failed.html", {
            "reason": "Signature verification failed"
        })

    # -------------------------------
    # 🛒 SESSION DATA
    # -------------------------------
    selected_items = request.session.get("selected_items", [])
    selected_address_id = request.session.get("selected_address")

    if not selected_items or not selected_address_id:
        return redirect("cartPage:cartPage")

    cart_items = CartItem.objects.select_related("product", "size").filter(
        user=user,
        id__in=selected_items
    )

    if not cart_items.exists():
        return redirect("cartPage:cartPage")

    address = Address.objects.get(id=selected_address_id, user=user)

    # -------------------------------
    # 💰 PRICE CALCULATION
    # -------------------------------
    tax_obj = TaxesAndCharges.objects.last()

    tax_rate = Decimal(tax_obj.tax) if tax_obj else Decimal("0.00")
    delivery_charge = Decimal(tax_obj.delivery_charges) if tax_obj else Decimal("0.00")
    free_delivery_min = Decimal(tax_obj.min_amount_for_free_delivery) if tax_obj else Decimal("0.00")

    subtotal = sum(Decimal(str(i.price)) * i.quantity for i in cart_items)

    tax_amount = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    if subtotal >= free_delivery_min:
        delivery_charge = Decimal("0.00")

    total_amount = (subtotal + tax_amount + delivery_charge).quantize(Decimal("0.01"))

    # -------------------------------
    # 🧾 CREATE ORDER + ITEMS
    # -------------------------------
    with transaction.atomic():

        order = Order.objects.create(
            user=user,
            address=address,
            order_code=generate_order_code(),
            payment_method="razorpay",
            payment_status="paid",
            status="processing",
            total_amount=total_amount,
            tax_amount=tax_amount,
            delivery_charges=delivery_charge,
            grand_total=total_amount,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            paid_at=timezone.now(),
        )

        # -------------------------------
        # 📦 ORDER ITEMS + STOCK UPDATE
        # -------------------------------
        for item in cart_items:

            stock = ProductStock.objects.select_for_update().get(
                product=item.product,
                size=item.size
            )

            if stock.stock < item.quantity:
                raise Exception("Stock mismatch after payment")

            stock.stock -= item.quantity
            stock.save()

            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                size=item.size,
                quantity=item.quantity,
                price=item.price
            )

        # -------------------------------
        # 🧹 CLEAR CART
        # -------------------------------
        CartItem.objects.filter(
            id__in=selected_items,
            user=user
        ).delete()

    # -------------------------------
    # 🚚 SHIPROCKET (AFTER COMMIT - SAFE)
    # -------------------------------
    def after_commit_shiprocket():
        try:
            from .services.shiprocket import create_order as shiprocket_create_order

            ship_res = shiprocket_create_order(order)

            print("🚚 Shiprocket Response:", ship_res)

            order.shiprocket_shipment_id = ship_res.get("shipment_id")
            order.shiprocket_order_id = ship_res.get("order_id")
            order.save()

        except Exception as e:
            print("❌ Shiprocket Error:", str(e))

    transaction.on_commit(lambda: process_shipping(order.id))

    # -------------------------------
    # 📧 EMAIL
    # -------------------------------
    send_order_confirmation_email(order)

    # -------------------------------
    # 🧹 CLEAR SESSION
    # -------------------------------
    for key in [
        "selected_items",
        "selected_address",
        "payment_method",
        "razorpay_order_id",
        "payable_amount"
    ]:
        request.session.pop(key, None)

    return redirect("order_success")


from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import Order
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import Order
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone
import json
from .models import Order

from django.conf import settings

@csrf_exempt
def shiprocket_webhook(request):

    # 🔐 TOKEN VALIDATION
    api_key = request.headers.get("x-api-key")

    if api_key != settings.SHIPROCKET_WEBHOOK_TOKEN:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    try:
        data = json.loads(request.body)
        print("📩 WEBHOOK:", data)

        awb = data.get("awb")
        status = data.get("current_status")

        order = Order.objects.filter(awb_code=awb).first()

        if not order:
            return JsonResponse({"status": "ignored"})

        order.tracking_status = status

        if status.lower() == "delivered":
            order.status = "delivered"

        elif status.lower() == "out for delivery":
            order.status = "out_for_delivery"

        elif status.lower() in ["shipped", "in transit"]:
            order.status = "shipped"

        order.save()

        return JsonResponse({"status": "updated"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def retry_payment(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        payment_status="failed"
    )

    razorpay_order = client.order.create({
        "amount": int(order.grand_total * 100),
        "currency": "INR",
        "payment_capture": 1
    })

    order.razorpay_order_id = razorpay_order["id"]
    order.payment_status = "pending"
    order.save(update_fields=[
        "razorpay_order_id",
        "payment_status",
        "updated_at"
    ])

    return render(request, "orders/razorpay_payment.html", {
        "order": order,
        "razorpay_order_id": razorpay_order["id"],
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "amount_paise": int(order.grand_total * 100)
    })

@login_required
def payment_failed_page(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    return render(request, "orders/payment_failed.html", {
        "order": order
    })


@login_required
def order_history(request):
    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related('items')
        .order_by('-created_at')
    )

    return render(request, 'orders/order_history.html', {
        'orders': orders
    })

@login_required
def order_summary(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    confirmed_items = order.items.filter(status='confirmed')
    cancelled_items = order.items.filter(status='cancelled')

    return render(request, 'orders/order_summary.html', {
        'order': order,
        'confirmed_items': confirmed_items,
        'cancelled_items': cancelled_items,
    })


@login_required
def order_detail(request, order_code):
    order = get_object_or_404(
        Order,
        order_code=order_code,
        user=request.user
    )

    items = order.items.all()
    # Check if all items are delivered
    items_statuses = [item.status for item in items]

    # Case 1: All items delivered
    all_delivered = all(status == 'delivered' for status in items_statuses)

    # Case 2: At least one item returned (successfully)
    any_returned = any(status == 'returned' for status in items_statuses)

    # Case 3: Entire order cancelled
    all_cancelled = all(status == 'cancelled' for status in items_statuses)

    # FINAL INVOICE CONDITION
    enable_invoice = all_delivered or any_returned or all_cancelled

    return render(request, 'orders/order_detail.html', {
        'order': order,
            "enable_invoice": enable_invoice,
        'items': items,
    })

@login_required
def load_active_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    return render(request, "orders/partials/active_item.html", {"item": item})


def active_item_partial(request, item_id):
    item = get_object_or_404(
        OrderItem.objects.select_related("product", "order", "order__address"),
        id=item_id
    )
    return render(request, "orders/partials/active_item.html", {
        "item": item
    })

# orders/views.py
from django.http import JsonResponse
from django.db import transaction

@login_required
def cancel_order_item(request, item_id):
    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "message": "Invalid request method."
        })

    order_item = get_object_or_404(
        OrderItem,
        id=item_id,
        order__user=request.user
    )

    if order_item.status not in ["confirmed", "processing"]:
        return JsonResponse({
            "success": False,
            "message": "This item cannot be cancelled."
        })

    with transaction.atomic():

        # 1️⃣ Mark item cancelled
        order_item.status = "cancelled"
        order_item.save(update_fields=["status"])

        # 2️⃣ Restore stock
        if order_item.product:
            if order_item.size:
                stock = order_item.product.stocks.filter(
                    size=order_item.size
                ).first()
                if stock:
                    stock.stock += order_item.quantity
                    stock.save(update_fields=["stock"])
            else:
                order_item.product.stock += order_item.quantity
                order_item.product.save(update_fields=["stock"])

        # 3️⃣ Recalculate order totals (MODEL METHOD)
        totals = order_item.order.recalculate_totals()

    return JsonResponse({
        "success": True,
        "message": "Item cancelled successfully.",
        "item_id": order_item.id,
        "totals": totals
    })


# ##### RETURN FUNCTIONALITIES  #######


from .models import ReturnRequest
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal
from .models import OrderItem, ReturnRequest

@login_required
@transaction.atomic
def item_issue(request, item_id):
    if request.method != "POST":
        return JsonResponse({"success": False})

    order_item = get_object_or_404(
        OrderItem,
        id=item_id,
        order__user=request.user
    )

    if order_item.status != "delivered":
        return JsonResponse({
            "success": False,
            "message": "Item not eligible for return"
        })

    reason = request.POST.get("reason", "").strip()
    if not reason:
        return JsonResponse({
            "success": False,
            "message": "Reason required"
        })

    order_item.status = "returned"
    order_item.return_reason = reason
    order_item.refunded_quantity = order_item.quantity
    order_item.save()

    # Restore stock
    if order_item.size:
        stock = order_item.product.stocks.filter(size=order_item.size).first()
        if stock:
            stock.stock += order_item.quantity
            stock.save()
    else:
        order_item.product.stock += order_item.quantity
        order_item.product.save()

    return_request = ReturnRequest.objects.create(
        order=order_item.order,
        item=order_item,
        reason=reason,
        quantity=order_item.quantity,
    )

    return JsonResponse({
        "success": True,
        "message": "Return requested successfully"
    })
#

import razorpay
from django.conf import settings

client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

@transaction.atomic
def process_refund(rr):
    order = rr.order

    refund_amount = rr.item.price * rr.quantity
    refund_paise = int(refund_amount * 100)

    if order.payment_method == "razorpay":
        client.payment.refund(
            order.razorpay_payment_id,
            {
                "amount": refund_paise,
                "notes": {
                    "order": order.order_code,
                    "reason": "Product returned"
                }
            }
        )


    rr.refund_amount = refund_amount
    rr.status = "refunded"
    rr.refunded_at = timezone.now()
    rr.save()


    # Update order payment status
    order.payment_status = "refunded"
    order.save(update_fields=["payment_status"])


@login_required
def refund_return(request, return_id):
    rr = get_object_or_404(ReturnRequest, id=return_id)

    if rr.status != "received":
        return JsonResponse({"error": "Item not received"}, status=400)

    process_refund(rr)

    return JsonResponse({"success": True})


# orders/views.py
from django.contrib.admin.views.decorators import staff_member_required
from .models import ReturnRequest

@staff_member_required
def returns_list(request):
    returns = (
        ReturnRequest.objects
        .select_related("order", "item")
        .order_by("-created_at")
    )

    return render(request, "orders/returns_list.html", {
        "returns": returns
    })



@login_required
def return_detail(request, return_id):
    if not request.user.is_staff:
        return redirect("home")

    rr = get_object_or_404(ReturnRequest, id=return_id)

    return render(request, "orders/return_detail.html", {
        "rr": rr
    })



# #### EMAIL SERVICE #####



from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def send_order_confirmation_email(order):

    subject = f"Order Confirmation - {order.order_code}"
    html_message = render_to_string('orders/order_confirmation_email.html', {'order': order})
    plain_message = strip_tags(html_message)
    recipient_list = [order.user.email]

    send_mail(
        subject,
        plain_message,
        'MyShop <your-email@gmail.com>',
        recipient_list,
        html_message=html_message,
        fail_silently=False,
    )


# # orders/views.py

from django.shortcuts import render, get_object_or_404
from .models import OrderItem

def track_order_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    return render(request, 'orders/track_order_item.html', {
        'item': item
    })



# --------- ship rocket  -----------#
