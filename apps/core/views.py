from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from .models import Company
from django.views.decorators.http import require_http_methods
from decimal import Decimal
from .models import Product, Bill, BillItem, Customer
import json
from .models import Expense, ExpenseCategory
from .models import SupplierPayment
from .models import BankAccount, BankTransaction
import math
from .models import Supplier, Purchase, PurchaseItem
from decimal import ROUND_HALF_UP
import csv
from io import TextIOWrapper
import openpyxl
from django.contrib import messages
from .models import PurchaseReturn, PurchaseReturnItem
from django.db.models import Sum
from datetime import date
from django.db.models import Q
from django.http import HttpResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import TableStyle
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph
from reportlab.lib.pagesizes import A4
from num2words import num2words
import pandas as pd
from django.http import JsonResponse
from .models import Product
from .models import PaymentAllocation, Purchase

def number_to_words(n):
    from num2words import num2words
    return num2words(n, to='cardinal', lang='en').title()

# ---------------- LOGIN ----------------

def login_view(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        # ✅ Basic validation (empty fields)
        if not username or not password:
            messages.error(request, "Please enter username and password ⚠️")
            return render(request, "login.html")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # ✅ success message (optional)
            request.session['login_success'] = True

            return redirect("dashboard")
        else:
            # ✅ better error message
            messages.error(request, "Invalid username or password ❌")

    return render(request, "login.html")


# ---------------- LOGOUT ----------------

def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------- SAVE BILL ----------------

@login_required
@transaction.atomic
def save_bill(request):

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    data = json.loads(request.body)

    items = data.get("items", [])
    discount = Decimal(data.get("discount", 0))
    apply_gst = data.get("apply_gst", True)
    paid = Decimal(data.get("paid", 0))

    if not items:
        return JsonResponse({"error": "No items in cart"}, status=400)

    # CUSTOMER
    customer_id = data.get("customer_id")

    if customer_id:
        customer = Customer.objects.get(id=customer_id)
    else:
        customer, _ = Customer.objects.get_or_create(name="Walk-in Customer")

    bill = Bill.objects.create(
        customer=customer,
        created_by=request.user
    )

    subtotal = Decimal("0.00")

    for item in items:

        product = Product.objects.get(id=item["product_id"])
        qty = Decimal(item["qty"])

        if product.stock < qty:
            return JsonResponse({
                "status": "error",
                "message": f"{product.name} is out of stock."
            }, status=400)

        price = product.price
        line_total = price * qty

        BillItem.objects.create(
            bill=bill,
            product=product,
            qty=qty,
            price=price
        )

        product.stock -= int(qty)
        product.save()

        subtotal += line_total

    # GST
    if apply_gst:
        total_gst = subtotal * Decimal("0.18")
    else:
        total_gst = Decimal("0.00")

    gross_total = subtotal + total_gst - discount

    rounded_total = gross_total.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    roundoff = rounded_total - gross_total

    # SAVE BILL TOTALS
    bill.subtotal = subtotal
    bill.cgst = total_gst / 2
    bill.sgst = total_gst / 2
    bill.discount = discount
    bill.roundoff = roundoff
    bill.total = rounded_total
    bill.save()

    # CUSTOMER BALANCE UPDATE
    remaining = rounded_total - paid

# Add remaining amount to customer balance
    customer.balance = customer.balance + remaining

    customer.save()

    return JsonResponse({
        "status": "success",
        "bill_id": bill.id
    })

# ---------------- SALES PAGE ----------------

@login_required
def sales_invoices(request):
    bills = Bill.objects.all().order_by("-date")
    return render(request, "dashboard/sales_invoices.html", {
        "bills": bills
    })


@login_required
def purchase_invoices(request):

    supplier_id = request.GET.get("supplier_id")

    if supplier_id:
        purchases = Purchase.objects.filter(
            supplier_id=supplier_id
        ).order_by("-date")
    else:
        purchases = Purchase.objects.all().order_by("-date")

    return render(request, "dashboard/purchase_invoices.html", {
        "purchases": purchases
    })

# ---------------- PRODUCTS ----------------

from django.db import IntegrityError

@login_required
def product_view(request):

    if request.method == "POST":
        try:
            name = request.POST.get("name")
            hsn = request.POST.get("hsn")
            price = request.POST.get("price")
            gst = request.POST.get("gst") or 18
            stock = request.POST.get("stock") or 0
            barcode = request.POST.get("barcode")  # ✅ added barcode support

            product, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    "hsn": hsn,
                    "price": price,
                    "gst": gst,
                    "stock": stock,
                    "barcode": barcode
                }
            )

            if not created:
                product.stock += int(stock)
                product.price = price
                product.gst = gst
                if barcode:
                    product.barcode = barcode
                product.save()

            messages.success(request, "Product Saved Successfully")
            return redirect("products")

        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect("products")

    products = Product.objects.all().order_by("-id")
    return render(request, "dashboard/products.html", {
        "products": products
    })


