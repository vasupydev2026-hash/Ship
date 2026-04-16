// ===============================
// INIT
// ===============================
document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    setupAddressDropdown();
    setupCheckout();
    updateCartSummary();
});


// ===============================
// 🔥 EVENT BINDING
// ===============================
function bindEvents() {

    // Quantity buttons (event delegation)
    document.addEventListener("click", async (e) => {
        const btn = e.target.closest(".qty-btn");
        if (!btn) return;

        const itemId = btn.dataset.id;
        const action = btn.classList.contains("increase") ? "increase" : "decrease";

        await updateCart(itemId, action);
    });

    // Select item checkbox
    document.querySelectorAll(".select-item").forEach(box => {
        box.addEventListener("change", updateCartSummary);
    });

    // Select all
    const selectAll = document.getElementById("select-all");
    if (selectAll) {
        selectAll.addEventListener("change", function () {
            document.querySelectorAll(".select-item")
                .forEach(cb => cb.checked = this.checked);
            updateCartSummary();
        });
    }
}


// ===============================
// ADDRESS DROPDOWN
// ===============================

function setupAddressDropdown() {
    const select = document.getElementById("selected_address");
    if (!select) return;

    const selected = select.querySelector(".selected-option");
    const options = select.querySelector(".options");
    const hiddenInput = document.getElementById("selected_address_input");

    selected.addEventListener("click", (e) => {
        e.stopPropagation();
        options.style.display =
            options.style.display === "block" ? "none" : "block";
    });

    options.querySelectorAll(".option").forEach(option => {
        option.addEventListener("click", () => {
            selected.innerHTML = option.innerHTML;
            hiddenInput.value = option.dataset.id;
            options.style.display = "none";
        });
    });

    document.addEventListener("click", (e) => {
        if (!select.contains(e.target)) {
            options.style.display = "none";
        }
    });
}


// ===============================
// UPDATE CART (AJAX)
// ===============================
// ===============================
// UPDATE CART (AJAX) — FIXED
// ===============================
async function updateCart(itemId, action) {
    try {
        const response = await fetch(`/cart/update-cart/${itemId}/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCSRFToken()
            },
            body: JSON.stringify({ action })
        });

        const data = await response.json();

        // REMOVE ITEM
        if (data.removed) {
            document.querySelector(`#qty-${itemId}`)?.closest(".cart-item")?.remove();
            checkAndShowEmptyCart();
            updateCartSummary();
            return;
        }

        // UPDATE QTY
        const qtyEl = document.getElementById(`qty-${itemId}`);
        if (qtyEl) qtyEl.textContent = data.quantity;

        // UPDATE SUBTOTAL
        const subtotalEl = document.getElementById(`subtotal-${itemId}`);
        if (subtotalEl) {
            subtotalEl.textContent = formatCurrency(data.subtotal);
        }

        // UPDATE STOCK BUTTON
        const increaseBtn = document.querySelector(`.increase[data-id="${itemId}"]`);
        if (increaseBtn) {
            increaseBtn.disabled = data.quantity >= data.stock;
        }

        // ❌ REMOVE THIS BLOCK COMPLETELY (VERY IMPORTANT)
        // const checkbox = document.getElementById(`item-${itemId}`);
        // if (checkbox) {
        //     checkbox.dataset.cod = data.is_available_for_cod ? "true" : "false";
        // }

        // ✅ JUST RECALCULATE
        updateCartSummary();

    } catch (err) {
        console.error("Cart update error:", err);
    }
}
// ===============================
// 🔥 MAIN CALCULATION ENGINE
// ===============================
function updateCartSummary() {
    const checkboxes = document.querySelectorAll(".select-item");

    let total = 0;
    let totalItems = 0;
    let allCOD = true;

    checkboxes.forEach(box => {
        if (box.checked) {
            const id = box.dataset.id;

            const qty = parseInt(document.getElementById(`qty-${id}`).textContent || 0);

            const subtotalText = document.getElementById(`subtotal-${id}`).textContent;
            const subtotal = parseFloat(subtotalText.replace(/[^\d.]/g, "")) || 0;

            total += subtotal;
            totalItems += qty;

            if (box.dataset.cod !== "true") {
                allCOD = false;
            }
        }
    });

    const tax = (TAX_PERCENTAGE / 100) * total;
    const delivery = total >= FREE_DELIVERY_MIN ? 0 : DELIVERY_CHARGE;
    const grandTotal = total + tax + delivery;

    // ===============================
    // COD LOGIC
    // ===============================
    if (totalItems === 0) {
        disableCOD("Select at least one item");
    } else if (!allCOD) {
        disableCOD("Some items are not eligible for COD");
    } else {
        enableCOD();
    }

    // ===============================
    // UPDATE UI
    // ===============================
    document.getElementById("total-price").textContent = formatCurrency(total);
    document.getElementById("total-items").textContent = totalItems;
    document.getElementById("tax-amount").textContent = formatCurrency(tax);
    document.getElementById("delivery-charge").textContent = formatCurrency(delivery);
    document.getElementById("grand-total").textContent = formatCurrency(grandTotal);
}


