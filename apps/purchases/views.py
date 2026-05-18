from turtle import mode

from apps.core.models import BillItem
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
import json
from decimal import Decimal, InvalidOperation
from apps.core.models import Bill, Company
from django.contrib import messages
from apps.core.models import Product, Supplier
from apps.purchases.models import Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem,SupplierPayment,PaymentAllocation
from django.db.models import Sum
import pandas as pd
from num2words import num2words
from django.http import HttpResponse
from decimal import ROUND_HALF_UP
from apps.core.models import Product, Supplier, Company, BankAccount, BankTransaction
from apps.core.models import Customer

def number_to_words(n):
    from num2words import num2words
    return num2words(n, to='cardinal', lang='en').title()
# ================= PURCHASE PAGE =================

@login_required
def purchase(request):

    suppliers = Supplier.objects.all().order_by("name")

    customers = Customer.objects.all().order_by("name")

    return render(
        request,
        "transactions/transaction.html",
        {
            "mode": "purchase",
            "suppliers": suppliers,
            "customers": customers
        }
    )


@login_required
@transaction.atomic
def update_purchase(request, id):

    purchase = Purchase.objects.get(id=id)

    data = json.loads(request.body)
    items = data.get("items", [])
    discount = Decimal(str(data.get("discount", 0)))
    apply_gst = data.get("apply_gst", True)

    # 🔥 OLD STOCK REVERT
    for item in purchase.items.all():
        product = item.product
        product.stock -= item.qty
        product.save()

    purchase.items.all().delete()

    subtotal = Decimal("0.00")

    for item in items:
        product_id = int(item.get("product_id", 0))

        qty = int(item.get("qty", 0))
        print("PRODUCT ID:", product_id)
        print("QTY:", qty)
        product = Product.objects.get(id=product_id)

        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            qty=qty,
            price=product.price
        )

        product.stock += qty
        product.save()

        subtotal += Decimal(qty) * product.price

    gst = subtotal * Decimal("0.18") if apply_gst else Decimal("0.00")

    gross_total = subtotal + gst - discount

    rounded_total = gross_total.quantize(
    Decimal("1"),
    rounding=ROUND_HALF_UP
    )

    roundoff = rounded_total - gross_total

    purchase.subtotal = subtotal
    purchase.cgst = gst / 2
    purchase.sgst = gst / 2
    purchase.discount = discount
    purchase.roundoff = roundoff
    purchase.total = discount
    purchase.total = rounded_total

    purchase.save()

    return JsonResponse({
        "status": "success",
        "purchase_id": purchase.id
    })
@login_required
def purchase_preview(request, id):

    purchase = Purchase.objects.get(id=id)

    amount_words = number_to_words(int(purchase.total))

    return render(request, "dashboard/bill_preview.html", {
        "purchase": purchase,
        "amount_words": amount_words,
        "mode": "purchase"
    })
@login_required
def purchase_edit(request,id):
    purchase = Purchase.objects.get(id=id)

    if purchase.payment_mode != "credit" or purchase.balance <= 0:
     return redirect("purchase_invoices")
    purchase = Purchase.objects.get(id=id)
    suppliers = Supplier.objects.all()

    return render(request,"purchases/purchase.html",{
        "edit_purchase":purchase,
        "suppliers":suppliers
    })

@login_required
def purchase_delete(request, id):

    purchase = Purchase.objects.get(id=id)
    if purchase.payment_mode != "credit" or purchase.balance <= 0:
     return redirect("purchase_invoices")
    supplier = purchase.supplier
    if purchase.payment_mode == "credit":
     supplier.balance -= purchase.total
     supplier.save()

    purchase.delete()

    return redirect("purchase_invoices")

