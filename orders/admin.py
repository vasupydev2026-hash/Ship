from django.contrib import admin
from .models import Order, OrderItem ,ReturnRequest


# --- Inline Order Items inside Order Admin ---

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'size', 'quantity', 'price')
    can_delete = False


# --- Order Admin ---

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_code',
        'user',
        'payment_method',
        'payment_status',
        'order_status_display',  # ✅ USE METHOD HERE
        'courier_name',
        'tracking_id',
        'grand_total',
        'created_at'
    )

    list_filter = (
        'payment_status',
        'status',
        'payment_method',
        'courier_name',
        'created_at',
    )

    search_fields = (
        'order_code',
        'user__username',
        'user__email',
        'razorpay_order_id',
        'razorpay_payment_id',
    )

    readonly_fields = (
        'order_code',
        'user',
        'address',
        'total_amount',
        'tax_amount',
        'delivery_charges',
        'grand_total',

        # Payment
        'payment_method',
        'razorpay_order_id',
        'razorpay_payment_id',
        'payment_status',

        # Shipping
        'courier_name',
        'tracking_id',
        'shipment_created_at',
        'shipped_at',
        'delivered_at',

        # Meta
        "status",
        'created_at',
    )

    def order_status_display(self, obj):
        return obj.get_status_display()

    order_status_display.short_description = "Order Status"

    inlines = [OrderItemInline]

    fieldsets = (
        ("Order Info", {
            "fields": ("order_code", "user", "address", "created_at")
        }),
        ("Amount Details", {
            "fields": ("total_amount", "tax_amount", "delivery_charges", "grand_total")
        }),
        ("Payment Details", {
            "fields": ("payment_method", "payment_status", "razorpay_order_id", "razorpay_payment_id")
        }),
        ("Shipping Details", {
            "fields": (
                "courier_name",
                "tracking_id",
                "shipment_created_at",
                "shipped_at",
                "delivered_at",
            )
        }),
        ("Order Status", {
            "fields": ("status",)
        }),
    )




from django.contrib import admin
from django.utils import timezone
from .models import ReturnRequest

@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "item",
        "status",
        "return_waybill",
        "quantity",
        "refund_amount",
        "created_at",
        "approved_at",
        "pickup_scheduled_at",
        "picked_up_at",
        "received_at",
        "refunded_at",
    )
    list_filter = ("status", "courier_name")
    search_fields = ("order__order_code", "return_waybill", "item__product__name")
    readonly_fields = (
        "order",
        "item",
        "reason",
        "quantity",
        "courier_name",
        "return_waybill",
        "refund_amount",
        "created_at",
        "approved_at",
        "pickup_scheduled_at",
        "picked_up_at",
        "received_at",
        "refunded_at",
        "status",
    )

    actions = ["approve_return"]

    def approve_return(self, request, queryset):
        """
        Admin action to approve return requests, schedule pickup, and process refund
        """
        from orders.delhivery import create_return_shipment

        for ret in queryset:
            if ret.status == "requested":
                # 1️⃣ Approve
                ret.status = "approved"
                ret.approved_at = timezone.now()
                ret.save(update_fields=["status", "approved_at"])

                # 2️⃣ Schedule pickup (test mode will skip Delhivery call)
                try:
                    create_return_shipment(ret)
                except Exception as e:
                    self.message_user(
                        request,
                        f"Error scheduling pickup for ReturnRequest {ret.id}: {e}",
                        level="error"
                    )

                # 3️⃣ Process refund immediately (optional: can do after delivery confirmation)
                ret.refund_amount = ret.item.price * ret.quantity
                ret.status = "refunded"
                ret.refunded_at = timezone.now()
                ret.save(update_fields=["refund_amount", "status", "refunded_at"])

                # 4️⃣ Recalculate order totals
                ret.order.recalculate_totals()

                self.message_user(
                    request,
                    f"ReturnRequest {ret.id} approved, pickup scheduled, and refund processed."
                )

    approve_return.short_description = "Approve, Schedule Pickup & Refund"
