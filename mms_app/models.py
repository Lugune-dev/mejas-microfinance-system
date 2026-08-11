import datetime
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

class Branch(models.Model):
    name = models.CharField(_("Branch Name"), max_length=100)
    location = models.CharField(_("Location"), max_length=150, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Branch")
        verbose_name_plural = _("Branches")


class User(AbstractUser):
    class Role(models.TextChoices):
        CEO = "CEO", _("CEO / Admin")
        ADMIN = "ADMIN", _("Administrator")
        MANAGER = "MANAGER", _("Manager")
        CASHIER = "CASHIER", _("Cashier (Mhazini)")
        OFFICER = "OFFICER", _("Loan Officer")
        CLIENT = "CLIENT", _("Mteja (Client)")

    role = models.CharField(
        _("User Role"),
        max_length=20,
        choices=Role.choices,
        default=Role.CLIENT,
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name=_("Branch"),
    )
    phone = models.CharField(_("Phone Number"), max_length=50, blank=True, null=True)
    nida = models.CharField(_("NIDA ID Number"), max_length=50, blank=True, null=True)
    photo = models.ImageField(_("Photo"), upload_to="user_photos/", blank=True, null=True)

    def __str__(self):
        full_name = self.get_full_name()
        name = full_name if full_name else self.username
        return f"{name} ({self.get_role_display()})"

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")


class ClientProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="client_profile",
        verbose_name=_("Client User"),
    )
    address = models.CharField(_("Address / Anwani"), max_length=255)

    # Guarantor details
    guarantor_name = models.CharField(_("Guarantor Full Name"), max_length=150)
    guarantor_phone = models.CharField(_("Guarantor Phone Number"), max_length=50)
    guarantor_nida = models.CharField(_("Guarantor NIDA ID"), max_length=50, blank=True, null=True)
    guarantor_address = models.CharField(_("Guarantor Address"), max_length=255, blank=True, null=True)
    guarantor_relationship = models.CharField(_("Relationship to Client"), max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile: {self.user.get_full_name()}"

    class Meta:
        verbose_name = _("Client Profile")
        verbose_name_plural = _("Client Profiles")


class Loan(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "DAILY", _("Kila Siku (Daily)")
        WEEKLY = "WEEKLY", _("Kila Wiki (Weekly)")
        MONTHLY = "MONTHLY", _("Kila Mwezi (Monthly)")

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Inayosubiri Kuidhinishwa (Pending)")
        APPROVED = "APPROVED", _("Imeidhinishwa (Approved)")
        REJECTED = "REJECTED", _("Imekataliwa (Rejected)")
        ACTIVE = "ACTIVE", _("Inafanya kazi (Active)")
        COMPLETED = "COMPLETED", _("Imelipwa Kamili (Completed/Paid Off)")
        OVERDUE = "OVERDUE", _("Iliyochelewa (Overdue)")
        DEFAULTED = "DEFAULTED", _("Chechefu (Defaulted)")

    loan_id = models.CharField(_("Loan ID"), max_length=50, unique=True, blank=True)
    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="client_loans",
        limit_choices_to={"role": User.Role.CLIENT},
        verbose_name=_("Client"),
    )
    officer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="officer_loans",
        limit_choices_to={"role": User.Role.OFFICER},
        verbose_name=_("Loan Officer"),
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="loans",
        verbose_name=_("Branch"),
    )
    principal_amount = models.DecimalField(_("Principal Amount"), max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(_("Interest Rate (%)"), max_digits=5, decimal_places=2)
    duration = models.IntegerField(_("Duration (Installments Count)"))
    frequency = models.CharField(
        _("Repayment Frequency"),
        max_length=15,
        choices=Frequency.choices,
        default=Frequency.DAILY,
    )
    total_repayable = models.DecimalField(_("Total Repayable"), max_digits=12, decimal_places=2, blank=True, null=True)
    installment_amount = models.DecimalField(_("Installment Amount"), max_digits=12, decimal_places=2, blank=True, null=True)
    balance = models.DecimalField(_("Outstanding Balance"), max_digits=12, decimal_places=2, blank=True, null=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    application_date = models.DateField(_("Application Date"), default=timezone.now)
    approval_date = models.DateField(_("Approval Date"), blank=True, null=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_loans",
        verbose_name=_("Approved By"),
    )
    disbursement_date = models.DateField(_("Disbursement Date"), blank=True, null=True)
    disbursed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disbursed_loans",
        verbose_name=_("Disbursed By"),
    )

    penalty_rate = models.DecimalField(_("Late Penalty Rate (%)"), max_digits=5, decimal_places=2, default=0.0)
    penalty_accumulated = models.DecimalField(_("Accumulated Penalty"), max_digits=12, decimal_places=2, default=0.0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Calculate interest and totals
        interest_fraction = Decimal(self.interest_rate) / Decimal("100.0")
        interest_val = self.principal_amount * interest_fraction
        self.total_repayable = self.principal_amount + interest_val

        if self.duration > 0:
            self.installment_amount = (self.total_repayable / Decimal(self.duration)).quantize(Decimal("0.01"))
        else:
            self.installment_amount = self.total_repayable

        if self.balance is None:
            self.balance = self.total_repayable

        if not self.loan_id:
            # Generate a temporary unique loan ID if not provided
            date_str = datetime.date.today().strftime("%Y%m%d")
            # We will finalize this on post_save or we can generate based on counts
            count = Loan.objects.count() + 1
            self.loan_id = f"LN-{date_str}-{count:04d}"

        super().save(*args, **kwargs)

    def calculate_penalties(self):
        """
        Check overdue instalments and add late penalty (if penalty rate > 0).
        For simplicity, penalty_accumulated increases as a percentage of overdue instalments.
        """
        if self.status in [self.Status.ACTIVE, self.Status.OVERDUE] and self.penalty_rate > 0:
            overdue_schedules = self.schedules.filter(
                due_date__lt=datetime.date.today(),
                status__in=["UNPAID", "OVERDUE"]
            )
            penalty_tot = Decimal("0.00")
            for sched in overdue_schedules:
                overdue_balance = sched.installment_amount - sched.paid_amount
                penalty_tot += overdue_balance * (Decimal(self.penalty_rate) / Decimal("100.0"))
            self.penalty_accumulated = penalty_tot.quantize(Decimal("0.01"))
            # update balance to include penalty if applicable
            # We can treat penalty as separate or append it
            self.save()

    def __str__(self):
        return f"{self.loan_id} - {self.client.get_full_name()} ({self.get_status_display()})"

    class Meta:
        verbose_name = _("Loan")
        verbose_name_plural = _("Loans")


class RepaymentSchedule(models.Model):
    class Status(models.TextChoices):
        UNPAID = "UNPAID", _("Hajalipa (Unpaid)")
        PAID = "PAID", _("Amelipa (Paid)")
        OVERDUE = "OVERDUE", _("Iliyochelewa (Overdue)")

    loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("Loan"),
    )
    due_date = models.DateField(_("Due Date"))
    installment_amount = models.DecimalField(_("Installment Amount"), max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(_("Paid Amount"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        _("Status"),
        max_length=15,
        choices=Status.choices,
        default=Status.UNPAID,
    )

    class Meta:
        ordering = ["due_date"]
        verbose_name = _("Repayment Schedule")
        verbose_name_plural = _("Repayment Schedules")

    def __str__(self):
        return f"Due {self.due_date}: {self.installment_amount} (Paid: {self.paid_amount})"


class Payment(models.Model):
    loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("Loan"),
    )
    cashier_or_officer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
        verbose_name=_("Recorded By"),
    )
    amount_paid = models.DecimalField(_("Amount Paid"), max_digits=12, decimal_places=2)
    payment_date = models.DateTimeField(_("Payment Date"), default=timezone.now)
    receipt_no = models.CharField(_("Receipt / Transaction ID"), max_length=50, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.receipt_no:
            date_str = timezone.now().strftime("%Y%m%d%H%M%S")
            count = Payment.objects.count() + 1
            self.receipt_no = f"REC-{date_str}-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Receipt {self.receipt_no}: {self.amount_paid}"

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")


class CashFlow(models.Model):
    class FlowType(models.TextChoices):
        IN = "IN", _("Ingizo (Cash In / Collection)")
        OUT = "OUT", _("Toleo (Cash Out / Disbursement / Expense)")

    class Category(models.TextChoices):
        DISBURSEMENT = "DISBURSEMENT", _("Mikopo Iliyotolewa (Disbursement)")
        COLLECTION = "COLLECTION", _("Marejesho ya Mikopo (Collection)")
        OFFICE_INCOME = "OFFICE_INCOME", _("Mapato ya Ofisi (Office Income)")
        OFFICE_EXPENSE = "OFFICE_EXPENSE", _("Matumizi ya Ofisi (Office Expense)")

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="cash_flows",
        verbose_name=_("Branch"),
    )
    flow_type = models.CharField(_("Flow Type"), max_length=10, choices=FlowType.choices)
    category = models.CharField(_("Category"), max_length=30, choices=Category.choices)
    amount = models.DecimalField(_("Amount"), max_digits=12, decimal_places=2)
    date = models.DateTimeField(_("Date"), default=timezone.now)
    description = models.TextField(_("Description / Maelezo"), blank=True, null=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_cash_flows",
        verbose_name=_("Recorded By"),
    )

    def __str__(self):
        return f"{self.get_flow_type_display()} - {self.get_category_display()}: {self.amount}"

    class Meta:
        verbose_name = _("Cash Flow")
        verbose_name_plural = _("Cash Flows")


class DailyReconciliation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Inasubiri Kuthibitishwa (Pending Approval)")
        CONFIRMED = "CONFIRMED", _("Imethibitishwa (Confirmed)")
        REJECTED = "REJECTED", _("Imekataliwa (Rejected)")

    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="reconciliations",
        verbose_name=_("Branch"),
    )
    date = models.DateField(_("Date"), default=datetime.date.today)
    cashier = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="cashier_reconciliations",
        limit_choices_to={"role": User.Role.CASHIER},
        verbose_name=_("Cashier"),
    )
    opening_balance = models.DecimalField(_("Opening Balance"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_received = models.DecimalField(_("Total Cash In (Collections)"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_disbursed = models.DecimalField(_("Total Cash Out (Disbursements/Expenses)"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    calculated_closing = models.DecimalField(_("Calculated Closing Balance"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    actual_cash = models.DecimalField(_("Actual Physical Cash"), max_digits=12, decimal_places=2)
    difference = models.DecimalField(_("Difference (Actual - Calculated)"), max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_reconciliations",
        verbose_name=_("Confirmed By"),
    )
    confirmation_date = models.DateTimeField(_("Confirmation Date"), blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.calculated_closing = self.opening_balance + self.total_received - self.total_disbursed
        self.difference = self.actual_cash - self.calculated_closing
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Reconciliation {self.date} - {self.branch.name} ({self.get_status_display()})"

    class Meta:
        verbose_name = _("Daily Reconciliation")
        verbose_name_plural = _("Daily Reconciliations")
        unique_together = ("branch", "date")


class AuditLog(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name=_("User"),
    )
    action = models.CharField(_("Action"), max_length=100)
    description = models.TextField(_("Description"))
    timestamp = models.DateTimeField(_("Timestamp"), auto_now_add=True)
    ip_address = models.GenericIPAddressField(_("IP Address"), blank=True, null=True)

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"[{self.timestamp}] {user_str} - {self.action}"

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = _("Audit Log")
        verbose_name_plural = _("Audit Logs")