@login_required
def purchase_return_print(request, id):

    pr = PurchaseReturn.objects.get(id=id)

    company = Company.objects.first()

    subtotal = Decimal("0.00")

    # 🔥 RECALCULATE FROM ITEMS
    for item in pr.items.all():

        subtotal += (
            Decimal(item.qty) *
            Decimal(item.price)
        )

    # GST
    gst = (
        subtotal * Decimal("0.18")
    ).quantize(Decimal("0.01"))

    cgst = (
        gst / Decimal("2")
    ).quantize(Decimal("0.01"))

    sgst = (
        gst / Decimal("2")
    ).quantize(Decimal("0.01"))

    grand_total = (
        subtotal + gst
    ).quantize(Decimal("0.01"))

    # 🔥 SAVE VALUES
    pr.subtotal = subtotal
    pr.cgst = cgst
    pr.sgst = sgst
    pr.total = grand_total
    pr.save()
    pr.refresh_from_db()

    # WORDS
    amount_words = number_to_words(
        int(grand_total)
    )

    return render(
        request,
        "purchases/purchase_return_invoice.html",
        {
            "return": pr,
            "purchase": pr.purchase,
            "company": company,

            # 🔥 TEMPLATE VALUES
            "subtotal": subtotal,
            "cgst": cgst,
            "sgst": sgst,
            "total": grand_total,

            "amount_words": amount_words
        }
    )

@login_required
def return_print(request, mode, id):

    company = Company.objects.first()

    if mode == "sales":

        sr = PurchaseReturn.objects.get(id=id)

        # 🔥 RECALCULATE
        subtotal = Decimal("0.00")

        for item in sr.items.all():
            subtotal += Decimal(item.qty) * Decimal(item.price)

        gst = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"))

        cgst = (gst / 2).quantize(Decimal("0.01"))
        sgst = (gst / 2).quantize(Decimal("0.01"))

        total = (subtotal + gst).quantize(Decimal("0.01"))

        # 🔥 SAVE
        sr.subtotal = subtotal
        sr.cgst = cgst
        sr.sgst = sgst
        sr.total = total
        sr.save()

        amount_words = number_to_words(int(total))

        return render(
            request,
            "purchases/purchase_return_invoice.html",
            {
                "return": sr,
                "purchase": sr.bill,
                "company": company,
                "subtotal": subtotal,
                "cgst": cgst,
                "sgst": sgst,
                "total": total,
                "amount_words": amount_words,
                "mode": "sales"
            }
        )

    else:

     pr = PurchaseReturn.objects.get(id=id)

    subtotal = Decimal("0.00")

    for item in pr.items.all():

        subtotal += (
            Decimal(item.qty) *
            Decimal(item.price)
        )

    gst = (
        subtotal * Decimal("0.18")
    ).quantize(Decimal("0.01"))

    cgst = (
        gst / Decimal("2")
    ).quantize(Decimal("0.01"))

    sgst = (
        gst / Decimal("2")
    ).quantize(Decimal("0.01"))

    total = (
        subtotal + gst
    ).quantize(Decimal("0.01"))

    pr.subtotal = subtotal
    pr.cgst = cgst
    pr.sgst = sgst
    pr.total = total
    pr.save()

    amount_words = number_to_words(int(total))

    return render(
        request,
        "purchases/purchase_return_invoice.html",
        {
            "return": pr,
            "purchase": pr.purchase,
            "company": company,

            "subtotal": subtotal,
            "cgst": cgst,
            "sgst": sgst,
            "total": total,

            "amount_words": amount_words,

            "mode": "purchase"
        }
    )

def get_transactions(request):

    mode = request.GET.get("mode")
    party_id = request.GET.get("party_id")

    data = []

    if mode == "sales":

        bills = Bill.objects.filter(customer_id=party_id)

        for b in bills:

            data.append({
                "id": b.id,
                "invoice_number": b.invoice_no,
                "total": float(b.total)
            })

    else:

        purchases = Purchase.objects.filter(supplier_id=party_id)

        for p in purchases:

            data.append({
                "id": p.id,
                "invoice_number": p.invoice_number,
                "total": float(p.total)
            })

    return JsonResponse(data, safe=False)

def get_items(request):
    from apps.core.models import BillItem 
    mode = request.GET.get("mode")
    transaction_id = request.GET.get("transaction_id")

    data = []

    if mode == "sales":

        items = BillItem.objects.filter(bill_id=transaction_id)

    else:

        items = PurchaseItem.objects.filter(
            purchase_id=transaction_id
        )

    for i in items:

        data.append({
            "id": i.product.id,
            "name": i.product.name,
            "price": float(i.price),
            "qty": i.qty
        })

    return JsonResponse(data, safe=False)

