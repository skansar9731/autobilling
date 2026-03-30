from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.db.models import Sum

# =========================
# PRODUCT MODEL
# =========================

class Product(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    barcode = models.CharField(max_length=100, unique=True, db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    hsn = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.name


# =========================
# CUSTOMER MODEL
# =========================

class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gst = models.CharField(max_length=20, blank=True, null=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return self.name


# =========================
# SUPPLIER MODEL
# =========================

class Supplier(models.Model):

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    gst = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return self.name


# =========================
# BILL MODEL
# =========================

class Bill(models.Model):

    invoice_no = models.CharField(max_length=20, unique=True, blank=True)

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    date = models.DateTimeField(auto_now_add=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    roundoff = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    STATUS_CHOICES = (
        ("active", "Active"),
        ("returned", "Returned"),
        ("cancelled", "Cancelled"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    def save(self, *args, **kwargs):

        if not self.invoice_no:

            last_bill = Bill.objects.order_by("-id").first()

            if last_bill:
                last_number = int(last_bill.invoice_no.replace("INV", ""))
                new_number = last_number + 1
            else:
                new_number = 1

            self.invoice_no = f"INV{str(new_number).zfill(5)}"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_no


# =========================
# BILL ITEM MODEL
# =========================

class BillItem(models.Model):

    bill = models.ForeignKey(
        Bill,
        related_name="items",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    qty = models.IntegerField()

    price = models.DecimalField(max_digits=10, decimal_places=2)

    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):

        self.amount = Decimal(self.qty) * Decimal(self.price)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} ({self.qty})"


# ======================
# PURCHASE MODEL
# ======================

class Purchase(models.Model):
    @property
    def balance(self):
        return self.total - self.paid_amount
    payment_mode = models.CharField(
    max_length=10,
    choices=(
        ("cash", "Cash"),
        ("bank", "Bank"),
        ("credit", "Credit"),
    ),
    default="cash"
)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    invoice_number = models.CharField(max_length=50)
    date = models.DateTimeField(auto_now_add=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    roundoff = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return self.invoice_number
    @property
    def paid_amount(self):
        return self.paymentallocation_set.aggregate(
        total=Sum("amount")
    )["total"] or 0

    @property
    def balance(self):
         return self.total - self.paid_amount


# ======================
# PURCHASE ITEM MODEL
# ======================

class PurchaseItem(models.Model):

    purchase = models.ForeignKey(Purchase, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    qty = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def amount(self):
        return self.qty * self.price

    def __str__(self):
        return f"{self.product.name} ({self.qty})"

class SupplierPayment(models.Model):
    supplier = models.ForeignKey("Supplier", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"Payment to {self.supplier.name} - ₹{self.amount}"


class PurchaseReturn(models.Model):
    purchase = models.ForeignKey("Purchase", on_delete=models.CASCADE)
    reason = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def __str__(self):
        return f"Return - {self.purchase.invoice_number}"
    
class PurchaseReturnItem(models.Model):
    purchase_return = models.ForeignKey(PurchaseReturn, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    qty = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def amount(self):
        return self.qty * self.price
    
class ExpenseCategory(models.Model):

    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Expense(models.Model):

    category = models.ForeignKey(ExpenseCategory,on_delete=models.CASCADE)

    amount = models.DecimalField(max_digits=10,decimal_places=2)

    date = models.DateField()

    note = models.CharField(max_length=255,blank=True)

class BankAccount(models.Model):
    name = models.CharField(max_length=100)  # HDFC / SBI
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return self.name


class BankTransaction(models.Model):

    TRANSACTION_TYPE = (
        ('credit', 'Credit'),   # paisa aaya
        ('debit', 'Debit'),     # paisa gaya
    )

    bank = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPE)
    description = models.CharField(max_length=255, blank=True)
    date = models.DateTimeField(auto_now_add=True)

class Company(models.Model):
    name = models.CharField(max_length=150)
    owner = models.CharField(max_length=100, blank=True)
    gst = models.CharField(max_length=50, blank=True)

    # ✅ NEW FIELDS
    address = models.TextField(blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="India")

    financial_year_from = models.DateField()
    financial_year_to = models.DateField()

    def __str__(self):
        return self.name

class PaymentAllocation(models.Model):
    payment = models.ForeignKey("SupplierPayment", on_delete=models.CASCADE)
    purchase = models.ForeignKey("Purchase", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)



