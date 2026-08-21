import json
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.mail import send_mail
from django.utils.translation import gettext as _

from mms_app.models import Loan, Payment, CashFlow, RepaymentSchedule, User, Notification
from mms_app.utils import log_activity, send_sms
from .models import PaymentTransaction
from .services import AzamPayService

logger = logging.getLogger(__name__)


@login_required
def initiate_payment_view(request, loan_id):
    """
    Initiates an AzamPay MNO push checkout for a loan repayment.

    Flow:
      1. Validate input and create a PaymentTransaction with status=PENDING.
      2. Call AzamPay to send a push prompt to the customer's phone.
      3. If push was sent successfully → stay PENDING, inform user to approve on phone.
      4. If push failed → mark FAILED, inform user to retry.
      5. Actual payment confirmation comes via the /payments/webhook/ endpoint.
    """
    loan = get_object_or_404(Loan, pk=loan_id)

    # RBAC: clients can only pay their own loans
    if request.user.role == User.Role.CLIENT and loan.client != request.user:
        raise Http404(_("Ruhusa imekataliwa."))

    if request.method != "POST":
        return redirect("dashboard")

    operator = request.POST.get("operator", "AIRTEL").upper()
    phone = request.POST.get("phone", "").strip()
    amount_str = request.POST.get("amount", "").strip()

    # --- Input validation ---
    if not phone or not amount_str:
        messages.error(request, _("Tafadhali jaza namba ya simu na kiasi cha kulipa."))
        return redirect("dashboard")

    try:
        amount = Decimal(amount_str)
    except Exception:
        messages.error(request, _("Kiasi ulichojaza si sahihi."))
        return redirect("dashboard")

    if amount <= Decimal("0"):
        messages.error(request, _("Kiasi cha kulipia lazima kiwe zaidi ya TZS 0."))
        return redirect("dashboard")

    if amount > loan.balance:
        messages.error(
            request,
            _("Kiasi ulichoweka (TZS {}) kinazidi salio la mkopo (TZS {}). Weka kiasi sahihi.").format(
                amount, loan.balance
            )
        )
        return redirect("dashboard")

    # --- Generate unique transaction reference ---
    date_str = timezone.now().strftime("%Y%m%d%H%M%S")
    ref_id = f"MMS-{date_str}-{PaymentTransaction.objects.count() + 1}"

    # --- Create PENDING transaction record ---
    tx = PaymentTransaction.objects.create(
        loan=loan,
        client=loan.client,
        amount=amount,
        operator=operator,
        phone_number=phone,
        reference_id=ref_id,
        status=PaymentTransaction.Status.PENDING,
        nmb_account_ref="NMB 12345678901 - MEJAS ENTERPRISES MICROFINANCE"
    )

    logger.info(f"[AzamPay] Initiating checkout: ref={ref_id}, loan={loan.loan_id}, amount={amount}, operator={operator}")

    # --- Call AzamPay to send push prompt ---
    azampay = AzamPayService()
    res = azampay.initiate_checkout(
        amount=amount,
        phone_number=phone,
        operator=operator,
        reference_id=ref_id,
        loan_id=loan.loan_id
    )

    if res.get("push_sent"):
        # Push was sent to customer's phone — transaction stays PENDING
        tx.external_transaction_id = res.get("transaction_id", "")
        tx.response_payload = res.get("raw", {})
        # Status remains PENDING — webhook will confirm actual payment
        tx.save()

        log_activity(
            loan.client,
            "AZAMPAY_PUSH_SENT",
            f"Push prompt sent for TZS {amount} via {operator}. Ref: {ref_id}. Awaiting customer PIN confirmation.",
            request
        )

        messages.info(
            request,
            _(
                "✅ Ombi la malipo la TZS {} limetumwa kwenye simu yako ya {}! "
                "Tafadhali ingiza PIN yako ya {} ili kukamilisha malipo. "
                "Baada ya kuthibitisha, akaunti yako itasasishwa kiotomatiki."
            ).format(amount, phone, operator)
        )
    else:
        # Push was NOT sent — mark as FAILED immediately
        tx.status = PaymentTransaction.Status.FAILED
        tx.response_payload = {"error": res.get("message", "Unknown failure")}
        tx.save()

        logger.error(f"[AzamPay] Push failed for ref={ref_id}: {res.get('message')}")
        log_activity(
            loan.client,
            "AZAMPAY_PUSH_FAILED",
            f"Push prompt FAILED for TZS {amount} via {operator}. Ref: {ref_id}. Reason: {res.get('message')}",
            request
        )

        messages.error(
            request,
            _("❌ Imeshindikana kutuma ombi la malipo: {}. Tafadhali angalia namba yako ya simu na jaribu tena.").format(
                res.get("message", "Kosa la kiufundi")
            )
        )

    return redirect("dashboard")