@login_required
def get_return_info(request):

    from django.http import JsonResponse
    from django.db.models import Sum

    purchase_id = request.GET.get("purchase_id")
    product_id = request.GET.get("product_id")

    mode = request.GET.get("mode", "purchase")

    # =========================
    # PURCHASE / SALES
    # =========================

    if mode == "sales":

        purchase = Bill.objects.get(id=purchase_id)

    else:

        purchase = Purchase.objects.get(id=purchase_id)

    # =========================================
    # 🔥 CASE 1 → INVOICE LEVEL
    # =========================================

    if not product_id:

        data = []

        if mode == "sales":

            items = BillItem.objects.filter(
                bill=purchase
            )

        else:

            items = PurchaseItem.objects.filter(
                purchase=purchase
            )

        for item in items:

            if mode == "sales":

                returned = PurchaseReturnItem.objects.filter(
                    purchase_return__bill=purchase,
                    product=item.product
                ).aggregate(total=Sum("qty"))["total"] or 0

            else:

                returned = PurchaseReturnItem.objects.filter(
                    purchase_return__purchase=purchase,
                    product=item.product
                ).aggregate(total=Sum("qty"))["total"] or 0

            remaining = item.qty - returned

            data.append({
                "product_id": item.product.id,
                "name": item.product.name,
                "qty": item.qty,
                "returned": returned,
                "remaining": remaining,
                "has_return": returned > 0
            })

        return JsonResponse({
            "items": data,
            "invoice": (
                purchase.invoice_no
                if mode == "sales"
                else purchase.invoice_number
            )
        })

    # =========================================
    # 🔥 CASE 2 → PRODUCT LEVEL (MODAL)
    # =========================================

    if mode == "sales":

        items = PurchaseReturnItem.objects.filter(
            purchase_return__bill=purchase,
            product__id=product_id
        ).select_related("purchase_return")

    else:

        items = PurchaseReturnItem.objects.filter(
            purchase_return__purchase=purchase,
            product__id=product_id
        ).select_related("purchase_return")

    total_qty = 0
    total_amount = Decimal("0.00")
    history = []

    for i in items:

        line_total = i.qty * i.price
        gst = line_total * Decimal("0.18")
        grand = line_total + gst

        total_qty += i.qty
        total_amount += grand

        history.append({
            "date": i.purchase_return.date.strftime("%d %b %Y"),
            "qty": i.qty,
            "price": float(i.price),
            "amount": float(grand),
            "return_id": i.purchase_return.id
        })

    return JsonResponse({
        "returned": total_qty,
        "returned_amount": float(total_amount),
        "history": history
    })
 
@login_required
def creditors(request):

    if request.method == "POST":
        
        name = request.POST.get("name")
        phone = request.POST.get("phone")
        gst = request.POST.get("gst")
        address = request.POST.get("address")

        Supplier.objects.create(
            name=name,
            phone=phone,
            gst=gst,
            address=address
        )

        return redirect("creditors")

    suppliers = Supplier.objects.all().order_by("-id")

    return render(request, "purchases/creditors.html", {
        "suppliers": suppliers
    })

@login_required
def receivables(request):

    suppliers = Supplier.objects.all()
    data = []

    for s in suppliers:

        if mode == "purchase":
            purchases = Purchase.objects.filter(supplier=s)
        else:
            purchases = Bill.objects.filter(customer=s)

        receivable = Decimal("0.00")
        outstanding = Decimal("0.00")

        for p in purchases:

            # =========================
            # 💰 RETURN CALC
            # =========================
            return_amount = Decimal("0.00")

            returns = PurchaseReturnItem.objects.filter(
                purchase_return__purchase=p
            )

            for r in returns:
                line_total = Decimal(r.qty) * Decimal(r.price)
                gst = line_total * Decimal("0.18")
                return_amount += line_total + gst

            # =========================
            # 💰 PAYMENT
            # =========================
            if p.payment_mode in ["cash", "bank"]:
                paid = p.total
            else:
                paid = p.paid_amount or Decimal("0.00")

            # =========================
            # 🧠 LOGIC
            # =========================
            if p.payment_mode in ["credit", "partial"]:

                balance = p.total - paid - return_amount

                if balance > 0:
                    outstanding += balance
                elif balance < 0:
                    receivable += abs(balance)

            else:
                # cash/bank return → receivable
                receivable += return_amount

        # =========================
        # 🔥 NET CALC
        # =========================
        net = receivable - outstanding

        data.append({
            "id": s.id,
            "name": s.name,
            "receivable": round(receivable, 2),
            "outstanding": round(outstanding, 2),
            "net": round(net, 2)
        })

    return render(request, "purchases/receivables.html", {
        "data": data
    })



