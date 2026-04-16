# -------------------------------
# Django Imports
# -------------------------------
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from tomlkit import item

from app.models import Product, ProductStock
from wishlist.models import Wishlist
# -------------------------------
# Python Imports
# -------------------------------
import json, random, re, time, requests
from decimal import Decimal

# -------------------------------
# Models
# -------------------------------
from .models import CartItem, TaxesAndCharges
from app.models import Product,Size
from address.models import Address

# -------   TAX CREDENTIALS INFO --------- #

def get_tax_settings():
    taxes_and_charges = TaxesAndCharges.objects.first()
    if not taxes_and_charges:
        return {
            "tax": 0,
            "min_amount_for_free_delivery": 9999999,  # fallback high
            "delivery_charges": 0,
        }
    return {
        "tax": taxes_and_charges.tax,
        "min_amount_for_free_delivery": taxes_and_charges.min_amount_for_free_delivery,
        "delivery_charges": taxes_and_charges.delivery_charges,
    }

from django.views.decorators.csrf import csrf_exempt, csrf_protect

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import CartItem
from app.models import Product, Size, ProductStock

# -------   ADD TO CART LOGIC  --------- #

@csrf_protect
def add_to_cart(request):
    if request.method == 'POST' and request.user.is_authenticated:

        product_id = request.POST.get('product_id')
        size_id = request.POST.get('size_id')
        quantity = int(request.POST.get('quantity', 1))

        product = get_object_or_404(Product, id=product_id)
        size = get_object_or_404(Size, id=size_id)

        stock = ProductStock.objects.filter(product=product, size=size).first()
        if not stock or stock.stock < quantity:
            return JsonResponse({
                'success': False,
                'message': 'Requested quantity not available in stock'
            })

        cart_item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product,
            size=size,  
            defaults={
                'image_url': product.image_url,
                'name': product.name,
                'price': product.price,
                'color': product.color,
                'quantity': quantity,
                'stock': stock.stock,
                'is_available_for_cod': product.is_available_for_cod,
            }
        )

        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        total_items = CartItem.objects.filter(user=request.user).count()

        return JsonResponse({
            'success': True,
            'message': f"{product.name} added to cart!",
            'cart_count': total_items
        })

    return JsonResponse({'success': False, 'message': 'Login required'})


# -------   CART VIEW OR CART ITEMS --------- #

from decimal import Decimal

def cart(request):
    """Render cart page for the current user."""
    settings_data = get_tax_settings()
    tax_percentage = settings_data["tax"]
    min_amount_for_free_delivery = settings_data["min_amount_for_free_delivery"]
    delivery_charges = settings_data["delivery_charges"]

    if request.user.is_authenticated:
        cart_items = CartItem.objects.filter(user=request.user)
        addresses = Address.objects.filter(user=request.user)
        wishlist_items = Wishlist.objects.filter(user=request.user).select_related("product")
    else:
        cart_items = []
        addresses = None
        wishlist_items = []

    # ----------------- CALCULATIONS -----------------
    total_items = 0
    all_items_eligible_for_cod = True

    for item in cart_items:
        item_price = Decimal(str(item.price))  # ✅ FIX
        item.subtotal = item_price * item.quantity
        total_items += item.quantity

        stock_record = ProductStock.objects.filter(
            product=item.product,
            size=item.size
        ).first()

        item.stock = stock_record.stock if stock_record else 0

        if item.product and not item.product.is_available_for_cod:
            all_items_eligible_for_cod = False
            item.is_available_for_cod = False
        else:
            item.is_available_for_cod = True

    # ✅ FIXED TOTAL PRICE
    total_price = sum(Decimal(str(item.price)) * item.quantity for item in cart_items)
    total_price = Decimal(str(total_price)).quantize(Decimal("0.01"))
    tax_percentage = Decimal(str(tax_percentage))
    taxes = (tax_percentage / Decimal("100") * total_price).quantize(Decimal("0.01"))

    delivery_charges = Decimal(str(delivery_charges))
    min_amount_for_free_delivery = Decimal(str(min_amount_for_free_delivery))

    delivery_charge = Decimal("0.00") if total_price >= min_amount_for_free_delivery else delivery_charges
    delivery_charge = delivery_charge.quantize(Decimal("0.01"))

    grand_total = (total_price + taxes + delivery_charge).quantize(Decimal("0.01"))

    # ----------------- DEFAULT ADDRESS -----------------
    default_address = None
    if addresses:
        default_address = addresses.filter(is_default=True).first() or addresses.first()

    return render(request, "cartPage/cart.html", {
        "cart_items": cart_items,
        "wishlist_items": wishlist_items,
        "total_items": total_items,
        "total_price": total_price,
        "addresses": addresses,
        "default_address": default_address,
        "all_items_eligible_for_cod": all_items_eligible_for_cod,
        "taxes": taxes,
        "delivery_charge": delivery_charge,
        "grand_total": grand_total,
        "min_amount_for_free_delivery": min_amount_for_free_delivery,
        "taxes_and_charges": settings_data,
    })


