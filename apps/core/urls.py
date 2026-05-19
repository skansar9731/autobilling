from django.urls import path
from django.shortcuts import redirect
from . import views
# 👉 IMPORT SPLIT
from apps.core import views as core_views
from apps.purchases import views as purchase_views


def home(request):
    return redirect('/login/')


urlpatterns = [

    # ================= HOME =================
    path('', home),

    # ================= AUTH =================
    path("login/", core_views.login_view, name="login"),
    path("logout/", core_views.logout_view, name="logout"),

    # ================= DASHBOARD =================
    path("dashboard/", core_views.dashboard, name="dashboard"),
    path("billing/", core_views.billing, name="billing"),

    # ================= MASTER =================
    path("products/", core_views.product_view, name="products"),
    path("customers/", core_views.customer_view, name="customers"),
    path("users/", core_views.user_view, name="users"),

    # ================= BILLING =================
    path("save-sale/", core_views.save_bill, name="save_sale"),
    path("invoice/<int:bill_id>/", core_views.generate_invoice, name="invoice"),

    # ================= PRODUCT / STOCK =================
    path("scan-product/", core_views.scan_product, name="scan_product"),
    path("search-products/", core_views.search_products, name="search_products"),

    path("stock-receive/", core_views.stock_receive, name="stock_receive"),
    path("stock-scan/", core_views.stock_scan, name="stock_scan"),
    path("update-stock/", core_views.update_stock, name="update_stock"),

    path("check-product-exists/", core_views.check_product_exists),
    path("create-product-stock/", core_views.create_product_stock, name="create_product_stock"),

    # ================= BILL ACTIONS =================
    path("bill/preview/<int:bill_id>/", core_views.bill_preview),
    path("bill/edit/<int:bill_id>/", core_views.edit_bill),
    path("sale/update/<int:bill_id>/",views.update_bill,name="update_sale"),
    path("bill/return/<int:bill_id>/", core_views.return_bill),
    path("bill/delete/<int:bill_id>/", core_views.delete_bill),

    # ================= CUSTOMER =================
    path("customer-balance/", core_views.get_customer_balance),
    path("debtor/<int:id>/", core_views.debtor_detail),

    # ================= SUPPLIERS =================
    path("creditors/", purchase_views.creditors, name="creditors"),
    path("creditor/<int:id>/", purchase_views.creditor_detail),
    path("supplier-balance/", purchase_views.supplier_balance),

    # ================= PURCHASES (NEW MODULE 🔥) =================
    path("purchase/", purchase_views.purchase, name="purchase"),
    path("save-purchase/", purchase_views.save_purchase, name="save_purchase"),
    path("purchase/update/<int:id>/", purchase_views.update_purchase, name="update_purchase"),
    path("purchase/preview/<int:id>/", purchase_views.purchase_preview),
    path("purchase/edit/<int:id>/", purchase_views.purchase_edit),
    path("purchase/delete/<int:id>/", purchase_views.purchase_delete),

    path("purchase-invoices/", purchase_views.purchase_invoices, name="purchase_invoices"),
    path("debit-note/",purchase_views.purchase_return,name="purchase_return"),
    path("sales-return/", purchase_views.purchase_return, {"mode": "sales"}, name="sales_return"),
    path("return/print/<str:mode>/<int:id>/",purchase_views.return_print),
    path("get-transactions/",purchase_views.get_transactions),
    path("get-items/", purchase_views.get_items),
    path("get-return-info/", purchase_views.get_return_info),

    # ================= PAYMENTS =================
    path("payment/", purchase_views.supplier_payment, name="payment"),
    path("receive-payment/<int:supplier_id>/", purchase_views.receive_payment, name="receive_payment"),
    path("print-receipt/<int:payment_id>/", purchase_views.print_receipt),

    # ================= RECEIPT =================
    path("receipt/",core_views.receipt_voucher,name="receipt"),

    # ================= SALES =================
    path("sales-return/", core_views.sales_return),
    path("sales-invoices/", core_views.sales_invoices),

    # ================= RECEIVABLE =================
    path("receivables/", purchase_views.receivables, name="receivables"),
    path("supplier-summary/",core_views.supplier_summary,name="supplier_summary"
),
    # ================= EXPENSE =================
    path("expenses/add/", core_views.add_expense),
    path("expenses/categories/", core_views.expense_categories),
    path("expenses/history/", core_views.expense_history),

    # ================= ACCOUNTS =================
    path("accounts/ledger/", core_views.ledger_view),
    path("accounts/trial/", core_views.trial_balance),
    path("accounts/pl/", core_views.profit_loss),
    path("accounts/balance/", core_views.balance_sheet),

    # ================= REPORTS =================
    path("reports/sales/", core_views.sales_report),
    path("reports/purchase/", core_views.purchase_report),
    path("reports/expenses/", core_views.expense_report),
    path("reports/profit/", core_views.profit_report),
    path("reports/gst/", core_views.gst_report),

    # ================= STOCK =================
    path("stocks/", core_views.stock_view, name="stocks"),

    # ================= BANK =================
    path("bank/", core_views.bank_transaction),

    # ================= BULK =================
    path("bulk-upload/", core_views.bulk_upload, name="bulk_upload"),
    path("bulk-purchase-upload/", purchase_views.bulk_purchase_upload),

    # ================= API =================
    path("api/supplier-invoices/<int:id>/", purchase_views.supplier_invoices_api),
    path("api/purchase-ledger/<int:id>/", purchase_views.purchase_ledger),
    path("api/sales-ledger/<int:id>/",core_views.sales_ledger,name="sales_ledger"
),

    # ================= VOUCHER =================
    path("payment-voucher/<int:id>/", purchase_views.payment_voucher),
    path("receipt-voucher/<int:id>/",views.receipt_voucher_print,name="receipt_voucher"),
    path("purchase-return/view/<int:id>/", purchase_views.purchase_return_invoice),
    path("debtor-summary/",core_views.debtor_summary,name="debtor_summary"),
    path("sales-invoices/",core_views.sales_invoices,name="sales_invoices"),
    path("receipt/", core_views.receipt_voucher, name="receipt"),
    path("api/customer-invoices/<int:id>/",core_views.customer_invoices, name="customer_invoices"),
    path("return/print/<str:mode>/<int:id>/",purchase_views.return_print,name="return_print"),

    path("home/",core_views.home_dashboard,name="home"),
]

