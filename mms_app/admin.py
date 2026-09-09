from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    User,
    Branch,
    ClientProfile,
    Loan,
    Payment,
    CashFlow,
    DailyReconciliation,
    AuditLog,
    RepaymentSchedule,
    Notification,
)

admin.site.site_header = "Mejas Microfinance Management System (MMS)"
admin.site.site_title = "Mejas MMS Admin"
admin.site.index_title = "Usimamizi wa Mfumo"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        (_("Microfinance Details"), {
            "fields": ("role", "branch", "phone", "nida", "photo"),
        }),
    )
    list_display = ("username", "get_full_name", "role", "branch", "phone", "is_staff", "is_active")
    list_filter = ("role", "branch", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "phone", "nida")
    ordering = ("username",)


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("get_client_name", "get_phone", "get_nida", "get_branch", "guarantor_name", "guarantor_phone", "created_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__phone",
        "user__nida",
        "guarantor_name",
        "guarantor_phone",
    )
    list_filter = ("user__branch", "created_at")
    readonly_fields = ("created_at",)

    @admin.display(description=_("Mteja (Full Name)"))
    def get_client_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description=_("Simu"))
    def get_phone(self, obj):
        return obj.user.phone or "-"

    @admin.display(description=_("NIDA ID"))
    def get_nida(self, obj):
        return obj.user.nida or "-"

    @admin.display(description=_("Tawi"))
    def get_branch(self, obj):
        return obj.user.branch.name if obj.user.branch else "-"


class RepaymentScheduleInline(admin.TabularInline):
    model = RepaymentSchedule
    extra = 0
    can_delete = False
    fields = ("due_date", "installment_amount", "paid_amount", "status")
    readonly_fields = ("due_date", "installment_amount", "paid_amount", "status")


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    inlines = [RepaymentScheduleInline]
    list_display = (
        "loan_id",
        "client_name",
        "principal_display",
        "interest_rate_display",
        "duration_display",
        "balance_display",
        "status_badge",
        "application_date",
    )
    list_filter = ("status", "frequency", "branch", "application_date")
    search_fields = (
        "loan_id",
        "client__first_name",
        "client__last_name",
        "client__username",
        "client__phone",
        "client__nida",
    )
    date_hierarchy = "application_date"
    readonly_fields = ("total_repayable", "installment_amount", "balance", "created_at", "updated_at")

    @admin.display(description=_("Mkopaji"))
    def client_name(self, obj):
        return obj.client.get_full_name() or obj.client.username

    @admin.display(description=_("Mtaji (TZS)"))
    def principal_display(self, obj):
        return f"TZS {obj.principal_amount:,.0f}"

    @admin.display(description=_("Riba"))
    def interest_rate_display(self, obj):
        return f"{obj.interest_rate}%"

    @admin.display(description=_("Muda na Awamu"))
    def duration_display(self, obj):
        return f"{obj.duration} ({obj.get_frequency_display()})"

    @admin.display(description=_("Salio (TZS)"))
    def balance_display(self, obj):
        bal = obj.balance if obj.balance is not None else obj.total_repayable
        return f"TZS {bal:,.0f}"

    @admin.display(description=_("Hali"))
    def status_badge(self, obj):
        colors = {
            "ACTIVE": "background-color: #dcfce7; color: #15803d; border: 1px solid #86efac;",
            "COMPLETED": "background-color: #e0e7ff; color: #4338ca; border: 1px solid #a5b4fc;",
            "OVERDUE": "background-color: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5;",
            "DEFAULTED": "background-color: #fef2f2; color: #991b1b; border: 1px solid #f87171;",
            "APPROVED": "background-color: #e0f2fe; color: #0369a1; border: 1px solid #7dd3fc;",
            "PENDING": "background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1;",
            "REJECTED": "background-color: #f3f4f6; color: #6b7280; border: 1px solid #d1d5db;",
        }
        style = colors.get(obj.status, "background-color: #f1f5f9; color: #334155;")
        return format_html(
            '<span style="padding: 3px 10px; border-radius: 9999px; font-weight: 700; font-size: 11px; display: inline-block; {}">{}</span>',
            style,
            obj.get_status_display(),
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_no", "loan_ref", "client_name", "amount_display", "payment_date", "cashier_or_officer")
    list_filter = ("payment_date", "loan__branch")
    search_fields = (
        "receipt_no",
        "loan__loan_id",
        "loan__client__first_name",
        "loan__client__last_name",
        "loan__client__phone",
    )
    date_hierarchy = "payment_date"
    readonly_fields = ("receipt_no", "payment_date")

    @admin.display(description=_("Namba ya Mkopo"))
    def loan_ref(self, obj):
        return obj.loan.loan_id

    @admin.display(description=_("Mteja"))
    def client_name(self, obj):
        return obj.loan.client.get_full_name() or obj.loan.client.username

    @admin.display(description=_("Kiasi Kilicholipwa"))
    def amount_display(self, obj):
        return f"TZS {obj.amount_paid:,.0f}"


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ("loan", "due_date", "installment_amount", "paid_amount", "status")
    list_filter = ("status", "due_date")
    search_fields = ("loan__loan_id", "loan__client__first_name", "loan__client__last_name")
    date_hierarchy = "due_date"


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "created_at")
    search_fields = ("name", "location")
    list_filter = ("created_at",)


@admin.register(CashFlow)
class CashFlowAdmin(admin.ModelAdmin):
    list_display = ("date", "branch", "flow_type", "category", "amount_display", "recorded_by")
    list_filter = ("flow_type", "category", "branch", "date")
    search_fields = ("description", "branch__name")
    date_hierarchy = "date"

    @admin.display(description=_("Kiasi (TZS)"))
    def amount_display(self, obj):
        return f"TZS {obj.amount:,.0f}"


@admin.register(DailyReconciliation)
class DailyReconciliationAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "branch",
        "cashier",
        "opening_balance",
        "total_received",
        "total_disbursed",
        "actual_cash",
        "difference",
        "status",
    )
    list_filter = ("status", "branch", "date")
    date_hierarchy = "date"
    search_fields = ("branch__name", "cashier__username")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "description", "ip_address")
    list_filter = ("action", "timestamp")
    search_fields = ("user__username", "action", "description", "ip_address")
    readonly_fields = ("user", "action", "description", "timestamp", "ip_address")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("title", "message", "user__username")