// ===============================
// COD HELPERS
// ===============================
function disableCOD(message) {
    const cod = document.getElementById("payment-cod");
    const tooltip = document.getElementById("cod-tooltip");

    if (!cod) return;

    cod.disabled = true;
    cod.checked = false;

    if (tooltip) {
        tooltip.textContent = message;
        tooltip.classList.add("show");
    }
}

function enableCOD() {
    const cod = document.getElementById("payment-cod");
    const tooltip = document.getElementById("cod-tooltip");

    if (!cod) return;

    cod.disabled = false;

    if (tooltip) tooltip.classList.remove("show");
}


// ===============================
// CHECKOUT
// ===============================
function setupCheckout() {
    const checkoutButton = document.getElementById("checkout-button");
    if (!checkoutButton) return;

    checkoutButton.addEventListener("click", async function (e) {
        e.preventDefault();

        const selectedItems = getSelectedItemIDs();
        const addressInput = document.getElementById("selected_address_input");
        const paymentInput = document.querySelector('input[name="payment_method"]:checked');
        const codRadio = document.getElementById("payment-cod");

        // ===============================
        // VALIDATIONS
        // ===============================
        if (selectedItems.length === 0) {
            showWarning("✋ Please select at least one item.");
            return;
        }

        if (!addressInput || !addressInput.value) {
            showWarning("📍 Please select a delivery address.");
            return;
        }

        // 🔥 FIX: HANDLE COD DISABLED CASE
        if (!paymentInput) {

            // If COD is disabled → show correct message
            if (codRadio && codRadio.disabled) {
                showWarning("🚫 COD not available for selected items. Please choose online payment.");
            } else {
                showWarning("💳 Please select payment method.");
            }

            return;
        }

        // ===============================
        // API CALL
        // ===============================
        try {
            const response = await fetch("/orders/confirm_order/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCSRFToken(),
                },
                body: JSON.stringify({
                    selected_items: selectedItems,
                    selected_address: addressInput.value,
                    payment_method: paymentInput.value
                })
            });

            const data = await response.json();
            console.log("SERVER RESPONSE:", data);

            if (data.redirect_url) {
                window.location.href = data.redirect_url;
            } else {
                showWarning("❌ Something went wrong. Try again.");
            }

        } catch (err) {
            console.error("Checkout Error:", err);
            showWarning("❌ Order failed. Try again.");
        }
    });
}
// ===============================
// UTILITIES
// ===============================
function getSelectedItemIDs() {
    return Array.from(document.querySelectorAll(".select-item"))
        .filter(box => box.checked)
        .map(box => box.dataset.id);
}

function formatCurrency(amount) {
    return `₹${Number(amount).toFixed(2)}`;
}

function getCSRFToken() {
    return document.cookie
        .split(";")
        .map(c => c.trim())
        .find(c => c.startsWith("csrftoken="))
        ?.split("=")[1] || "";
}

function showWarning(msg) {
    const warning = document.getElementById("warning-message");
    if (warning) {
        warning.textContent = msg;
        warning.classList.add("show");
    }
}


// ===============================
// EMPTY CART
// ===============================
function checkAndShowEmptyCart() {
    if (document.querySelectorAll(".cart-item").length === 0) {
        document.querySelectorAll(".cart-layout").forEach(el => el.style.display = "none");
        document.getElementById("empty-cart-layout").style.display = "block";
    }
}