@login_required
@transaction.atomic
def purchase_return(request, mode="purchase"):

    from decimal import Decimal
    from django.contrib import messages
    from django.shortcuts import redirect, render
    from django.db.models import Sum
    import json
    import traceback

    # ==================================================
    # PARTIES
    # ==================================================
    if mode == "sales":

        parties = Customer.objects.all().order_by("name")

    else:

        parties = Supplier.objects.all().order_by("name")

    # ==================================================
    # SAVE RETURN
    # ==================================================
    if request.method == "POST":
        print("POST DATA:", request.POST.dict())
        try:

            purchase_id = request.POST.get("purchase_id")
            items_data = request.POST.get("items_data")

            print("\n====================")
            print("🔥 RETURN SAVE START")
            print("====================")

            print("MODE:", mode)
            print("PURCHASE ID:", purchase_id)
            print("ITEMS RAW:", items_data)

            # ==================================================
            # SAFETY
            # ==================================================
            if not purchase_id or not items_data:

                print("❌ EMPTY PURCHASE OR ITEMS")

                redirect_url = (
                    "/sales-return/"
                    if mode == "sales"
                    else "/debit-note/"
                )

                return redirect(redirect_url)

            # ==================================================
            # GET TRANSACTION
            # ==================================================
            if mode == "sales":

                purchase = Bill.objects.get(
                    id=int(purchase_id)
                )

            else:

                purchase = Purchase.objects.get(
                    id=int(purchase_id)
                )

            print("✅ PURCHASE FOUND")

            # ==================================================
            # PARSE ITEMS
            # ==================================================
            items = json.loads(items_data)

            print("PARSED ITEMS:", items)

            valid_items = []

            for i in items:

                try:
                    product_id = int(i.get("product_id", 0))
                    qty = int(i.get("qty", 0))

                    if product_id > 0 and qty > 0:

                        valid_items.append({
                            "product_id": product_id,
                            "qty": qty
                        })

                except Exception as e:

                    print("❌ VALID ITEM ERROR:", e)


            # ==================================================
            # EMPTY CHECK
            # ==================================================
            if not valid_items:

                print("❌ NO VALID ITEMS")

                messages.error(
                    request,
                    "Please select at least one item ❌"
                )

                redirect_url = (
                    "/sales-return/"
                    if mode == "sales"
                    else "/debit-note/"
                )

                return redirect(redirect_url)

            # ==================================================
            # CREATE RETURN
            # ==================================================
            if mode == "sales":

                pr = PurchaseReturn.objects.create(
                    bill=purchase
                )

            else:

                pr = PurchaseReturn.objects.create(
                    purchase=purchase
                )

            print("✅ RETURN CREATED:", pr.id)

            subtotal = Decimal("0.00")
            total_gst = Decimal("0.00")

            # ==================================================
            # ITEMS LOOP
            # ==================================================
            for item in valid_items:

                try:

                    product_id = int(item["product_id"])
                    qty = int(item["qty"])

                    if qty <= 0:
                        continue

                    # ================= PRODUCT =================
                    product = Product.objects.get(
                        id=product_id
                    )

                    print("PRODUCT:", product.name)

                    # ================= ITEM =================
                    if mode == "sales":

                        purchase_item = BillItem.objects.filter(
                            bill=purchase,
                            product=product
                        ).first()

                        if not purchase_item:

                            print("❌ BILL ITEM NOT FOUND")

                            continue

                    else:

                        purchase_item = PurchaseItem.objects.filter(
                            purchase=purchase,
                            product=product
                        ).first()

                        if not purchase_item:

                            print("❌ PURCHASE ITEM NOT FOUND")

                            continue

                    # ==================================================
                    # RETURNED QTY
                    # ==================================================
                    if mode == "sales":

                        returned = PurchaseReturnItem.objects.filter(
                            purchase_return__bill=purchase,
                            product=product
                        ).aggregate(
                            total=Sum("qty")
                        )["total"] or 0

                    else:

                        returned = PurchaseReturnItem.objects.filter(
                            purchase_return__purchase=purchase,
                            product=product
                        ).aggregate(
                            total=Sum("qty")
                        )["total"] or 0

                    remaining = (
                        purchase_item.qty - returned
                    )

                    print(
                        "ITEM:",
                        product.name,
                        "| PURCHASE:",
                        purchase_item.qty,
                        "| RETURNED:",
                        returned,
                        "| REMAINING:",
                        remaining,
                        "| NEW:",
                        qty
                    )

                    # ==================================================
                    # VALIDATION
                    # ==================================================
                    if qty > remaining:

                        print("❌ EXCEEDS REMAINING")

                        messages.error(
                            request,
                            f"{product.name} exceeds remaining qty ❌"
                        )

                        redirect_url = (
                            "/sales-return/"
                            if mode == "sales"
                            else "/debit-note/"
                        )

                        return redirect(redirect_url)

                    # ==================================================
                    # CALCULATION
                    # ==================================================
                    line_total = (
                        Decimal(qty) *
                        Decimal(purchase_item.price)
                    )

                    gst = (
                        line_total *
                        Decimal("0.18")
                    )

                    # ==================================================
                    # SAVE ITEM
                    # ==================================================
                    PurchaseReturnItem.objects.create(
                        purchase_return=pr,
                        product=product,
                        qty=qty,
                        price=purchase_item.price
                    )

                    print("✅ ITEM SAVED")

                    # ==================================================
                    # STOCK UPDATE
                    # ==================================================
                    if mode == "sales":

                        product.stock += qty

                    else:

                        product.stock -= qty

                    product.save()

                    subtotal += line_total
                    total_gst += gst

                except Exception as e:

                    print("❌ ITEM LOOP ERROR")
                    traceback.print_exc()

            # ==================================================
            # TOTALS
            # ==================================================
            grand_total = (
                subtotal + total_gst
            ).quantize(Decimal("0.01"))

            pr.subtotal = subtotal

            pr.cgst = (
                total_gst / 2
            ).quantize(Decimal("0.01"))

            pr.sgst = (
                total_gst / 2
            ).quantize(Decimal("0.01"))

            pr.total = grand_total

            pr.save()

            print("✅ TOTAL SAVED:", grand_total)

            # ==================================================
            # SUPPLIER BALANCE
            # ==================================================
            if mode != "sales":

                purchase.supplier.balance -= grand_total
                purchase.supplier.save()

            # ==================================================
            # SUCCESS MESSAGE
            # ==================================================
            # if mode == "sales":

            #     messages.success(
            #         request,
            #         "Sales Return Saved Successfully ✅"
            #     )

            # else:

            #     messages.success(
            #         request,
            #         "Purchase Return Saved Successfully ✅"
            #     )

            # print("✅ SUCCESS REDIRECT")

            # ==================================================
            # PRINT REDIRECT
            # ==================================================
            return redirect(
                f"/return/print/{mode}/{pr.id}/"
            )

        except Exception as e:

            print("\n❌ FULL ERROR")
            traceback.print_exc()

            messages.error(
                request,
                f"ERROR: {str(e)}"
            )

            redirect_url = (
                "/sales-return/"
                if mode == "sales"
                else "/debit-note/"
            )

            return redirect(redirect_url)

    # ==================================================
    # NORMAL LOAD
    # ==================================================
    return render(
        request,
        "purchases/purchase_return.html",
        {
            "parties": parties,
            "mode": mode
        }
    )