# ---------------- CUSTOMERS ----------------

@login_required
@require_http_methods(["GET", "POST"])
def customer_view(request):

    if request.method == "POST":
        name = request.POST.get("name")
        phone = request.POST.get("phone")
        address = request.POST.get("address")
        gst = request.POST.get("gst")

        Customer.objects.create(
            name=name,
            phone=phone,
            address=address,
            gst=gst

        )

        return redirect("customers")

    customers = Customer.objects.all().order_by("-id")

    return render(request, "dashboard/customers.html", {
        "customers": customers
    })


# ---------------- USERS (ADMIN ONLY) ----------------

@login_required
def user_view(request):

    if not request.user.is_superuser:
        return redirect("billing")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        role = request.POST.get("role")

        user = User.objects.create_user(
            username=username,
            password=password
        )

        if role == "admin":
            user.is_superuser = True
            user.is_staff = True
            user.save()

        return redirect("users")

    users = User.objects.all()
    return render(request, "dashboard/users.html", {
        "users": users
    })


# ---------------- INVOICE VIEW ----------------

@login_required
def generate_invoice(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    return render(request, "dashboard/invoice.html", {
        "bill": bill
    })


# ---------------- SCAN PRODUCT (FIXED) ----------------

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.http import require_http_methods
from decimal import Decimal, ROUND_HALF_UP
import json
import csv
from io import TextIOWrapper
import openpyxl


# ---------------- BILLING ----------------

@login_required
def billing(request):
    customers = Customer.objects.all().order_by("name")
    suppliers = Supplier.objects.all().order_by("name")

    return render(request, "dashboard/billing.html", {
        "customers": customers,
        "suppliers": suppliers
    })

# ---------------- BULK UPLOAD ----------------

@login_required
@transaction.atomic
def bulk_upload(request):

    if request.method == "POST":

        file = request.FILES.get("file")

        if not file:
            messages.error(request, "No file uploaded")
            return redirect("bulk_upload")

        try:

            if file.name.endswith(".csv"):
                csv_file = TextIOWrapper(file.file, encoding="utf-8")
                rows = csv.DictReader(csv_file)

            elif file.name.endswith(".xlsx"):
                wb = openpyxl.load_workbook(file)
                sheet = wb.active
                headers = [cell.value for cell in sheet[1]]
                rows = []
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    rows.append(dict(zip(headers, row)))

            else:
                messages.error(request, "Only CSV or Excel allowed")
                return redirect("bulk_upload")

            for row in rows:
                name = row["part description"]
                barcode = str(row["part #"]).strip()
                stock = int(row["quantity"] or 0)
                price = Decimal(row["mrp"] or 0)

                product, created = Product.objects.get_or_create(
                    barcode=barcode,
                    defaults={
                        "name": name,
                        "price": price,
                        "stock": stock,
                        "hsn": ""
                    }
                )

                if not created:
                    product.stock += stock
                    product.price = price
                    product.save()

            messages.success(request, "Bulk upload successful!")
            return redirect("products")

        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect("bulk_upload")

    return render(request, "dashboard/bulk_upload.html")


# ---------------- SCAN PRODUCT ----------------

@login_required
def scan_product(request):

    barcode = request.GET.get("barcode")

    if not barcode:
        return JsonResponse({"status": "error"})

    barcode = " ".join(barcode.strip().split())

    try:
        parts = barcode.split("/")
        part_code = parts[3].strip()
    except:
        return JsonResponse({"status": "error"})

    try:
        product = Product.objects.get(barcode__iexact=part_code)

        return JsonResponse({
            "status": "success",
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "stock": product.stock,
        })

    except Product.DoesNotExist:
        return JsonResponse({"status": "error"})
    

@login_required
def stock_receive(request):
    products = Product.objects.all()
    return render(request, "dashboard/stock_receive.html", {
        "products": products
    })


@login_required
@require_http_methods(["POST"])
def stock_scan(request):

    data = json.loads(request.body)
    barcode = data.get("barcode")

    if not barcode:
        return JsonResponse({"status": "error", "message": "No barcode received"})

    barcode = " ".join(barcode.strip().split())

    try:
        parts = barcode.split("/")
        part_code = parts[3].strip()
    except IndexError:
        return JsonResponse({"status": "error", "message": "Invalid barcode format"})

    try:
        product = Product.objects.get(barcode__iexact=part_code)

        return JsonResponse({
            "status": "success",
            "id": product.id,
            "name": product.name,
            "stock": product.stock
        })

    except Product.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Product not found"})

@login_required
@require_http_methods(["POST"])
def update_stock(request):

    data = json.loads(request.body)

    product_id = data.get("product_id")
    qty = int(data.get("qty"))
    mrp = float(data.get("mrp"))

    # Get product first
    product = Product.objects.get(id=product_id)

    # Update stock
    product.stock += qty

    # Update price (MRP change support)
    product.price = mrp

    product.save()

    return JsonResponse({
        "status": "success",
        "new_stock": product.stock
    })

@login_required
def search_products(request):

    query = request.GET.get("q", "")

    if not query:
        return JsonResponse([], safe=False)

    products = Product.objects.filter(
        Q(name__icontains=query) |
        Q(barcode__icontains=query)
    ).values("id", "name", "price", "stock")[:20]   # 🔥 LIMIT 20

    return JsonResponse(list(products), safe=False)

# ---------------- PDF PRINT ----------------

def generate_bill_pdf(request, bill_id):

    bill = Bill.objects.get(id=bill_id)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="bill_{bill.id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"<b>INVOICE</b>", styles['Title']))
    elements.append(Spacer(1, 0.3 * inch))

    data = [["Item", "Qty", "Price"]]

    for item in bill.items.all():
        data.append([
            item.product.name,
            item.quantity,
            f"₹ {item.price}"
        ])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Paragraph(f"<b>Total: ₹ {bill.total_amount}</b>", styles['Heading2']))

    doc.build(elements)

    return response

