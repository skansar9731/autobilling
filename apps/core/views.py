from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from .models import Company
from django.views.decorators.http import require_http_methods
from decimal import Decimal, InvalidOperation
from .models import Product, Bill, BillItem, Customer
import json
from .models import Expense, ExpenseCategory
from .models import BankAccount, BankTransaction
import math

from decimal import ROUND_HALF_UP
import csv
from io import TextIOWrapper
import openpyxl
from django.contrib import messages
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
from apps.purchases.models import Supplier
from apps.core.models import Customer
from decimal import Decimal
from apps.core.models import Bill
from apps.purchases.models import PaymentAllocation
# core models
from .models import (
    Product, Bill, BillItem, Customer,
    Supplier, Company,
    Expense, ExpenseCategory,
    BankAccount, BankTransaction
)

# purchases models
from apps.purchases.models import (
    Purchase, PurchaseItem,
    PurchaseReturn, PurchaseReturnItem,
)

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
    payment_mode = data.get("payment_mode", "CASH").upper()

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
    created_by=request.user,
    payment_mode=payment_mode.lower(),
    status=payment_mode.upper()
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

    from decimal import Decimal

    customer_id = request.GET.get("customer_id")

    customer = None

    # =====================================
    # FILTER CUSTOMER
    # =====================================

    if customer_id:

        bills = Bill.objects.filter(
            customer_id=customer_id
        ).order_by("-date")

        customer = get_object_or_404(
            Customer,
            id=customer_id
        )

    else:

        bills = Bill.objects.all().order_by("-date")

    # =====================================
    # LOOP ALL BILLS
    # =====================================

    for p in bills:

        paid = Decimal(
            p.paid_amount or 0
        )

        balance = Decimal(
            p.balance or 0
        )

        mode = (
            p.payment_mode or ""
        ).lower()

        # =====================================
        # STATUS
        # =====================================

        if mode in ["cash", "bank"]:

            p.status = mode.upper()

        else:

            if paid <= 0:

                p.status = "CREDIT"

            elif balance > 0:

                p.status = "PARTIAL"

            else:

                p.status = "PAID"

        # =====================================
        # RETURN TOTAL
        # =====================================

        return_amount = Decimal("0.00")

        returns = PurchaseReturnItem.objects.filter(
            purchase_return__bill=p
        )

        for r in returns:

            line_total = (
                Decimal(r.qty) *
                Decimal(r.price)
            )

            gst = (
                line_total *
                Decimal("0.18")
            )

            return_amount += (
                line_total + gst
            )

        # =====================================
        # DEFAULT PAYABLE
        # =====================================

        p.receivable = Decimal("0.00")

        # =====================================
        # CASH / BANK / PAID
        # RETURN = PAYABLE
        # =====================================

        if mode in ["cash", "bank", "paid"]:

            if return_amount > 0:

                p.receivable = return_amount

        # =====================================
        # CREDIT / PARTIAL
        # ONLY EXTRA RETURN PAYABLE
        # =====================================

        else:

            extra_return = (
                return_amount -
                balance
            )

            if extra_return > 0:

                p.receivable = extra_return

    # =====================================
    # RENDER
    # =====================================

    return render(
        request,
        "purchases/purchase_invoices.html",
        {
            "purchases": bills,
            "party": customer,
            "mode": "sales"
        }
    )
# ---------------- PRODUCTS ----------------


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

    amount_words = number_to_words(int(bill.total))

    return render(request, "dashboard/bill_preview.html", {
        "bill": bill,
        "amount_words": amount_words,
        "mode": "sales"
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
    "amount_words": amount_words,
    "mode": "sales"
})