@login_required
def purchase_invoices(request):

    supplier_id = request.GET.get("supplier_id")
    supplier = None

    if supplier_id:
        purchases = Purchase.objects.filter(
            supplier_id=supplier_id
        ).order_by("-date")

        supplier = get_object_or_404(Supplier, id=supplier_id)

    else:
        purchases = Purchase.objects.all().order_by("-date")

    for p in purchases:

        # =========================
        # 🔁 RETURN CHECK
        # =========================
        total_qty = p.items.aggregate(total=Sum("qty"))["total"] or 0

        returned_qty = PurchaseReturnItem.objects.filter(
            purchase_return__purchase=p
        ).aggregate(total=Sum("qty"))["total"] or 0

        p.is_fully_returned = returned_qty >= total_qty and total_qty > 0

        # =========================
        # 💰 RETURN AMOUNT
        # =========================
        total_return = Decimal("0.00")

        returns = PurchaseReturnItem.objects.filter(
            purchase_return__purchase=p
        )

        for r in returns:
            line_total = Decimal(r.qty) * Decimal(r.price)
            gst = line_total * Decimal("0.18")
            total_return += line_total + gst

        # =========================
        # 💰 FIXED PAYMENT LOGIC
        # =========================
        if p.payment_mode in ["cash", "bank"]:
            paid = p.total   # 🔥 FIX
        else:
            paid = p.paid_amount or Decimal("0.00")

        # =========================
        # 💰 CORRECT BALANCE
        # =========================
        correct_balance = p.total - paid - total_return

        # =========================
        # 💚 RECEIVABLE
        # =========================
        if correct_balance < 0:
            p.receivable = abs(correct_balance)
        else:
            p.receivable = 0

        # =========================
        # 💰 STATUS
        # =========================
        if p.payment_mode == "credit":

            if paid == 0:
                p.status = "CREDIT"

            elif correct_balance > 0:
                p.status = "PARTIAL"

            else:
                p.status = "PAID"

        else:
            p.status = p.payment_mode.upper()

    return render(request, "purchases/purchase_invoices.html", {
    "purchases": purchases,
    "party": supplier,
    "mode": "purchase"
})

