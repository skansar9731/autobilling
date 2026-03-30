from django.contrib import admin
from .models import Product, Customer, Bill, BillItem, Supplier, Purchase
from .models import Company, BankAccount, BankTransaction



# ---------------- PRODUCT ADMIN ----------------

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "barcode", "hsn", "price", "stock")
    search_fields = ("name", "barcode", "hsn")
    ordering = ("name",)


# ---------------- CUSTOMER ADMIN ----------------

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "gst", "balance")
    search_fields = ("name", "phone")
    ordering = ("name",)


# ---------------- BILL ITEM INLINE ----------------

class BillItemInline(admin.TabularInline):
    model = BillItem
    extra = 0
    readonly_fields = ("product", "qty", "price")
    can_delete = False


# ---------------- BILL ADMIN ----------------

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
        return False  # Bills should only be created via Billing UI

    def has_delete_permission(self, request, obj=None):
        return False  # Prevent accidental deletion
    
    # Register only new models
admin.site.register(Supplier)
admin.site.register(Purchase)
admin.site.register(Company)
admin.site.register(BankAccount)
admin.site.register(BankTransaction)