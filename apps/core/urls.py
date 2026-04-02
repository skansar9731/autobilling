from django.urls import path
from . import views
from django.shortcuts import redirect

def home(request):
    return redirect('/login/')
urlpatterns = [

    # Render live domain
    path('', home),

    # AUTH
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # DASHBOARD
    path("billing/", views.billing, name="billing"),
    path("products/", views.product_view, name="products"),
    path("customers/", views.customer_view, name="customers"),
    path("users/", views.user_view, name="users"),

    # BILLING API
    path("save-bill/", views.save_bill, name="save_bill"),

    # INVOICE
    path("invoice/<int:bill_id>/", views.generate_invoice, name="invoice"),

    # PRODUCT SCAN API
    path("scan-product/", views.scan_product, name="scan_product"),

    # Bulk Upload
    path("bulk-upload/", views.bulk_upload, name="bulk_upload"),

    # Stock Receive Scanner
    path("stock-receive/", views.stock_receive, name="stock_receive"),
    path("stock-scan/", views.stock_scan, name="stock_scan"),
    path("update-stock/", views.update_stock, name="update_stock"),

    path("search-products/", views.search_products, name="search_products"),

    path("bill/preview/<int:bill_id>/", views.bill_preview, name="bill_preview"),
    path("bill/edit/<int:bill_id>/", views.edit_bill, name="edit_bill"),
    path("bill/update/<int:bill_id>/", views.update_bill, name="update_bill"),
    path("bill/return/<int:bill_id>/", views.return_bill, name="return_bill"),
    path("bill/delete/<int:bill_id>/", views.delete_bill, name="delete_bill"),

    path("check-product-exists/", views.check_product_exists),
    path("create-product-stock/", views.create_product_stock, name="create_product_stock"),
    path("customer-balance/", views.get_customer_balance),
    path("debtor/<int:id>/", views.debtor_detail, name="debtor_detail"),

    path("creditors/", views.creditors, name="creditors"),
    path("creditor/<int:id>/", views.creditor_detail, name="creditor_detail"),

    path("purchase/", views.purchase, name="purchase"),
    path("save-purchase/", views.save_purchase, name="save_purchase"),
    path("purchase/preview/<int:id>/", views.purchase_preview, name="purchase_preview"),
    path("purchase/edit/<int:id>/", views.purchase_edit, name="purchase_edit"),
    path("purchase/delete/<int:id>/", views.purchase_delete, name="purchase_delete"),

    path("supplier-balance/", views.supplier_balance, name="supplier_balance"),
    path("receipt/", views.receipt_voucher, name="receipt"),
    path("sales-return/", views.sales_return, name="sales_return"),
    path("sales-invoices/", views.sales_invoices, name="sales_invoices"),
    path("purchase-invoices/", views.purchase_invoices, name="purchase_invoices"),
    path("payment/", views.supplier_payment, name="supplier_payment"),
    path("debit-note/", views.purchase_return, name="purchase_return"),
    path("expenses/add/", views.add_expense),
    path("expenses/categories/", views.expense_categories),
    path("expenses/history/", views.expense_history),
    path("dashboard/", views.dashboard, name="dashboard"),

    # ACCOUNTS
    path("accounts/ledger/", views.ledger_view),
    path("accounts/trial/", views.trial_balance),
    path("accounts/pl/", views.profit_loss),
    path("accounts/balance/", views.balance_sheet),

    # REPORTS
    path("reports/sales/", views.sales_report),
    path("reports/purchase/", views.purchase_report),
    path("reports/expenses/", views.expense_report),
    path("reports/profit/", views.profit_report),
    path("reports/gst/", views.gst_report),
    path("stocks/", views.stock_view, name="stocks"),
    path("bank/", views.bank_transaction),
    path("bulk-purchase-upload/", views.bulk_purchase_upload),
    path("api/supplier-invoices/<int:id>/", views.supplier_invoices_api),
    path("api/purchase-ledger/<int:id>/", views.purchase_ledger),
    path("payment-voucher/<int:id>/", views.payment_voucher, name="payment_voucher"),
    path("purchase-return/view/<int:id>/", views.purchase_return_invoice, name="purchase_return_invoice"),
    path("get-purchases/", views.get_purchases),
    path("get-items/", views.get_items),
    path("purchase-return/print/<int:id>/", views.purchase_return_print),
    path("supplier-summary/", views.supplier_summary, name="supplier_summary"),
]