def supplier_balance(request):
    supplier_id = request.GET.get("supplier_id")

    if not supplier_id:
        return JsonResponse({"balance": 0})

    supplier = Supplier.objects.get(id=supplier_id)

    # ✅ ONLY CREDIT PURCHASES
    purchases = Purchase.objects.filter(
        supplier=supplier,
        payment_mode="credit"
    )

    total_balance = 0

    for p in purchases:
        total_balance += p.balance

    return JsonResponse({
        "balance": float(total_balance)
    })

def creditor_detail(request, id):

    supplier = Supplier.objects.get(id=id)

    purchases = Purchase.objects.filter(supplier=supplier,payment_mode="credit")

    data = []
    total_balance = 0

    for p in purchases:
        balance = p.balance
        if balance > 0:
            data.append({
            "id": p.id,
            "invoice": p.invoice_number,
            "total": float(p.total),
            "paid": 0,
            "balance": float(p.total)
        })
        total_balance += balance
    return JsonResponse({
        "supplier": supplier.name,
        "balance": float(total_balance),
        "purchase": data
    })

@login_required
@transaction.atomic
def save_purchase(request):

    try:
        data = json.loads(request.body)

        items = data.get("items", [])
        supplier_id = data.get("supplier_id")
        payment_mode = data.get("payment_mode", "cash")
        discount = Decimal(str(data.get("discount", 0)))
        apply_gst = data.get("apply_gst", True)
        if not items:
            return JsonResponse({"status": "error", "message": "Cart empty"})

        if not supplier_id:
            return JsonResponse({"status": "error", "message": "Supplier required"})

        supplier = Supplier.objects.get(id=supplier_id)

        # ==============================
        # CREATE PURCHASE
        # ==============================
        purchase = Purchase.objects.create(
            supplier=supplier,
            invoice_number="PUR" + str(Purchase.objects.count() + 1),
            payment_mode=payment_mode
        )

        subtotal = Decimal("0.00")

        # ==============================
        # ITEMS LOOP
        # ==============================
        for item in items:

            product = Product.objects.get(id=item["product_id"])
            qty = int(item["qty"])
            price = product.price

            if qty <= 0:
                continue

            PurchaseItem.objects.create(
                purchase=purchase,
                product=product,
                qty=qty,
                price=price
            )

            product.stock += qty
            product.save()

            subtotal += Decimal(qty) * price

        # ==============================
        # GST CALCULATION
        # ==============================
        gst = subtotal * Decimal("0.18") if apply_gst else Decimal("0.00")

        total_before_round = subtotal + gst - discount

        rounded_total = total_before_round.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP
)

        roundoff = rounded_total - total_before_round

        rounded_total = total_before_round.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        roundoff = rounded_total - total_before_round

        # SAVE PURCHASE
        purchase.subtotal = subtotal
        purchase.cgst = gst / 2
        purchase.sgst = gst / 2
        purchase.discount = discount
        purchase.roundoff = roundoff
        purchase.total = rounded_total
        purchase.save()

        # ==============================
        # 🔥 PAYMENT LOGIC (FINAL FIX)
        # ==============================

        if payment_mode == "credit":
            supplier.balance += purchase.total
            supplier.save()

        elif payment_mode in ["cash", "bank"]:

            # 🔥 CREATE PAYMENT (AUTO)
            payment = SupplierPayment.objects.create(
                supplier=supplier,
                amount=purchase.total,
                note=f"Auto payment for {purchase.invoice_number}"
            )

            # 🔥 LINK TO PURCHASE
            PaymentAllocation.objects.create(
                payment=payment,
                purchase=purchase,
                amount=purchase.total
            )

            # BANK ENTRY
            if payment_mode == "bank":
                bank = BankAccount.objects.first()

                if bank:
                    BankTransaction.objects.create(
                        bank=bank,
                        amount=purchase.total,
                        type="debit",
                        description=f"Purchase {purchase.invoice_number}"
                    )

                    bank.balance -= purchase.total
                    bank.save()

        return JsonResponse({
            "status": "success",
            "purchase_id": purchase.id
        })

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        })
@transaction.atomic
def supplier_payment(request):

    suppliers = Supplier.objects.all()
    allocations = None

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        amount = Decimal(request.POST.get("amount"))
        note = request.POST.get("note")

        supplier = Supplier.objects.get(id=supplier_id)

        payment = SupplierPayment.objects.create(
            supplier=supplier,
            amount=amount,
            note=note,
            payment_type="pay"
        )

        # 🔥 AUTO ALLOCATION
        remaining = amount

        purchases = Purchase.objects.filter(
            supplier=supplier,
            payment_mode="credit"
        ).order_by("date")

        for p in purchases:

            balance = p.balance

            if balance <= 0:
                continue

            if remaining <= 0:
                break

            pay_amount = min(balance, remaining)

            PaymentAllocation.objects.create(
                payment=payment,
                purchase=p,
                amount=pay_amount
            )

            remaining -= pay_amount

        # 🔥 IMPORTANT: allocations fetch karo
        allocations = PaymentAllocation.objects.filter(payment=payment)

    return render(request, "purchases/payment.html", {
        "suppliers": suppliers,
        "allocations": allocations
    })

