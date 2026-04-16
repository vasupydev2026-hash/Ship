from django.contrib import admin
from django.utils import timezone
from .models import Order, OrderItem, ReturnRequest


# =========================
# ORDER ITEM INLINE
# =========================
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "product_name",
        "size",
        "quantity",
        "price",
        "status",
    )
    can_delete = False


# =========================
# ORDER ADMIN
# =========================
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        "order_code",
        "user",
        "payment_method",
        "payment_status",
        "status",
        "grand_total",
        "shiprocket_order_id",
        "shiprocket_shipment_id",
        "awb_code",
        "created_at",
    )

    list_filter = (
        "payment_status",
        "payment_method",
        "status",
        "created_at",
    )

    search_fields = (
        "order_code",
        "user__username",
        "user__email",
        "razorpay_order_id",
        "razorpay_payment_id",
        "shiprocket_order_id",
        "shiprocket_shipment_id",
    )

    readonly_fields = (
        "order_code",
        "user",
        "address",

        # amounts
        "total_amount",
        "tax_amount",
        "delivery_charges",
        "grand_total",

        # payment
        "payment_method",
        "payment_status",
        "razorpay_order_id",
        "razorpay_payment_id",

        # shipping (SHIPROCKET)
        "shiprocket_order_id",
        "shiprocket_shipment_id",
        "awb_code",

        # status
        "status",
        "created_at",
        "updated_at",
        "paid_at",
    )

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

        ("Shipping Details (Shiprocket)", {
            "fields": ("shiprocket_order_id", "shiprocket_shipment_id", "awb_code")
        }),

        ("Status", {
            "fields": ("status",)
        }),
    )

    def order_status_display(self, obj):
        return obj.get_status_display()

    order_status_display.short_description = "Order Status"


# =========================
# RETURN ADMIN
# =========================
@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "item",
        "status",
        "quantity",
        "refund_amount",
        "return_waybill",
        "created_at",
        "refunded_at",
    )

    list_filter = (
        "status",
        "courier_name",
    )

    search_fields = (
        "order__order_code",
        "item__product__name",
        "return_waybill",
    )

    readonly_fields = (
        "order",
        "item",
        "reason",
        "quantity",
        "courier_name",
        "return_waybill",
        "refund_amount",
        "status",
        "created_at",
        "approved_at",
        "pickup_scheduled_at",
        "picked_up_at",
        "received_at",
        "refunded_at",
    )

    actions = ["approve_return"]

    def approve_return(self, request, queryset):

        from orders.delhivery import create_return_shipment

        for ret in queryset:

            if ret.status == "requested":

                ret.status = "approved"
                ret.approved_at = timezone.now()
                ret.save()

                try:
                    create_return_shipment(ret)
                except Exception as e:
                    self.message_user(
                        request,
                        f"Pickup error: {e}",
                        level="error"
                    )

                ret.refund_amount = ret.item.price * ret.quantity
                ret.status = "refunded"
                ret.refunded_at = timezone.now()
                ret.save()

                ret.order.recalculate_totals()

        self.message_user(request, "Return processed successfully.")

    approve_return.short_description = "Approve & Refund Return"