@login_required
def edit_bill(request, bill_id):

    bill = get_object_or_404(Bill, id=bill_id)

    # ✅ ONLY CREDIT EDIT ALLOWED
    if bill.status != "CREDIT":
        return redirect("sales_invoices")

    customers = Customer.objects.all()

    return render(request, "transactions/transaction.html", {
        "customers": customers,
        "edit_bill": bill,
        "mode": "sales"
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
    payment_mode = data.get(
        "payment_mode",
        "CASH"
    ).upper()

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
    bill.payment_mode = payment_mode.lower()
    bill.status = payment_mode.upper()
    bill.save()

    return JsonResponse({"status": "success", "bill_id": bill.id})

@login_required
def delete_bill(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)

    bill.status = "cancelled"
    bill.save()

    return redirect("sales_invoices")

@login_required
@transaction.atomic
def return_bill(request, bill_id):

    bill = get_object_or_404(Bill, id=bill_id)

    if bill.status != "active":
        return redirect("sales_invoices")

    # Restore stock
    for item in bill.items.all():
        product = item.product
        product.stock += item.qty
        product.save()

    bill.status = "returned"
    bill.save()

    return redirect("sales_invoices")

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

@login_required
@transaction.atomic
def receipt_voucher(request):

    from apps.core.models import Customer, Bill
    from apps.purchases.models import SupplierPayment, PaymentAllocation
    from decimal import Decimal

    allocations = None

    if request.method == "POST":

        customer_id = request.POST.get("customer")
        amount = Decimal(request.POST.get("amount"))
        note = request.POST.get("note")

        customer = Customer.objects.get(id=customer_id)

        # =========================
        # CREATE RECEIPT
        # =========================

        payment = SupplierPayment.objects.create(
            supplier=None,
            amount=amount,
            note=note,
            payment_type="receive"
        )

        remaining = amount

        # =========================
        # CUSTOMER CREDIT BILLS
        # =========================

        bills = Bill.objects.filter(
            customer=customer,
            payment_mode__iexact="credit"
        ).order_by("date")

        for bill in bills:

            if remaining <= 0:
                break

            paid = PaymentAllocation.objects.filter(
            bill=bill
            ).aggregate(
            total=Sum("amount")
            )["total"] or 0

            balance = bill.total - paid

            if balance <= 0:
                continue

        allocate_amount = min(balance, remaining)

        PaymentAllocation.objects.create(
        payment=payment,
        bill=bill,
        amount=allocate_amount
    )

        remaining -= allocate_amount

        allocations = PaymentAllocation.objects.filter(
            payment=payment
        )

        customer.balance -= amount
        customer.save()

        messages.success(
            request,
            "Receipt saved successfully"
        )

        return render(request, "purchases/payment.html", {

            "customers": Customer.objects.filter(balance__gt=0),
            "receipt_mode": True,
            "allocations": allocations

        })

    customers = Customer.objects.filter(balance__gt=0)

    return render(request, "purchases/payment.html", {

        "customers": customers,
        "receipt_mode": True,
        "allocations": allocations

    })

@login_required
def sales_return(request):

    bills = Bill.objects.filter(status="active")

    return render(request,"dashboard/sales_return.html",{
        "bills": bills
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

    return render(request, "core/dashboard.html", context)

from apps.purchases.models import Supplier

@login_required
def party_summary(request, mode="purchase"):

    try:

        # ====================================
        # PARTY LIST
        # ====================================

        if mode == "purchase":
            parties = Supplier.objects.all()
        else:
            parties = Customer.objects.all()

        data = []

        # ====================================
        # LOOP PARTIES
        # ====================================

        for s in parties:

            if mode == "purchase":

                purchases = Purchase.objects.filter(
                    supplier=s
                )

            else:

                purchases = Bill.objects.filter(
                    customer=s
                )

            total_purchase = Decimal("0.00")
            total_payment = Decimal("0.00")
            total_return = Decimal("0.00")
            total_receivable = Decimal("0.00")
            total_outstanding = Decimal("0.00")

            # ====================================
            # LOOP INVOICES
            # ====================================

            for p in purchases:

                total_purchase += Decimal(
                    p.total or 0
                )

                # ====================================
                # RETURN CALCULATION
                # ====================================

                return_amount = Decimal("0.00")

                if mode == "purchase":

                    returns = PurchaseReturnItem.objects.filter(
                        purchase_return__purchase=p
                    )

                    for r in returns:

                        line_total = (
                            Decimal(r.qty) *
                            Decimal(r.price)
                        )

                        gst = (
                            line_total *
                            Decimal("0.18")
                        )

                        return_amount += (
                            line_total + gst
                        )

                # ====================================
                # PAYMENT MODE
                # ====================================

                payment_mode = (
                    getattr(
                        p,
                        "payment_mode",
                        ""
                    ) or ""
                ).lower()

                # ====================================
                # PAID CALCULATION
                # ====================================

                if payment_mode in ["cash", "bank"]:

                    paid = Decimal(
                        p.total or 0
                    )

                else:

                    from apps.purchases.models import PaymentAllocation

                    paid = PaymentAllocation.objects.filter(
                        purchase=p
                    ).aggregate(
                        total=Sum("amount")
                    )["total"] or Decimal("0.00")

                    paid = Decimal(paid)

                total_payment += paid

                # ====================================
                # PURCHASE SUMMARY LOGIC
                # ====================================

                if mode == "purchase":

                    # =========================
                    # CREDIT PURCHASE
                    # =========================

                    if payment_mode == "credit":

                        balance_before_return = (
                            Decimal(p.total) - paid
                        )

                        # -------------------------
                        # PENDING CREDIT
                        # -------------------------

                        if balance_before_return > 0:

                            total_return += return_amount

                            balance = (
                                Decimal(p.total)
                                - paid
                                - return_amount
                            )

                            if balance > 0:

                                total_outstanding += balance

                            elif balance < 0:

                                total_receivable += abs(balance)

                        # -------------------------
                        # FULLY PAID CREDIT
                        # -------------------------

                        else:

                            if return_amount > 0:

                                total_receivable += return_amount

                    # =========================
                    # CASH / BANK
                    # =========================

                    else:

                        if return_amount > 0:

                            total_receivable += return_amount

                # ====================================
                # SALES SUMMARY LOGIC
                # ====================================

                else:

                    balance = (
                        Decimal(p.total) - paid
                    )

                    if balance > 0:

                        total_outstanding += balance

            # ====================================
            # FINAL OUTSTANDING
            # ====================================

            if mode == "purchase":

                final_outstanding = (
                    total_outstanding
                    - total_receivable
                )

                if final_outstanding < 0:

                    final_outstanding = Decimal("0.00")

            else:

                final_outstanding = total_outstanding

            # ====================================
            # FINAL DATA
            # ====================================

            data.append({

                "id": s.id,

                "name": s.name,

                "total": round(
                    total_purchase,
                    2
                ),

                "payment": round(
                    total_payment,
                    2
                ),

                "return": round(
                    total_return,
                    2
                ),

                "outstanding": round(
                    final_outstanding,
                    2
                ),

                "receivable": round(
                    total_receivable,
                    2
                )

            })

        # ====================================
        # RENDER
        # ====================================

        return render(

            request,

            "transactions/summary.html",

            {

                "parties": data,

                "title":
                    "Supplier Summary"
                    if mode == "purchase"
                    else "Debtors Summary",

                "party_label":
                    "Supplier"
                    if mode == "purchase"
                    else "Customer",

                "total_label":
                    "Total Purchase"
                    if mode == "purchase"
                    else "Total Sales",

                "detail_url":
                    "/purchase-invoices/?supplier_id="
                    if mode == "purchase"
                    else "/sales-invoices/?customer_id="

            }

        )

    except Exception as e:

        return JsonResponse({

            "error": str(e)

        })

 # ---------------- BILLING ----------------

@login_required
def billing(request):

    customers = Customer.objects.all().order_by("name")

    suppliers = Supplier.objects.all().order_by("name")

    return render(
        request,
        "transactions/transaction.html",
        {
            "mode": "sales",
            "customers": customers,
            "suppliers": suppliers
        }
    )

@login_required
def supplier_summary(request):

    return party_summary(
        request,
        mode="purchase"
    )


@login_required
def debtor_summary(request):

    from decimal import Decimal

    customers = Customer.objects.all()

    parties = []

    for c in customers:

        bills = Bill.objects.filter(
            customer=c
        )

        total_sales = Decimal("0.00")

        total_receipt = Decimal("0.00")

        total_return = Decimal("0.00")

        total_remaining = Decimal("0.00")

        total_payable = Decimal("0.00")

        # =====================================
        # LOOP ALL BILLS
        # =====================================

        for b in bills:

            bill_total = Decimal(
                b.total or 0
            )

            total_sales += bill_total

            mode = (
                b.payment_mode or ""
            ).lower()

            # =====================================
            # RETURN TOTAL FOR THIS BILL
            # =====================================

            bill_return = Decimal("0.00")

            returns = PurchaseReturnItem.objects.filter(
                purchase_return__bill=b
            )

            for r in returns:

                line_total = (
                    Decimal(r.qty) *
                    Decimal(r.price)
                )

                gst = (
                    line_total *
                    Decimal("0.18")
                )

                bill_return += (
                    line_total + gst
                )

            # =====================================
            # CASH / BANK / PAID
            # =====================================

            if mode in ["cash", "bank", "paid"]:

                paid = bill_total

                balance = Decimal("0.00")

                # RETURN → PAYABLE
                total_payable += bill_return

            # =====================================
            # CREDIT / PARTIAL
            # =====================================

            else:

                paid = Decimal(
                    b.paid_amount or 0
                )

                # RETURN COLUMN
                total_return += bill_return

                balance = (
                    bill_total -
                    paid -
                    bill_return
                )

                # REMAINING
                if balance > 0:

                    total_remaining += balance

                # EXTRA RETURN
                elif balance < 0:

                    total_payable += abs(balance)

            # =====================================
            # RECEIPT
            # =====================================

            total_receipt += paid

        # =====================================
        # FINAL DATA
        # =====================================

        parties.append({

            "id": c.id,

            "name": c.name,

            "total": round(total_sales, 2),

            "payment": round(total_receipt, 2),

            "return": round(total_return, 2),

            "outstanding": round(
                total_remaining,
                2
            ),

            "receivable": round(
                total_payable,
                2
            )
        })

    return render(
        request,
        "transactions/summary.html",
        {

            "title": "Debtors Summary",

            "parties": parties,

            "party_label": "Customer",

            "total_label": "Total Sales",

            "detail_url": "/sales-invoices/?customer_id=",

            "mode": "sales"
        }
    )
@login_required
def sales_ledger(request, id):

    from apps.core.models import Bill
    from apps.purchases.models import PaymentAllocation

    bill = get_object_or_404(Bill, id=id)

    # =========================
    # RECEIPT ALLOCATIONS
    # =========================

    allocations = PaymentAllocation.objects.filter(
        bill=bill
    ).select_related("payment")

    payments = []

   # =========================
# CASH / BANK AUTO PAID
# =========================

    if (bill.payment_mode or "").lower() in ["cash", "bank"]:

        paid = Decimal(bill.total)

        balance = Decimal("0.00")

    else:

     paid = Decimal("0.00")

    for a in allocations:

        paid += a.amount

        payments.append({
            "id": a.payment.id,
            "date": a.payment.date.strftime("%d %b %Y"),
            "amount": float(a.amount)
        })

    balance = bill.total - paid
    return JsonResponse({

        "invoice": bill.invoice_no,

        "total": float(bill.total),

        "paid": float(paid),

        "balance": float(balance),

        "payment_mode": bill.status_display,

        "payments": payments

    })

@login_required
def customer_invoices(request, id):

    bills = Bill.objects.filter(
        customer_id=id
    )

    data = []

    for b in bills:

        # =========================
        # CREDIT ONLY
        # =========================

        mode = (b.payment_mode or "").lower()

        if mode != "credit":
            continue

        paid = PaymentAllocation.objects.filter(
            bill=b
        ).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")

        balance = Decimal(b.total) - Decimal(paid)

        # FULLY PAID HIDE
        if balance <= 0:
            continue

        data.append({
            "invoice": b.invoice_no,
            "paid": float(paid),
            "balance": float(balance)
        })

    return JsonResponse({
        "bills": data
    })

@login_required
def receipt_voucher_print(request, id):

    from apps.purchases.models import (
        SupplierPayment,
        PaymentAllocation
    )

    payment = get_object_or_404(
        SupplierPayment,
        id=id
    )

    allocation = PaymentAllocation.objects.filter(
        payment=payment
    ).first()

    bill = allocation.bill if allocation else None

    company = Company.objects.first()

    customer = bill.customer if bill else None

    amount = payment.amount

    amount_words = num2words(
        amount,
        lang="en_IN"
    ).title()

    return render(
        request,
        "purchases/payment_voucher.html",
        {
            "payment": payment,
            "bill": bill,
            "customer": customer,
            "company": company,
            "amount": amount,
            "amount_words": amount_words,
            "receipt_mode": True
        }
    )  

@login_required
def sales_return(request, mode="sales"):

    customers = Customer.objects.all().order_by("name")

    return render(
        request,
        "purchases/purchase_return.html",
        {
            "parties": customers,
            "mode": "sales"
        }
    ) 