# shipping/services/courier_logic.py

def select_best_courier(couriers):
    # Smart production logic
    # Priority: delivery time → rating → price

    couriers = sorted(
        couriers,
        key=lambda x: (
            x["estimated_delivery_days"],
            -x["rating"],
            x["rate"]
        )
    )

    return couriers[0]