# -------   CART CHECKOUT --------- #

def checkout_view(request):
    addresses = Address.objects.filter(user=request.user)
    default_address = addresses.filter(is_default=True).first() or addresses.first()

    # Serialize for frontend JS if needed
    addresses_json = json.dumps(list(addresses.values(
        "id", "full_name", "address_line1", "address_line2",
        "city", "state", "pincode", "country",
        "mobile_number", "is_default"
    )), cls=DjangoJSONEncoder)

    return render(request, "checkout.html", {
        "addresses": addresses,
        "default_address": default_address,
        "addresses_json": addresses_json,
    })


# -------   UPDATE CART  --------- #

@require_POST
@login_required
def update_cart(request, item_id):
    data = json.loads(request.body)
    action = data.get("action")

    cart_item = get_object_or_404(CartItem, id=item_id, user=request.user)

    stock_obj = ProductStock.objects.filter(
        product=cart_item.product,
        size=cart_item.size
    ).first()

    available_stock = stock_obj.stock if stock_obj else 0

    if action == "increase":
        if cart_item.quantity >= available_stock:
            return JsonResponse({
                "error": "Stock limit reached",
                "quantity": cart_item.quantity,
                "stock": available_stock
            }, status=400)

        cart_item.quantity += 1

    elif action == "decrease":
        cart_item.quantity -= 1
        if cart_item.quantity <= 0:
            cart_item.delete()
            return _cart_summary_response(request.user, removed=True)

    else:
        return JsonResponse({"error": "Invalid action"}, status=400)

    cart_item.save() 

    item_subtotal = Decimal(cart_item.price) * cart_item.quantity

    # ✅ Check if all current items in cart are COD eligible using the CURRENT product status
    all_items_eligible_for_cod = all(
        item.product.is_available_for_cod if item.product else True
        for item in CartItem.objects.filter(user=request.user)
    )

    return JsonResponse({
        "quantity": cart_item.quantity,
        "subtotal": float(item_subtotal),
        "stock": available_stock,
        "all_items_eligible_for_cod": all_items_eligible_for_cod
    })


# -------   CART CONFIRMATION --------- #

def _cart_summary_response(user, updated_item=None, removed=False):
    settings_data = get_tax_settings()
    tax_percentage = Decimal(settings_data["tax"])  # use Decimal for money math
    min_amount_for_free_delivery = Decimal(settings_data["min_amount_for_free_delivery"])
    delivery_charges = Decimal(settings_data["delivery_charges"])

    cart_items = CartItem.objects.filter(user=user)
    total_items = sum(item.quantity for item in cart_items)
    total_price = sum(Decimal(item.price) * item.quantity for item in cart_items)
    taxes = (tax_percentage / Decimal(100)) * total_price
    delivery_charge = Decimal(0) if total_price >= min_amount_for_free_delivery else delivery_charges
    grand_total = total_price + taxes + delivery_charge
    # ✅ Check if all current items are COD eligible using the CURRENT product status
    all_items_eligible_for_cod = all(
        item.product.is_available_for_cod if item.product else True
        for item in cart_items
    )

    # formatted strings for display (same format as your template)
    formatted = {
        "total_items": total_items,
        "total_price": f"₹{total_price:.2f}",
        "taxes": f"₹{taxes:.2f}",
        "delivery_charge": f"₹{delivery_charge:.2f}",
        "grand_total": f"₹{grand_total:.2f}",
    }

    # raw numeric values for JS to use (floats are fine for transfer; keep Decimal server-side)
    raw = {
        "total_price_raw": float(total_price),
        "taxes_raw": float(taxes),
        "delivery_charge_raw": float(delivery_charge),
        "grand_total_raw": float(grand_total),
    }

    response = {
        "removed": removed,
        "cart_summary": {
            **formatted,
            **raw
        },
        "all_items_eligible_for_cod": all_items_eligible_for_cod,
    }

    if updated_item:
        item_subtotal = Decimal(updated_item.price) * updated_item.quantity
        response.update({
                "quantity": updated_item.quantity,
                # both formatted and raw subtotal
                "subtotal": f"₹{item_subtotal:.2f}",
                "subtotal_raw": float(item_subtotal),
                "item_id": updated_item.id,
        })

    return JsonResponse(response)


def check_cart_item(request):
    product_id = request.GET.get('product_id')
    size_code = request.GET.get('size')  # string

    exists = CartItem.objects.filter(
        user=request.user,
        product_id=product_id,
        size=size_code
    ).exists()

    return JsonResponse({'exists': exists})
