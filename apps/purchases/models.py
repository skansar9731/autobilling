from django.db import models
from decimal import Decimal
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.models import Product, Supplier


class Purchase(models.Model):

    PAYMENT_CHOICES = (
        ("cash", "Cash"),
        ("bank", "Bank"),
        ("credit", "Credit"),
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE
    )

    invoice_number = models.CharField(
        max_length=50
    )

    payment_mode = models.CharField(
        max_length=10,
        choices=PAYMENT_CHOICES,
        default="cash"
    )

    date = models.DateTimeField(
        auto_now_add=True
    )

    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    cgst = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    sgst = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    roundoff = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    def __str__(self):
        return self.invoice_number

    # =========================
    # TOTAL PAID
    # =========================
    @property
    def paid_amount(self):

        return self.paymentallocation_set.aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

    # =========================
    # BALANCE
    # =========================
    @property
    def balance(self):

        return Decimal(self.total) - Decimal(self.paid_amount)

    # =========================
    # STATUS DISPLAY
    # =========================
    @property
    def status_display(self):

        mode = (self.payment_mode or "").lower()

        # CASH
        if mode == "cash":
            return "CASH"

        # BANK
        if mode == "bank":
            return "BANK"

        # CREDIT
        if mode == "credit":

            # FULLY PAID
            if self.balance <= 0:
                return "PAID"

            # PARTIAL
            elif self.paid_amount > 0:
                return "PARTIAL"

            # FULL CREDIT
            else:
                return "CREDIT"

        return "CREDIT"


class PurchaseItem(models.Model):

    purchase = models.ForeignKey(
        Purchase,
        related_name="items",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    qty = models.IntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    @property
    def amount(self):
        return self.qty * self.price

    def __str__(self):
        return f"{self.product.name} ({self.qty})"


class PurchaseReturn(models.Model):

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    bill = models.ForeignKey(
        "core.Bill",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    date = models.DateTimeField(
        auto_now_add=True
    )

    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    cgst = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    sgst = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    def __str__(self):

        if self.bill:
            return f"Sales Return - {self.bill.invoice_no}"

        return f"Return - {self.purchase.invoice_number}"

class PurchaseReturnItem(models.Model):

    purchase_return = models.ForeignKey(
        PurchaseReturn,
        related_name="items",
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    qty = models.IntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    @property
    def amount(self):
        return self.qty * self.price


class SupplierPayment(models.Model):

    supplier = models.ForeignKey(
        "core.Supplier",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    date = models.DateTimeField(
        auto_now_add=True
    )

    note = models.TextField(
        blank=True
    )

    payment_type = models.CharField(
        max_length=20,
        choices=(
            ("pay", "Pay"),
            ("receive", "Receive"),
        ),
        default="pay"
    )

    def __str__(self):

        if self.supplier:
            return f"Payment to {self.supplier.name} - ₹{self.amount}"

        return f"Payment - ₹{self.amount}"


class PaymentAllocation(models.Model):

    payment = models.ForeignKey(
        "SupplierPayment",
        on_delete=models.CASCADE
    )

    purchase = models.ForeignKey(
        "purchases.Purchase",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    bill = models.ForeignKey(
        "core.Bill",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )