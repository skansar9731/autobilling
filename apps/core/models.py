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
    @property
    def status_display(self):

       mode = (self.payment_mode or "").lower()

    # CASH
       if mode == "cash":
        return "CASH"

    # BANK
       if mode == "bank":
         return "BANK"

    # CREDIT CHECK
       if mode == "credit":

        if self.balance <= 0:
            return "PAID"

        elif self.paid_amount > 0:
            return "PARTIAL"

        else:
            return "CREDIT"

        return "CREDIT"
       
    PAYMENT_CHOICES = (
        ("cash", "Cash"),
        ("bank", "Bank"),
        ("credit", "Credit"),
    )

    invoice_no = models.CharField(
        max_length=20,
        unique=True,
        blank=True
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )

    # PAYMENT MODE
    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default="cash"
    )

    date = models.DateTimeField(auto_now_add=True)

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    cgst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    sgst = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    roundoff = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    STATUS_CHOICES = (
        ("active", "Active"),
        ("returned", "Returned"),
        ("cancelled", "Cancelled"),

        # PAYMENT STATUS
        ("CASH", "Cash"),
        ("BANK", "Bank"),
        ("CREDIT", "Credit"),
        ("PARTIAL", "Partial"),
        ("PAID", "Paid"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    # =====================================
    # AUTO INVOICE NUMBER
    # =====================================

    def save(self, *args, **kwargs):

        if not self.invoice_no:

            last_bill = Bill.objects.order_by("-id").first()

            if (
                last_bill and
                last_bill.invoice_no and
                last_bill.invoice_no.startswith("INV")
            ):

                try:

                    last_number = int(
                        last_bill.invoice_no.replace("INV", "")
                    )

                except:

                    last_number = 0

                new_number = last_number + 1

            else:

                new_number = 1

            self.invoice_no = (
                f"INV{str(new_number).zfill(5)}"
            )

        super().save(*args, **kwargs)

    # =====================================
    # PAYMENT CALCULATIONS
    # =====================================

    @property
    def paid_amount(self):

        from apps.purchases.models import PaymentAllocation
        from django.db.models import Sum
        from decimal import Decimal
        if self.payment_mode in ["cash", "bank"]:
            return self.total

        total = (
            PaymentAllocation.objects
            .filter(bill=self)
            .aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )
        return total

    @property
    def balance(self):

        # CASH / BANK = already paid
        if self.payment_mode in ["cash", "bank"]:

         return Decimal("0.00")

        # CREDIT
        return self.total - self.paid_amount

    # =====================================
    # STRING
    # =====================================

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
    