def bulk_purchase_upload(request):

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request"})

    file = request.FILES.get("file")

    if not file:
        return JsonResponse({"status": "error", "message": "No file uploaded"})

    try:
        # ================= READ FILE =================
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        df.columns = df.columns.str.strip().str.lower()

        print("Columns:", df.columns)

        items = []

        # ================= LOOP =================
        for _, row in df.iterrows():

            try:
                part_no = str(row.get("part #", "")).strip()
                name = str(row.get("part description", "")).strip()
                qty = int(float(row.get("quantity", 0)))
                price = float(row.get("mrp", 0))

                # skip empty rows
                if not part_no and not name:
                    continue

                # ================= FIND PRODUCT =================
                product = Product.objects.filter(barcode=part_no).first()

                if not product:
                    product = Product.objects.filter(name__icontains=name).first()

                # ================= CREATE IF NOT FOUND =================
                if not product:
                    product = Product.objects.create(
                        name=name,
                        barcode=part_no,
                        price=price,   # store MRP
                        stock=0
                    )

                # ================= DUPLICATE MERGE =================
                existing = next((i for i in items if i["product_id"] == product.id), None)

                if existing:
                    existing["qty"] += qty
                    existing["value"] = existing["qty"] * existing["price"]
                else:
                    items.append({
                        "product_id": product.id,
                        "name": product.name,
                        "qty": qty,
                        "price": price,                # MRP
                        "value": qty * price           # total
                    })

            except Exception as e:
                print("Row Error:", e)
                continue

        # ================= RESPONSE =================
        return JsonResponse({
            "status": "success",
            "items": items
        })

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        })
    
