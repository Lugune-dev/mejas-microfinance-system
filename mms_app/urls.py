from django.urls import path
from . import views

urlpatterns = [
    # Public Pages
    path("", views.home_view, name="home"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),

    # Auth
    path("login/", views.mms_login, name="login"),
    path("logout/", views.mms_logout, name="logout"),
    path("password-reset/", views.password_reset_view, name="password_reset"),
    path("password-change/", views.password_change_view, name="password_change"),

    # Dashboard
    path("dashboard/", views.dashboard_view, name="dashboard"),

    # User Management
    path("users/", views.user_list_view, name="user_list"),
    path("users/new/", views.user_create_view, name="user_create"),
    path("users/<int:pk>/edit/", views.user_update_view, name="user_update"),
    path("users/<int:pk>/toggle-status/", views.user_toggle_status_view, name="user_toggle_status"),

    # Clients
    path("clients/", views.client_list_view, name="client_list"),
    path("clients/new/", views.client_register_view, name="client_register"),
    path("clients/<int:pk>/", views.client_detail_view, name="client_detail"),
    path("clients/<int:pk>/edit/", views.client_edit_view, name="client_edit"),

    # Loans
    path("loans/", views.loan_list_view, name="loan_list"),
    path("loans/apply/", views.loan_apply_view, name="loan_apply"),
    path("loans/<int:pk>/", views.loan_detail_view, name="loan_detail"),
    path("loans/<int:pk>/approve/", views.loan_approve_view, name="loan_approve"),
    path("loans/<int:pk>/disburse/", views.loan_disburse_view, name="loan_disburse"),
    path("loans/<int:pk>/record-payment/", views.payment_record_view, name="payment_record"),

    # Daily tracking
    path("daily-tracking/", views.daily_repayment_tracking_view, name="daily_repayment_tracking"),

    # Cash flow & Reconciliation
    path("cash-flow/", views.cash_flow_list_view, name="cash_flow_list"),
    path("cash-flow/new/", views.office_cash_flow_record_view, name="record_office_cash_flow"),
    path("reconciliation/", views.daily_reconciliation_view, name="daily_reconciliation"),
    path("reconciliation/all/", views.reconciliation_list_view, name="reconciliation_list"),
    path("reconciliation/<int:pk>/approve/", views.reconciliation_approve_view, name="reconciliation_approve"),

    # Reports
    path("reports/", views.reports_menu_view, name="reports_menu"),
    path("reports/<str:report_type>/", views.generate_report_view, name="generate_report"),
]