@csrf_exempt
def azampay_webhook_view(request):
    """
    Webhook Callback endpoint for AzamPay real-time payment status updates.
    URL: POST /payments/webhook/azampay/
    Register this URL in your AzamPay Developer Portal as the Callback URL.

    This is where ACTUAL payment processing happens:
    - Update transaction status (SUCCESS / FAILED)
    - Create Payment receipt
    - Deduct loan balance
    - Allocate across repayment schedules
    - Send SMS/email notifications to client and staff
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.warning("[Webhook] Invalid JSON payload received.")
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    # AzamPay webhook fields: externalId / utilityref, transactionStatus, message
    reference_id = data.get("externalId") or data.get("utilityref")
    transaction_status = data.get("transactionStatus", "").upper()
    provider = data.get("provider") or data.get("operator", "")
    gateway_tx_id = data.get("transactionId") or data.get("msisdn", "")

    logger.info(f"[Webhook] Received: ref={reference_id}, status={transaction_status}, gateway_tx={gateway_tx_id}")

    if not reference_id:
        return JsonResponse({"error": "Missing externalId/utilityref reference"}, status=400)

    tx = PaymentTransaction.objects.filter(reference_id=reference_id).first()
    if not tx:
        logger.warning(f"[Webhook] Transaction reference not found: {reference_id}")
        return JsonResponse({"error": "Transaction reference not found"}, status=404)

    # Prevent re-processing an already finalised transaction
    if tx.status in [PaymentTransaction.Status.SUCCESS, PaymentTransaction.Status.FAILED]:
        logger.info(f"[Webhook] Transaction {reference_id} already finalised as {tx.status}. Skipping.")
        return JsonResponse({"status": "ALREADY_PROCESSED", "current_status": tx.status})

    # Update raw payload
    tx.response_payload = data
    if gateway_tx_id:
        tx.external_transaction_id = gateway_tx_id

    # -------------------------------------------------------
    # PAYMENT CONFIRMED AS SUCCESSFUL BY AZAMPAY
    # -------------------------------------------------------
    if transaction_status in ["SUCCESS", "SUCCESSFUL", "200"]:
        tx.status = PaymentTransaction.Status.SUCCESS
        tx.save()

        loan = tx.loan
        amount = tx.amount
        operator = tx.operator or provider
        date_str = timezone.now().strftime("%Y%m%d%H%M%S")
        receipt_no = f"REC-{operator[:3].upper()}-{date_str}-{tx.pk}"

        # 1. Create payment receipt
        Payment.objects.create(
            loan=loan,
            amount_paid=amount,
            receipt_no=receipt_no,
            payment_date=timezone.now(),
            cashier_or_officer=None  # Self-paid by client via mobile money
        )

        # 2. Record cash inflow in CashFlow ledger
        CashFlow.objects.create(
            branch=loan.branch,
            flow_type=CashFlow.FlowType.IN,
            category=CashFlow.Category.COLLECTION,
            amount=amount,
            description=_("Marejesho ya mkopo {} kupitia AzamPay ({}) - Risiti {} - Ref: {}").format(
                loan.loan_id, operator, receipt_no, reference_id
            ),
            recorded_by=None
        )

        # 3. Deduct loan balance
        loan.balance = max(Decimal("0.00"), loan.balance - amount)

        # 4. Allocate payment across unpaid schedules (oldest first)
        remaining = amount
        unpaid = loan.schedules.filter(
            status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE]
        ).order_by("due_date")

        for sched in unpaid:
            if remaining <= Decimal("0"):
                break
            due_bal = sched.installment_amount - sched.paid_amount
            if remaining >= due_bal:
                sched.paid_amount = sched.installment_amount
                sched.status = RepaymentSchedule.Status.PAID
                remaining -= due_bal
            else:
                sched.paid_amount += remaining
                remaining = Decimal("0.00")
            sched.save()

        # 5. Auto-close loan if fully paid
        if loan.balance == Decimal("0.00"):
            loan.status = Loan.Status.COMPLETED

        loan.save()

        # 6. System notifications for staff
        notif_msg = _(
            "Mteja {} amelipia TZS {:,.0f} kwa mkopo {} kupitia {} (AzamPay). "
            "Risiti: {}. Salio jipya la mkopo: TZS {:,.0f}."
        ).format(
            loan.client.get_full_name(), amount, loan.loan_id,
            operator, receipt_no, loan.balance
        )

        staff_qs = User.objects.filter(
            role__in=[User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER]
        )
        if loan.branch:
            staff_qs = staff_qs.filter(branch=loan.branch)
        if loan.officer:
            staff_qs = staff_qs | User.objects.filter(pk=loan.officer.pk)

        for staff in staff_qs.distinct():
            Notification.objects.create(
                user=staff,
                title=_("✅ Malipo Yamepokelewa - AzamPay"),
                message=notif_msg
            )

        # 7. SMS to client
        client_sms = _(
            "Habari {}, malipo yako ya TZS {:,.0f} kwa mkopo {} yamethibitishwa! "
            "Risiti: {}. Salio la mkopo: TZS {:,.0f}. Asante - Mejas Enterprises."
        ).format(
            loan.client.get_full_name(), amount, loan.loan_id, receipt_no, loan.balance
        )
        send_sms(loan.client.phone or tx.phone_number, client_sms)

        # 8. SMS to admin/manager
        admin_sms = _(
            "MMS ARIFA: Malipo ya TZS {:,.0f} yamepokelewa kutoka {} ({}) kwa mkopo {}. Risiti: {}."
        ).format(amount, loan.client.get_full_name(), operator, loan.loan_id, receipt_no)
        for admin in staff_qs.filter(role__in=[User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]):
            if admin.phone:
                send_sms(admin.phone, admin_sms)

        # 9. Email to staff
        staff_emails = [s.email for s in staff_qs.distinct() if s.email]
        if staff_emails:
            try:
                send_mail(
                    subject=_("MMS - Malipo Mapya ya AzamPay Yamepokelewa"),
                    message=notif_msg,
                    from_email="noreply@mejas.co.tz",
                    recipient_list=staff_emails,
                    fail_silently=True
                )
            except Exception as email_err:
                logger.error(f"[Webhook] Email send failed: {email_err}")

        logger.info(f"[Webhook] SUCCESS processed: ref={reference_id}, receipt={receipt_no}, loan={loan.loan_id}")
        return JsonResponse({
            "status": "SUCCESS",
            "message": "Payment confirmed and loan updated successfully.",
            "receipt": receipt_no
        })

    # -------------------------------------------------------
    # PAYMENT FAILED OR CANCELLED BY CUSTOMER
    # -------------------------------------------------------
    else:
        tx.status = PaymentTransaction.Status.FAILED
        tx.save()

        # Notify client of failure
        client_fail_sms = _(
            "Habari {}, malipo yako ya TZS {:,.0f} kwa mkopo {} hayakukamilika. "
            "Tafadhali jaribu tena. - Mejas Enterprises."
        ).format(loan.client.get_full_name(), tx.amount, tx.loan.loan_id)
        send_sms(tx.loan.client.phone or tx.phone_number, client_fail_sms)

        logger.info(f"[Webhook] FAILED processed: ref={reference_id}, gateway_status={transaction_status}")
        return JsonResponse({
            "status": "FAILED",
            "message": data.get("message") or "Payment was not completed by customer."
        })