@login_required
def supplier_invoices_api(request, id):

    supplier = Supplier.objects.get(id=id)

    purchases = Purchase.objects.filter(
        supplier=supplier,
        payment_mode="credit"
    )

    data = []

    for p in purchases:
        balance = p.balance

        if balance > 0:  # 🔥 ONLY PENDING
            data.append({
                "invoice": p.invoice_number,
                "total": float(p.total),
                "paid": float(p.paid_amount),
                "balance": float(balance),
            })

    return JsonResponse({
        "bills": data
    })

@login_required
def purchase_ledger(request, id):

    purchase = Purchase.objects.get(id=id)

    allocations = PaymentAllocation.objects.filter(
        purchase=purchase
    ).order_by("payment__date")

    data = []

    for a in allocations:
        data.append({
            "id": a.id,
            "date": a.payment.date.strftime("%d %b %Y"),
            "amount": float(a.amount)
        })

    # ✅ 🔥 MAIN FIX (NO SIDE EFFECT)
    if purchase.payment_mode in ["cash", "bank"]:
        paid = purchase.total
        balance = 0
    else:
        paid = purchase.paid_amount
        balance = purchase.balance

    return JsonResponse({
        "invoice": purchase.invoice_number,
        "total": float(purchase.total),
        "paid": float(paid),
        "balance": float(balance),
        "payment_mode": purchase.status_display,
        "payments": data
    })

def payment_voucher(request, id):

    allocation = PaymentAllocation.objects.get(id=id)
    amount_words = num2words(int(allocation.amount), lang='en').title()
    payment = allocation.payment
    purchase = allocation.purchase
    supplier = payment.supplier
    company = Company.objects.first()

    return render(request, "purchases/payment_voucher.html", {
        "payment": payment,
        "purchase": purchase,
        "supplier": supplier,
        "amount": allocation.amount,
        "company": company, 
        "amount_words": amount_words
    })

def purchase_return_invoice(request, id):

    purchase = Purchase.objects.get(id=id)
    returns = PurchaseReturn.objects.filter(purchase=purchase).order_by("-date").first()

    return render(request, "purchases/purchase_return_invoice.html", {
        "purchase": purchase,
        "return": returns
    })

@login_required
def receive_payment(request, supplier_id):

    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == "POST":
        try:
            raw_amount = request.POST.get("amount")

            if not raw_amount:
                return HttpResponse("Amount missing ❌")

            amount = Decimal(raw_amount)

            # ✅ Create payment
            payment = SupplierPayment.objects.create(
                supplier=supplier,
                amount=amount,
                payment_type="receive"
            )

            remaining = amount

            # ✅ GET ALL CREDIT PURCHASES
            purchases = Purchase.objects.filter(
                supplier=supplier,
                payment_mode__in=["credit", "partial"]
            ).order_by("date")

            # 🔥 AUTO ADJUST
            for p in purchases:

                # current balance
                paid = p.paid_amount or Decimal("0.00")

                # calculate return
                return_amount = Decimal("0.00")
                returns = PurchaseReturnItem.objects.filter(
                    purchase_return__purchase=p
                )

                for r in returns:
                    line_total = Decimal(r.qty) * Decimal(r.price)
                    gst = line_total * Decimal("0.18")
                    return_amount += line_total + gst

                balance = p.total - paid - return_amount

                if balance <= 0:
                    continue

                if remaining <= 0:
                    break

                pay_amount = min(balance, remaining)

                # ✅ CREATE ALLOCATION
                PaymentAllocation.objects.create(
                    payment=payment,
                    purchase=p,
                    amount=pay_amount
                )

                # ✅ UPDATE PAID
                p.paid_amount = paid + pay_amount
                p.save()

                remaining -= pay_amount

            return redirect("print_receipt", payment.id)

        except InvalidOperation:
            return HttpResponse("Invalid amount ❌")

        except Exception as e:
            return HttpResponse(f"ERROR: {str(e)}")

    return render(request, "purchases/receive_payment.html", {
        "supplier": supplier
    })

@login_required
def print_receipt(request, payment_id):

    payment = get_object_or_404(SupplierPayment, id=payment_id)

    return render(request, "purchases/print_receipt.html", {
        "payment": payment
    })