@login_required
def bill_preview(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)

    amount_words = number_to_words(int(bill.total))

    return render(request, "dashboard/bill_preview.html", {
        "bill": bill,
        "amount_words": amount_words
    })

@login_required
def edit_bill(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)

    if bill.status != "active":
        return redirect("sales")

    customers = Customer.objects.all()

    return render(request, "dashboard/billing.html", {
        "customers": customers,
        "edit_bill": bill
    })

@login_required
@transaction.atomic
def update_bill(request, bill_id):

    bill = get_object_or_404(Bill, id=bill_id)

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    data = json.loads(request.body)
    items = data.get("items", [])
    discount = Decimal(data.get("discount", 0))
    apply_gst = data.get("apply_gst", True)

    # 🔥 Restore previous stock
    for item in bill.items.all():
        product = item.product
        product.stock += item.qty
        product.save()

    bill.items.all().delete()

    subtotal = Decimal("0.00")

    for item in items:
        product = Product.objects.get(id=item["product_id"])
        qty = Decimal(item["qty"])

        if product.stock < qty:
            return JsonResponse({"status": "error", "message": "Stock issue"}, status=400)

        price = product.price
        amount = price * qty

        BillItem.objects.create(
            bill=bill,
            product=product,
            qty=qty,
            price=price,
            amount=amount
        )

        product.stock -= qty
        product.save()

        subtotal += amount

    total_gst = subtotal * Decimal("0.18") if apply_gst else Decimal("0.00")
    gross_total = subtotal + total_gst - discount
    rounded_total = gross_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    roundoff = rounded_total - gross_total

    bill.subtotal = subtotal
    bill.cgst = total_gst / 2
    bill.sgst = total_gst / 2
    bill.discount = discount
    bill.roundoff = roundoff
    bill.total = rounded_total
    bill.save()

    return JsonResponse({"status": "success", "bill_id": bill.id})

@login_required
def delete_bill(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)

    bill.status = "cancelled"
    bill.save()

    return redirect("sales")

