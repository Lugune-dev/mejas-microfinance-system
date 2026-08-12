from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, Branch, ClientProfile, Loan, Payment, CashFlow, DailyReconciliation, AuditLog, RepaymentSchedule

admin.site.site_header = "MEJAS MMS ADMIN"
admin.site.site_title = "Mejas Microfinance System"
admin.site.index_title = "Usimamizi wa Mfumo"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Additional information", {
            "fields": ("role", "branch", "phone", "nida", "photo"),
        }),
    )
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_superuser", "is_active", "branch")
    search_fields = ("username", "first_name", "last_name", "email", "nida")


admin.site.register(Branch)
admin.site.register(ClientProfile)
admin.site.register(Loan)
admin.site.register(Payment)
admin.site.register(CashFlow)
admin.site.register(DailyReconciliation)
admin.site.register(AuditLog)
admin.site.register(RepaymentSchedule)
