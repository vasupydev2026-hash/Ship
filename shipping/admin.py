from django.contrib import admin
from django.utils.html import format_html
from .models import Shipment, ShipmentEvent
from .tasks import process_shipping


# 🔹 Inline for Timeline (VERY IMPORTANT)
class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    readonly_fields = ("status", "description", "created_at")
    can_delete = False
    ordering = ("-created_at",)


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):

    # =========================================================
    # 📋 TABLE VIEW
    # =========================================================
    list_display = (
        "id",
        "order",
        "shipment_id",
        "courier_name",
        "awb_code",
        "status_badge",
        "tracking_button",
        "created_at",
    )

    list_filter = ("status", "courier_name", "created_at")

    search_fields = (
        "order__id",
        "shipment_id",
        "awb_code",
        "courier_name",
    )

    ordering = ("-created_at",)

    # =========================================================
    # 🔒 READONLY
    # =========================================================
    readonly_fields = (
        "shiprocket_order_id",
        "shipment_id",
        "awb_code",
        "tracking_url",
        "created_at",
        "tracking_link",   # 👈 NEW
    )

    # =========================================================
    # 📦 FORM LAYOUT
    # =========================================================
    fieldsets = (
        ("Order Info", {
            "fields": ("order",)
        }),
        ("Shiprocket", {
            "fields": ("shiprocket_order_id", "shipment_id")
        }),
        ("Courier", {
            "fields": ("courier_name", "courier_id")
        }),
        ("Tracking", {
            "fields": ("awb_code", "tracking_url", "tracking_link", "status")
        }),
        ("Time", {
            "fields": ("created_at",)
        }),
    )

    # =========================================================
    # 📊 TIMELINE (INLINE EVENTS)
    # =========================================================
    inlines = [ShipmentEventInline]

    # =========================================================
    # 🎨 UI FEATURES
    # =========================================================

    # 🔹 Status badge
    def status_badge(self, obj):
        colors = {
            "created": "#6c757d",
            "assigned": "#007bff",
            "shipped": "#fd7e14",
            "delivered": "#28a745",
            "failed": "#dc3545",
        }
        color = colors.get(obj.status.lower(), "#000")

        return format_html(
            '<span style="color:white; padding:5px 10px; border-radius:6px; background:{};">{}</span>',
            color,
            obj.status.upper()
        )

    status_badge.short_description = "Status"

    # 🔹 Button in list view
    def tracking_button(self, obj):
        if obj.awb_code:
            return format_html(
                '<a href="/shipping/track/{}/" target="_blank" '
                'style="color:white;background:#28a745;padding:6px 12px;border-radius:6px;">Track</a>',
                obj.awb_code
            )
        return "-"
    tracking_button.short_description = "Tracking"

    # 🔹 Link inside detail page (NEW)
    def tracking_link(self, obj):
        if obj.awb_code:
            return format_html(
                '<a href="/shipping/track/{}/" target="_blank">🔗 Open Tracking Page</a>',
                obj.awb_code
            )
        return "No tracking available"

    tracking_link.short_description = "Tracking Page"

    # =========================================================
    # 🔁 ADMIN ACTIONS (SAFE VERSION)
    # =========================================================

    actions = [
        "retry_shipping",
        "mark_as_failed",
        "mark_as_delivered",
    ]

    # 🔹 Retry shipping (SAFE: avoids duplicate)
    def retry_shipping(self, request, queryset):
        for shipment in queryset:
            if shipment.status == "delivered":
                continue  # ❌ skip delivered

            process_shipping.delay(shipment.order.id)

        self.message_user(request, "🔁 Shipping retry triggered!")

    retry_shipping.short_description = "🔁 Retry Shipping"

    # 🔹 Mark failed
    def mark_as_failed(self, request, queryset):
        for shipment in queryset:
            shipment.status = "failed"
            shipment.save()

            ShipmentEvent.objects.create(
                shipment=shipment,
                status="failed",
                description="Marked as failed from admin"
            )

        self.message_user(request, "❌ Marked as failed")

    mark_as_failed.short_description = "❌ Mark as Failed"

    # 🔹 Mark delivered
    def mark_as_delivered(self, request, queryset):
        for shipment in queryset:
            shipment.status = "delivered"
            shipment.save()

            ShipmentEvent.objects.create(
                shipment=shipment,
                status="delivered",
                description="Manually marked as delivered"
            )

        self.message_user(request, "✅ Marked as delivered")

    mark_as_delivered.short_description = "✅ Mark as Delivered"