@login_required
@transaction.atomic
def return_bill(request, bill_id):

    bill = get_object_or_404(Bill, id=bill_id)

    if bill.status != "active":
        return redirect("sales")

    # Restore stock
    for item in bill.items.all():
        product = item.product
        product.stock += item.qty
        product.save()

    bill.status = "returned"
    bill.save()

    return redirect("sales")

def create_product_stock(request):
    import json
    data = json.loads(request.body)

    product = Product.objects.create(
        name=data["name"],
        barcode=data["barcode"],
        price=data["mrp"],
        stock=data["qty"]
    )

    return JsonResponse({"status": "created"})

import json
from django.http import JsonResponse
from .models import Product

def check_product_exists(request):
    import json
    data = json.loads(request.body)
    code = data.get("code")

    try:
        product = Product.objects.get(barcode=code)
        return JsonResponse({
            "exists": True,
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "stock": product.stock   # 👈 ADD THIS
        })
    except Product.DoesNotExist:
        return JsonResponse({"exists": False})
    
    
@login_required
def get_customer_balance(request):

    customer_id = request.GET.get("customer_id")

    if not customer_id:
        return JsonResponse({"balance": 0})

    customer = Customer.objects.get(id=customer_id)

    return JsonResponse({
        "balance": float(customer.balance)
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

@login_required
def debtor_detail(request, id):

    customer = Customer.objects.get(id=id)

    sales = Bill.objects.filter(customer=customer)

    data = []

    for bill in sales:

        data.append({
            "invoice": bill.invoice_no,
            "total": float(bill.total),
            "paid": 0,
            "balance": float(customer.balance)
        })

    return JsonResponse({
    "customer": customer.name,
    "balance": float(customer.balance or 0),
    "sales": data
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

    return render(request, "dashboard/creditors.html", {
        "suppliers": suppliers
    })

@login_required
def purchase(request):

    suppliers = Supplier.objects.all().order_by("name")

    return render(request,"dashboard/purchase.html",{
        "suppliers": suppliers
    })

@login_required
@transaction.atomic
def save_purchase(request):

    try:
        data = json.loads(request.body)

        items = data.get("items", [])
        supplier_id = data.get("supplier_id")
        payment_mode = data.get("payment_mode", "cash")

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
        gst = subtotal * Decimal("0.18")
        total_before_round = subtotal + gst

        rounded_total = total_before_round.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        roundoff = rounded_total - total_before_round

        # SAVE PURCHASE
        purchase.subtotal = subtotal
        purchase.cgst = gst / 2
        purchase.sgst = gst / 2
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

@login_required
@transaction.atomic
def update_purchase(request, id):

    purchase = Purchase.objects.get(id=id)

    data = json.loads(request.body)
    items = data.get("items", [])

    # 🔥 OLD STOCK REVERT
    for item in purchase.items.all():
        product = item.product
        product.stock -= item.qty
        product.save()

    purchase.items.all().delete()

    subtotal = Decimal("0.00")

    for item in items:
        product = Product.objects.get(id=item["product_id"])
        qty = int(item["qty"])

        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            qty=qty,
            price=product.price
        )

        product.stock += qty
        product.save()

        subtotal += Decimal(qty) * product.price

    gst = subtotal * Decimal("0.18")
    total = subtotal + gst

    purchase.subtotal = subtotal
    purchase.cgst = gst / 2
    purchase.sgst = gst / 2
    purchase.total = total
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
        "amount_words": amount_words
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
def purchase_edit(request,id):
    purchase = Purchase.objects.get(id=id)

    if purchase.payment_mode != "credit" or purchase.balance <= 0:
     return redirect("purchase_invoices")
    purchase = Purchase.objects.get(id=id)
    suppliers = Supplier.objects.all()

    return render(request,"dashboard/purchase.html",{
        "edit_purchase":purchase,
        "suppliers":suppliers
    })

@login_required
def receipt_voucher(request):

    if request.method == "POST":

        customer_id = request.POST.get("customer_id")
        amount = Decimal(request.POST.get("amount"))

        customer = Customer.objects.get(id=customer_id)

        customer.balance -= amount
        customer.save()

        messages.success(request,"Payment received successfully")

        return redirect("receipt")

    customers = Customer.objects.filter(balance__gt=0)

    return render(request,"dashboard/receipt_voucher.html",{
        "customers": customers
    })

@login_required
def sales_return(request):

    bills = Bill.objects.filter(status="active")

    return render(request,"dashboard/sales_return.html",{
        "bills": bills
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
            note=note
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

    return render(request, "dashboard/supplier_payment.html", {
        "suppliers": suppliers,
        "allocations": allocations
    })


@login_required
@transaction.atomic
def purchase_return(request):

    suppliers = Supplier.objects.all().order_by("name")

    # ================= SAVE RETURN =================
    if request.method == "POST":

        purchase_id = request.POST.get("purchase_id")
        items_data = request.POST.get("items_data")

        # ❌ safety
        if not purchase_id or not items_data:
            messages.error(request, "Invalid data ❌")
            return redirect("purchase_return")

        purchase = Purchase.objects.get(id=purchase_id)

        import json
        items = json.loads(items_data)
        # ❌ extra safety (empty or all zero qty)
        valid_items = [i for i in items if int(i.get("qty", 0)) > 0]
        if not items:
            messages.error(request, "No items selected ❌")
            return redirect("purchase_return")

        # ================= CREATE RETURN =================
        pr = PurchaseReturn.objects.create(purchase=purchase)

        total_return = Decimal("0.00")
        total_gst = Decimal("0.00")

        for item in items:

            product = Product.objects.get(id=item["product_id"])
            qty = int(item["qty"])

            if qty <= 0:
                continue

            purchase_item = PurchaseItem.objects.get(
                purchase=purchase,
                product=product
            )

            # ================= CHECK REMAINING =================
            returned = PurchaseReturnItem.objects.filter(
                purchase_return__purchase=purchase,
                product=product
            ).aggregate(total=Sum("qty"))["total"] or 0

            remaining = purchase_item.qty - returned

            if qty > remaining:
                messages.error(request, f"{product.name} exceeds remaining qty ❌")
                return redirect("purchase_return")

             # ================= CALCULATION =================
            line_total = Decimal(qty) * purchase_item.price

            gst = line_total * Decimal("0.18")   # 🔥 GST
            cgst = gst / 2
            sgst = gst / 2

            # ================= SAVE ITEM =================
            PurchaseReturnItem.objects.create(
                purchase_return=pr,
                product=product,
                qty=qty,
                price=purchase_item.price
            )

            # ================= STOCK UPDATE =================
            product.stock -= qty
            product.save()

            total_return += line_total
            total_gst += gst

        # ================= TOTAL =================
        grand_total = total_return + total_gst

        pr.subtotal = total_return
        pr.cgst = total_gst / 2
        pr.sgst = total_gst / 2
        pr.total = grand_total
        pr.save()

        # ================= SUPPLIER BALANCE =================
        purchase.supplier.balance -= total_return
        purchase.supplier.save()

        # messages.success(request, "Purchase Return Saved Successfully")

        return redirect(f"/purchase-return/print/{pr.id}/")

    # ================= NORMAL LOAD =================
    return render(request, "dashboard/purchase_return.html", {
        "suppliers": suppliers
    })

@login_required
def purchase_return_print(request, id):
    
    pr = PurchaseReturn.objects.get(id=id)
    company = Company.objects.first()

    total = Decimal("0.00")

    # 🔥 RECALCULATE FROM ITEMS
    for item in pr.items.all():
        total += item.qty * item.price

    gst = (total * Decimal("0.18")).quantize(Decimal("0.01"))
    cgst = (gst / 2).quantize(Decimal("0.01"))
    sgst = (gst / 2).quantize(Decimal("0.01"))

    grand_total = total + gst

    amount_words = number_to_words(int(grand_total))

    return render(request, "dashboard/purchase_return_invoice.html", {
        "return": pr,
        "purchase": pr.purchase,
        "company": company,
        "subtotal": total,
        "cgst": cgst,
        "sgst": sgst,
        "total": grand_total,
        "amount_words": amount_words
    })

def add_expense(request):

    categories = ExpenseCategory.objects.all()

    if request.method == "POST":

        Expense.objects.create(
            category_id=request.POST["category"],
            amount=request.POST["amount"],
            date=request.POST["date"],
            note=request.POST["note"]
        )

        return redirect("/expenses/add/")

    return render(request,"dashboard/expenses/add_expense.html",{
        "categories":categories
    })


def expense_categories(request):

    categories = ExpenseCategory.objects.all()

    if request.method == "POST":

        ExpenseCategory.objects.create(
            name=request.POST["name"]
        )

        return redirect("/expenses/categories/")

    return render(request,"dashboard/expenses/categories.html",{
        "categories":categories
    })


def expense_history(request):

    expenses = Expense.objects.all().order_by("-date")

    return render(request,"dashboard/expenses/history.html",{
        "expenses":expenses
    })

# ================= ACCOUNTS =================

@login_required
def ledger_view(request):
    customers = Customer.objects.all()
    suppliers = Supplier.objects.all()

    return render(request, "dashboard/accounts_summary/ledger.html", {
        "customers": customers,
        "suppliers": suppliers
    })


@login_required
def trial_balance(request):
    total_customer = Customer.objects.aggregate(total=Sum("balance"))["total"] or 0
    total_supplier = Supplier.objects.aggregate(total=Sum("balance"))["total"] or 0

    return render(request, "dashboard/accounts_summary/trial.html", {
        "customer_total": total_customer,
        "supplier_total": total_supplier
    })


@login_required
def profit_loss(request):
    total_sales = Bill.objects.aggregate(total=Sum("total"))["total"] or 0
    total_purchase = Purchase.objects.aggregate(total=Sum("total"))["total"] or 0
    total_expense = Expense.objects.aggregate(total=Sum("amount"))["total"] or 0

    profit = total_sales - (total_purchase + total_expense)

    return render(request, "dashboard/accounts_summary/pl.html", {
        "sales": total_sales,
        "purchase": total_purchase,
        "expense": total_expense,
        "profit": profit
    })


@login_required
def balance_sheet(request):
    cash = Bill.objects.aggregate(total=Sum("total"))["total"] or 0
    liabilities = Supplier.objects.aggregate(total=Sum("balance"))["total"] or 0

    return render(request, "dashboard/accounts_summary/balance.html", {
        "assets": cash,
        "liabilities": liabilities
    })

# ================= REPORTS =================

@login_required
def sales_report(request):
    sales = Bill.objects.all()
    total = sales.aggregate(total=Sum("total"))["total"] or 0

    return render(request, "dashboard/reports/sales.html", {
        "sales": sales,
        "total": total
    })


@login_required
def purchase_report(request):
    purchases = Purchase.objects.all()
    total = purchases.aggregate(total=Sum("total"))["total"] or 0

    return render(request, "dashboard/reports/purchase.html", {
        "purchases": purchases,
        "total": total
    })


@login_required
def expense_report(request):
    expenses = Expense.objects.all()
    total = expenses.aggregate(total=Sum("amount"))["total"] or 0

    return render(request, "dashboard/reports/expenses.html", {
        "expenses": expenses,
        "total": total
    })


@login_required
def profit_report(request):
    sales = Bill.objects.aggregate(total=Sum("total"))["total"] or 0
    purchase = Purchase.objects.aggregate(total=Sum("total"))["total"] or 0
    expense = Expense.objects.aggregate(total=Sum("amount"))["total"] or 0

    profit = sales - (purchase + expense)

    return render(request, "dashboard/reports/profit.html", {
        "profit": profit
    })

@login_required
def sales_report(request):
    from datetime import date

    start_date = request.GET.get("start")
    end_date = request.GET.get("end")

    sales = Bill.objects.all().order_by("-date")

    if start_date and end_date:
        sales = sales.filter(date__date__range=[start_date, end_date])

    total = sales.aggregate(total=Sum("total"))["total"] or 0
    total_gst = sales.aggregate(
        cgst=Sum("cgst"),
        sgst=Sum("sgst")
    )

    return render(request, "dashboard/reports/sales.html", {
        "sales": sales,
        "total": total,
        "cgst": total_gst["cgst"] or 0,
        "sgst": total_gst["sgst"] or 0,
    })

@login_required
def gst_report(request):
    sales = Bill.objects.all()

    total_cgst = sales.aggregate(total=Sum("cgst"))["total"] or 0
    total_sgst = sales.aggregate(total=Sum("sgst"))["total"] or 0

    return render(request, "dashboard/reports/gst.html", {
        "cgst": total_cgst,
        "sgst": total_sgst,
        "total_gst": total_cgst + total_sgst
    })

@login_required
def stock_view(request):
    products = Product.objects.all().order_by("-id")

    total_items = products.count()
    total_qty = sum(p.stock for p in products)
    total_value = sum(p.stock * p.price for p in products)

    return render(request, "dashboard/stock.html", {
        "products": products,
        "total_items": total_items,
        "total_qty": total_qty,
        "total_value": total_value
    })

@login_required
def bank_transaction(request):

    banks = BankAccount.objects.all()

    if request.method == "POST":

        bank_id = request.POST.get("bank")
        amount = float(request.POST.get("amount"))
        t_type = request.POST.get("type")
        note = request.POST.get("note")

        bank = BankAccount.objects.get(id=bank_id)

        # SAVE TRANSACTION
        BankTransaction.objects.create(
            bank=bank,
            amount=amount,
            type=t_type,
            description=note
        )

        # UPDATE BALANCE
        if t_type == "credit":
            bank.balance += amount
        else:
            bank.balance -= amount

        bank.save()

        return redirect("/bank/")

    return render(request, "dashboard/bank.html", {
        "banks": banks
    })

from .models import Company, BankAccount

def dashboard(request):

    company = Company.objects.first()
    banks = BankAccount.objects.all()

    total_bank = sum([b.balance for b in banks])

    # ✅ LOGIN SUCCESS MESSAGE (ONLY ONCE)
    if request.session.pop('login_success', False):
        messages.success(request, "Login successful")

    context = {
        "company": company,
        "bank_total": total_bank,
    }

    return render(request, "dashboard/dashboard.html", context)

from django.http import JsonResponse
from .models import Product
import pandas as pd


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
    
from django.http import JsonResponse

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

    return JsonResponse({
        "invoice": purchase.invoice_number,
        "total": float(purchase.total),
        "paid": float(purchase.paid_amount),
        "balance": float(purchase.balance),
        "payment_mode": purchase.payment_mode,   
        "payments": data
    })

def payment_voucher(request, id):

    allocation = PaymentAllocation.objects.get(id=id)
    amount_words = num2words(int(allocation.amount), lang='en').title()
    payment = allocation.payment
    purchase = allocation.purchase
    supplier = payment.supplier
    company = Company.objects.first()

    return render(request, "dashboard/payment_voucher.html", {
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

    return render(request, "dashboard/purchase_return_invoice.html", {
        "purchase": purchase,
        "return": returns
    })

def get_purchases(request):
    supplier_id = request.GET.get("supplier_id")

    purchases = Purchase.objects.filter(supplier_id=supplier_id)

    data = []
    for p in purchases:
        data.append({
            "id": p.id,
            "invoice_number": p.invoice_number,
            "total": float(p.total)
        })

    return JsonResponse(data, safe=False)


def get_items(request):
    purchase_id = request.GET.get("purchase_id")

    items = PurchaseItem.objects.filter(purchase_id=purchase_id)

    data = []
    for i in items:
        data.append({
            "id": i.product.id,
            "name": i.product.name,
            "price": float(i.price),
            "qty": i.qty
        })

    return JsonResponse(data, safe=False)

@login_required
def supplier_summary(request):

    try:
        suppliers = Supplier.objects.all()

        data = []

        for s in suppliers:

            purchases = Purchase.objects.filter(supplier=s)

            total_purchase = 0
            outstanding = 0

            for p in purchases:

                # SAFE access
                total_purchase += float(p.total or 0)

                if p.payment_mode == "credit":
                    outstanding += float(getattr(p, "balance", 0))

            data.append({
                "id": s.id,
                "name": s.name,
                "total": total_purchase,
                "outstanding": outstanding
            })

        return render(request, "dashboard/supplier_summary.html", {
            "suppliers": data
        })

    except Exception as e:
        return JsonResponse({
            "error": str(e)
        })
@login_required
def get_return_info(request):

    purchase_id = request.GET.get("purchase_id")
    product_id = request.GET.get("product_id")

    items = PurchaseReturnItem.objects.filter(
        purchase_return__purchase_id=purchase_id,
        product_id=product_id
    ).select_related("purchase_return")

    total = 0
    history = []

    for i in items:
        total += i.qty

        history.append({
            "date": i.purchase_return.date.strftime("%d %b %Y"),
            "qty": i.qty
        })

    return JsonResponse({
        "returned": total,
        "history": history
    })
    
