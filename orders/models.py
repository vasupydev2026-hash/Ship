from django.db import models
from django.conf import settings
from address.models import Address
from app.models import Product, Size
import uuid
from decimal import Decimal
from cartPage.models import TaxesAndCharges

# =========================
# ORDER
# =========================

class Order(models.Model):
    order_code = models.CharField(max_length=12, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True)

    # ---------- Amounts ----------
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_charges = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # ---------- Payment ----------
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    payment_method = models.CharField(max_length=50, default="razorpay")
    razorpay_order_id = models.CharField(max_length=200, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=200, null=True, blank=True)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default='pending'
    )

    payment_failure_reason = models.TextField(null=True, blank=True)
    payment_attempts = models.PositiveIntegerField(default=1)

    # ---------- Order Status ----------
    STATUS_CHOICES = (
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out For Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')

    # ---------- Timestamps ----------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # ---------- Shipping (Delhivery) ----------

    courier_name = models.CharField(max_length=50, blank=True, null=True)
    tracking_id = models.CharField(max_length=100, blank=True, null=True)  # Waybill
    shipment_created_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    shipping_status = models.CharField(
        max_length=50,
        default="not_created"
    )

### order status  ###

    def update_status_from_items(self):
        statuses = set(self.items.values_list("status", flat=True))

        if not statuses:
            return

        if "out_for_delivery" in statuses:
            new_status = "out_for_delivery"
        elif "shipped" in statuses:
            new_status = "shipped"
        elif "processing" in statuses:
            new_status = "processing"
        elif statuses == {"delivered"}:
            new_status = "delivered"
        elif statuses == {"cancelled"}:
            new_status = "cancelled"
        elif statuses == {"returned"}:
            new_status = "returned"
        else:
            new_status = "processing"

        if self.status != new_status:
            self.status = new_status
            self.save(update_fields=["status", "updated_at"])

    def recalculate_totals(self):
        active_items = self.items.exclude(status__in=['cancelled', 'returned'])
        subtotal = sum(item.price * item.quantity for item in active_items)

        tax_obj = TaxesAndCharges.objects.first()

        tax_rate = Decimal(tax_obj.tax) if tax_obj else Decimal("0.00")
        delivery = Decimal(tax_obj.delivery_charges) if tax_obj else Decimal("0.00")
        min_free = Decimal(tax_obj.min_amount_for_free_delivery) if tax_obj else Decimal("0.00")

        # tax
        tax = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))

        # ✅ FREE DELIVERY LOGIC FIX
        if subtotal >= min_free:
            delivery = Decimal("0.00")

        grand_total = subtotal + tax + delivery

        total_refunds = sum(
            r.refund_amount for r in self.return_requests.filter(status='refunded')
        )

        grand_total -= total_refunds

        self.total_amount = subtotal
        self.tax_amount = tax
        self.delivery_charges = delivery
        self.grand_total = max(grand_total, Decimal("0.00"))

        if self.grand_total <= 0:
            self.status = 'cancelled'

        self.save(update_fields=[
            'total_amount',
            'tax_amount',
            'delivery_charges',
            'grand_total',
            'status',
            'updated_at'
        ])

        return {
            "total_amount": float(self.total_amount),
            "tax_amount": float(self.tax_amount),
            "delivery_charges": float(self.delivery_charges),
            "grand_total": float(self.grand_total),
            "total_refunds": float(total_refunds),
        }

# ORDER ITEM
# =========================
class OrderItem(models.Model):

    STATUS_CHOICES = (
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out For Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned'),
    )

    order = models.ForeignKey(
        Order,
        related_name="items",
        on_delete=models.CASCADE
    )
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(product.name,default='Name')
    # product_name = models.CharField(max_length=255)

    product_sku = models.CharField(max_length=100, blank=True)
    size = models.ForeignKey(Size, null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField(default=1)
    refunded_quantity = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    return_reason = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Recalculate order totals automatically whenever item changes
        if self.order:
            self.order.recalculate_totals()
            self.order.update_status_from_items()  # 🔑 ADD THIS

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

# =========================
# RETURN REQUEST
# =========================

class ReturnRequest(models.Model):
    STATUS_CHOICES = (
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('pickup_scheduled', 'Pickup Scheduled'),
        ('picked_up', 'Picked Up'),
        ('received', 'Received'),
        ('refunded', 'Refunded'),
        ('rejected', 'Rejected'),
    )

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, default=1)

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="return_requests"
    )
    item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="returns"
    )

    reason = models.CharField(max_length=250)
    quantity = models.PositiveIntegerField(default=1)

    # -------- Return Shipping --------
    courier_name = models.CharField(max_length=50, default="Delhivery")
    return_waybill = models.CharField(max_length=100, blank=True, null=True)

    # -------- Refund Info --------
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='requested'
    )
    # -------- Timestamps --------

    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    pickup_scheduled_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Return {self.order.order_code} - {self.item.product.name}"




