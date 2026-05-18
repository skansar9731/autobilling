from django.contrib import admin
from .models import (
    Product,
    Customer,
    Bill,
    BillItem,
    Supplier,
    Company,
    BankAccount,
    BankTransaction
)


# ================= PRODUCT =================
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "barcode", "hsn", "price", "stock")
    search_fields = ("name", "barcode", "hsn")
    ordering = ("name",)


# ================= CUSTOMER =================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "gst", "balance")
    search_fields = ("name", "phone")
    ordering = ("name",)


# ================= BILL ITEM INLINE =================
class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    readonly_fields = ("product", "qty", "price")
    can_delete = False


# ================= BILL =================
@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):

    list_display = (
        "invoice_no",
        "customer",
        "date",
        "subtotal",
        "cgst",
        "sgst",
        "discount",
        "roundoff",
        "total"
    )

    search_fields = ("invoice_no", "customer__name")
    ordering = ("-date",)
    inlines = [BillItemInline]

    readonly_fields = (
        "invoice_no",
        "customer",
        "created_by",
        "date",
        "subtotal",
        "cgst",
        "sgst",
        "discount",
        "roundoff",
        "total"
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ================= SUPPLIER =================
@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "balance")
    search_fields = ("name", "phone")


# ================= COMPANY =================
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name",)


# ================= BANK =================
@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "balance")


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ("bank", "amount", "type", "date")