import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q
from django.core.mail import send_mail
from django.utils.translation import gettext as _

from mms_app.models import Loan, Payment, CashFlow, RepaymentSchedule, User, Notification
from mms_app.utils import log_activity, send_sms
from .models import PaymentTransaction
from .services import AzamPayService


@login_required
def initiate_payment_view(request, loan_id):
    """
    Web View for Client or Staff initiating AzamPay / Airtel Money checkout
    """
    loan = get_object_or_404(Loan, pk=loan_id)

    # Permission check
    if request.user.role == User.Role.CLIENT and loan.client != request.user:
        raise Http404(_("Ruhusa imekataliwa."))

    if request.method == "POST":
        operator = request.POST.get("operator", "AIRTEL").upper()
        phone = request.POST.get("phone", "").strip()
        amount_str = request.POST.get("amount", "").strip()

        if not phone or not amount_str:
            messages.error(request, _("Tafadhali jaza namba ya simu na kiasi cha kulipa."))
            return redirect("dashboard")

        try:
            amount = Decimal(amount_str)
        except ValueError:
            messages.error(request, _("Kiasi ulichojaza si sahihi."))
            return redirect("dashboard")

        if amount <= 0:
            messages.error(request, _("Kiasi cha kulipia lazima kiwe zaidi ya TZS 0."))
            return redirect("dashboard")

        # Generate unique transaction reference
        date_str = timezone.now().strftime("%Y%m%d%H%M%S")
        ref_id = f"MMS-{date_str}-{PaymentTransaction.objects.count() + 1}"

        # Create PaymentTransaction record
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

        # Call AzamPay Checkout Service
        azampay = AzamPayService()
        res = azampay.initiate_checkout(
            amount=amount,
            phone_number=phone,
            operator=operator,
            reference_id=ref_id,
            loan_id=loan.loan_id
        )

        if res.get("success"):
            tx.external_transaction_id = res.get("transaction_id")
            tx.response_payload = res.get("raw")
            tx.status = PaymentTransaction.Status.SUCCESS
            tx.save()

            # Create standard Payment Receipt
            receipt_no = f"REC-{operator[:3]}-{date_str}"
            payment = Payment.objects.create(
                loan=loan,
                amount_paid=amount,
                receipt_no=receipt_no,
                payment_date=timezone.now(),
                cashier_or_officer=None if request.user.role == User.Role.CLIENT else request.user
            )

            # Record CashFlow Inflow
            CashFlow.objects.create(
                branch=loan.branch,
                flow_type=CashFlow.FlowType.IN,
                category=CashFlow.Category.COLLECTION,
                amount=amount,
                description=_("Marejesho ya mkopo {} kupitia AzamPay ({}) - Risiti {}").format(loan.loan_id, operator, receipt_no),
                recorded_by=None if request.user.role == User.Role.CLIENT else request.user
            )

            # Deduct Loan Balance
            loan.balance = max(Decimal("0.00"), loan.balance - amount)

            # Allocate across schedules
            remaining = amount
            unpaid_schedules = loan.schedules.filter(status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE]).order_by("due_date")
            for sched in unpaid_schedules:
                if remaining <= 0:
                    break
                due_bal = sched.installment_amount - sched.paid_amount
                if remaining >= due_bal:
                    sched.paid_amount = sched.installment_amount
                    sched.status = RepaymentSchedule.Status.PAID
                    remaining -= due_bal
                    sched.save()
                else:
                    sched.paid_amount += remaining
                    remaining = Decimal("0.00")
                    sched.save()

            if loan.balance == Decimal("0.00"):
                loan.status = Loan.Status.COMPLETED

            loan.save()

            # --- NOTIFICATIONS FLOW ---
            notif_msg = _("Mteja {} amelipia TZS {} kwa mkopo {} kupitia {}. Pesa imeelekezwa NMB A/C 12345678901. Risiti: {}").format(
                loan.client.get_full_name(), amount, loan.loan_id, operator, receipt_no
            )

            # 1. Dashboard Notifications for Admin / Staff
            staff_users = User.objects.filter(role__in=[User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER])
            if loan.branch:
                staff_users = staff_users.filter(branch=loan.branch)
            if loan.officer:
                staff_users = staff_users | User.objects.filter(id=loan.officer.id)

            for staff in staff_users.distinct():
                Notification.objects.create(
                    user=staff,
                    title=_("Malipo ya Lipa Namba / AzamPay"),
                    message=notif_msg
                )

            # 2. SMS Notification to Client Phone
            client_sms = _("Habari {}, Malipo yako ya TZS {} kwa mkopo {} yamefanikiwa! Risiti: {}. Salio la mkopo ni TZS {}.").format(
                loan.client.get_full_name(), amount, loan.loan_id, receipt_no, loan.balance
            )
            send_sms(loan.client.phone or phone, client_sms)

            # 3. SMS Notification to Admin / Manager Phone
            admin_sms = _("MMS ARIFA: Malipo ya TZS {} yamepokelewa kutoka kwa {} ({}) kwa mkopo {}. Risiti: {}.").format(
                amount, loan.client.get_full_name(), operator, loan.loan_id, receipt_no
            )
            for admin in staff_users.filter(role__in=[User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]):
                if admin.phone:
                    send_sms(admin.phone, admin_sms)

            # 4. Email Notification to Admin / Staff
            staff_emails = [s.email for s in staff_users if s.email]
            if staff_emails:
                try:
                    send_mail(
                        subject=_("MMS - Taarifa ya Malipo Mapyaya AzamPay"),
                        message=notif_msg,
                        from_email="noreply@mejas.co.tz",
                        recipient_list=staff_emails,
                        fail_silently=True
                    )
                except Exception as e:
                    print(f"Failed to send email alert: {e}")

            log_activity(loan.client, "AZAMPAY_PAYMENT_SUCCESS", f"Paid TZS {amount} via {operator} for loan {loan.loan_id}. Receipt: {receipt_no}", request)
            messages.success(request, _("Malipo yako ya TZS {} yamekamilika kwa mafanikio! Risiti yako ni: {}.").format(amount, receipt_no))
        else:
            tx.status = PaymentTransaction.Status.FAILED
            tx.save()
            messages.error(request, _("Imeshindikana kukamilisha malipo. Tafadhali jaribu tena."))

    return redirect("dashboard")


@csrf_exempt
def azampay_webhook_view(request):
    """
    Webhook Callback receiver for real-time status updates from AzamPay payment gateway.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    reference_id = data.get("externalId") or data.get("utilityref")
    transaction_status = data.get("transactionStatus", "").upper()
    message = data.get("message", "")

    if not reference_id:
        return JsonResponse({"error": "Missing externalId reference"}, status=400)

    tx = PaymentTransaction.objects.filter(reference_id=reference_id).first()
    if not tx:
        return JsonResponse({"error": "Transaction reference not found"}, status=404)

    tx.response_payload = data
    if transaction_status in ["SUCCESS", "SUCCESSFUL", "200"]:
        tx.status = PaymentTransaction.Status.SUCCESS
        tx.save()
        return JsonResponse({"status": "SUCCESS", "message": "Transaction updated successfully"})
    else:
        tx.status = PaymentTransaction.Status.FAILED
        tx.save()
        return JsonResponse({"status": "FAILED", "message": message or "Transaction marked failed"})
