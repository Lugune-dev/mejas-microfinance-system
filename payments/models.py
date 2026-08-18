from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

class PaymentTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Inasubiri (Pending)")
        SUCCESS = "SUCCESS", _("Imefanikiwa (Success)")
        FAILED = "FAILED", _("Imefeli (Failed)")

    class Operator(models.TextChoices):
        AIRTEL = "AIRTEL", _("Airtel Money (Lipa Namba)")
        MPESA = "MPESA", _("Vodacom M-Pesa")
        TIGOPESA = "TIGOPESA", _("Tigo Pesa / Yas")
        HALOPESA = "HALOPESA", _("Halopesa")
        NMB = "NMB", _("NMB Bank Direct Deposit")

    loan = models.ForeignKey(
        "mms_app.Loan",
        on_delete=models.CASCADE,
        related_name="azampay_transactions",
        verbose_name=_("Loan")
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_transactions",
        verbose_name=_("Client")
    )
    amount = models.DecimalField(_("Amount Paid"), max_digits=12, decimal_places=2)
    operator = models.CharField(_("Operator"), max_length=20, choices=Operator.choices, default=Operator.AIRTEL)
    phone_number = models.CharField(_("Phone Number"), max_length=50)
    reference_id = models.CharField(_("Reference ID"), max_length=100, unique=True)
    external_transaction_id = models.CharField(_("External Transaction ID"), max_length=100, blank=True, null=True)
    nmb_account_ref = models.CharField(_("NMB Target Account"), max_length=100, default="NMB 12345678901 - MEJAS ENTERPRISES")
    status = models.CharField(_("Status"), max_length=20, choices=Status.choices, default=Status.PENDING)
    response_payload = models.JSONField(_("Provider Response"), blank=True, null=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    def __str__(self):
        return f"{self.reference_id} - {self.operator} - TZS {self.amount} ({self.get_status_display()})"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Payment Transaction")
        verbose_name_plural = _("Payment Transactions")
