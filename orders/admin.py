from django.contrib import admin
from django.utils.html import format_html
from django.db import transaction

from .models import Order, OrderItem, ReturnRequest
from shipping.tasks import process_shipping
from shipping.models import Shipment


# =========================
# ORDER ITEM INLINE
# =========================
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        'product',
        'product_name',
        'product_sku',
        'size',
        'quantity',
        'price',
        'status',
    )
    can_delete = False


# =========================
# RETURN REQUEST INLINE
# =========================
class ReturnRequestInline(admin.TabularInline):
    model = ReturnRequest
    extra = 0
    readonly_fields = (
        'item',
        'reason',
        'quantity',
        'refund_amount',
        'status',
        'created_at',
    )
    can_delete = False


# =========================
# ORDER ADMIN (UPGRADED)
# =========================
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        'order_code',
        'user',
        'order_status_badge',
        'payment_status',
        'grand_total',
        'shipment_status',
        'tracking_link',
        'created_at',
    )

    list_filter = (
        'status',
        'payment_status',
        'payment_method',
        'created_at',
    )

    search_fields = (
        'order_code',
        'user__username',
        'user__email',
    )

    readonly_fields = (
        'order_code',
        'total_amount',
        'tax_amount',
        'delivery_charges',
        'grand_total',
        'created_at',
        'updated_at',
        'razorpay_order_id',
        'razorpay_payment_id',
        'paid_at',
    )

    inlines = [OrderItemInline, ReturnRequestInline]

    ordering = ('-created_at',)

    # =========================
    # 🎯 UI STATUS BADGE
    # =========================
    def order_status_badge(self, obj):
        colors = {
            "pending": "gray",
            "confirmed": "blue",
            "shipped": "orange",
            "delivered": "green",
            "cancelled": "red",
        }
        color = colors.get(obj.status.lower(), "black")

        return format_html(
            '<span style="color:white;padding:4px 8px;border-radius:5px;background:{};">{}</span>',
            color,
            obj.status.upper()
        )

    order_status_badge.short_description = "Order Status"

    # =========================
    # 📦 SHIPMENT STATUS
    # =========================
    def shipment_status(self, obj):
        shipment = Shipment.objects.filter(order=obj).first()
        return shipment.status if shipment else "Not Created"

    shipment_status.short_description = "Shipment"

    # =========================
    # 🔗 TRACKING LINK
    # =========================
    def tracking_link(self, obj):
        shipment = Shipment.objects.filter(order=obj).first()
        if shipment and shipment.tracking_url:
            return format_html(
                '<a href="{}" target="_blank" style="color:white;background:#28a745;padding:5px 10px;border-radius:5px;">Track</a>',
                shipment.tracking_url
            )
        return "-"

    tracking_link.short_description = "Tracking"

    # =========================
    # 🔥 ADMIN ACTIONS
    # =========================
    actions = [
        'create_shipping',
        'retry_shipping',
        'mark_as_shipped',
        'mark_as_delivered',
    ]

    # 🚚 Create shipment manually
    def create_shipping(self, request, queryset):
        for order in queryset:
            print("ADMIN HIT:", order.id)  # DEBUG
            process_shipping.delay(order.id)

        self.message_user(request, "🚚 Shipping process started!")

    # 🔁 Retry shipping
    def retry_shipping(self, request, queryset):
        for order in queryset:
            process_shipping.delay(order.id)

        self.message_user(request, "🔁 Shipping retry triggered!")

    retry_shipping.short_description = "🔁 Retry Shipping"

    # 📦 Mark shipped
    def mark_as_shipped(self, request, queryset):
        queryset.update(status='shipped')

    mark_as_shipped.short_description = "📦 Mark as Shipped"

    # ✅ Mark delivered
    def mark_as_delivered(self, request, queryset):
        queryset.update(status='delivered')

    mark_as_delivered.short_description = "✅ Mark as Delivered"