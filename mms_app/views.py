import datetime
import csv
import json
from io import BytesIO
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import HttpResponse, Http404, JsonResponse
from django.utils import timezone
from django.db.models import Sum, Q, Count
from django.utils.translation import gettext as _
import openpyxl

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .models import (
    Branch, User, ClientProfile, Loan, RepaymentSchedule,
    Payment, CashFlow, DailyReconciliation, AuditLog, Notification
)
from .forms import (
    MMSLoginForm, UserForm, ClientRegistrationForm, ClientProfileForm,
    LoanApplicationForm, LoanApprovalForm, PaymentRecordingForm,
    OfficeCashFlowForm, DailyReconciliationForm, PasswordChangeForm, PasswordResetForm,
    BranchForm
)
from .utils import (
    log_activity, send_sms, sync_overdue_loans_and_penalties, calculate_client_credit_score
)



# --- AUTH VIEWS ---

import random

def mms_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = MMSLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if not user.is_active:
                messages.error(request, _("Akaunti yako imezimwa. Wasiliana na msimamizi."))
                return render(request, "auth/login.html", {"form": form})

            # Check if 2FA is enabled
            if user.two_factor_enabled:
                otp_code = str(random.randint(100000, 999999))
                expiry = timezone.now() + datetime.timedelta(minutes=5)

                # Store in session
                request.session["pre_2fa_user_id"] = user.id
                request.session["otp_code"] = otp_code
                request.session["otp_expiry"] = expiry.isoformat()

                # Send Simulated SMS
                from .utils import send_sms
                sms_text = _("MMS: Namba yako ya siri ya kuingia mfumoni (2FA OTP) ni {}. Itamalizika baada ya dakika 5.").format(otp_code)
                send_sms(user.phone, sms_text)

                # Send Email Notification
                if user.email:
                    from django.core.mail import send_mail
                    try:
                        send_mail(
                            subject=_("MMS - Two-Factor Authentication OTP"),
                            message=sms_text,
                            from_email="noreply@mejas.co.tz",
                            recipient_list=[user.email],
                            fail_silently=True
                        )
                    except Exception as e:
                        print(f"2FA Email failed: {e}")

                messages.info(request, _("Tafadhali jaza namba ya siri (OTP) uliyotumiwa kwenye barua pepe au simu yako."))
                return redirect("verify_2fa")

            # Standard Direct Login
            login(request, user)
            log_activity(user, "USER_LOGIN", f"User logged in successfully from branch {user.branch.name if user.branch else 'HQ'}", request)
            messages.success(request, _("Karibu tena, {}!").format(user.get_full_name() or user.username))

            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect("dashboard")
        else:
            messages.error(request, _("Jina la mtumiaji au password si sahihi."))
    else:
        form = MMSLoginForm()
    return render(request, "auth/login.html", {"form": form})


def verify_2fa_view(request):
    """
    Handles 2FA OTP verification before finalizing login.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")

    user_id = request.session.get("pre_2fa_user_id")
    if not user_id:
        messages.error(request, _("Kipindi chako kimeisha au hakipo sahihi. Tafadhali ingia tena."))
        return redirect("login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        entered_code = request.POST.get("otp_code", "").strip()
        session_code = request.session.get("otp_code")
        expiry_str = request.session.get("otp_expiry")

        if not entered_code or not session_code or not expiry_str:
            messages.error(request, _("Tafadhali jaza namba ya siri (OTP)."))
            return render(request, "auth/verify_2fa.html")

        # Check Expiry
        expiry = datetime.datetime.fromisoformat(expiry_str)
        if timezone.is_naive(expiry):
            expiry = timezone.make_aware(expiry)

        if timezone.now() > expiry:
            messages.error(request, _("Namba ya siri (OTP) imeisha muda wake. Tafadhali ingia tena."))
            # Clear invalid session
            request.session.pop("pre_2fa_user_id", None)
            return redirect("login")

        if entered_code == session_code:
            # Login successful
            login(request, user)
            log_activity(user, "USER_LOGIN_2FA_SUCCESS", f"User logged in successfully via 2FA verification", request)
            messages.success(request, _("Karibu tena, {}!").format(user.get_full_name() or user.username))

            # Clear session auth fields
            request.session.pop("pre_2fa_user_id", None)
            request.session.pop("otp_code", None)
            request.session.pop("otp_expiry", None)

            return redirect("dashboard")
        else:
            messages.error(request, _("Namba ya siri (OTP) uliyojaza si sahihi."))

    return render(request, "auth/verify_2fa.html")


def mms_logout(request):
    if request.user.is_authenticated:
        log_activity(request.user, "USER_LOGOUT", "User logged out", request)
        logout(request)
        messages.success(request, _("Umetoka kwenye mfumo salama."))
    return redirect("login")


def password_reset_view(request):
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            nida = form.cleaned_data["nida"]
            new_password = form.cleaned_data["new_password"]

            try:
                user = User.objects.get(username=username, nida=nida)
                user.set_password(new_password)
                user.save()
                log_activity(user, "PASSWORD_RESET", "User reset password using username & NIDA", request)
                messages.success(request, _("Password imebadilishwa kikamilifu! Sasa unaweza kuingia."))
                return redirect("login")
            except User.DoesNotExist:
                messages.error(request, _("Mtumiaji mwenye utambulisho huo na NIDA hapatikani."))
    else:
        form = PasswordResetForm()
    return render(request, "auth/password_reset.html", {"form": form})


@login_required
def password_change_view(request):
    if request.method == "POST":
        if "toggle_2fa" in request.POST:
            user = request.user
            user.two_factor_enabled = not user.two_factor_enabled
            user.save()
            status_str = "ENABLED" if user.two_factor_enabled else "DISABLED"
            log_activity(request.user, f"USER_2FA_{status_str}", f"User {user.username} toggled 2FA to {status_str}", request)
            messages.success(request, _("Ulinzi wa Two-Factor Authentication (2FA) imesasishwa kikamilifu!"))
            return redirect("password_change")

        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep the user logged in
            log_activity(request.user, "PASSWORD_CHANGE", "User changed password", request)
            messages.success(request, _("Password yako imebadilishwa kikamilifu!"))
            return redirect("dashboard")
        else:
            messages.error(request, _("Tafadhali rekebisha makosa yaliyopo chini."))
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "auth/password_change.html", {"form": form})


# --- DASHBOARD VIEW ---

@login_required
def dashboard_view(request):
    user = request.user
    role = user.role

    # Automatically synchronize overdue statuses & penalties
    sync_overdue_loans_and_penalties()

    # Ensure staff flag is set for system administrative roles
    if role in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.OFFICER, User.Role.CASHIER] and not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])

    context = {
        "role": role,
    }

    today = datetime.date.today()
    branch_filter = request.GET.get("branch")
    selected_branch = None
    if branch_filter and user.role in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        selected_branch = Branch.objects.filter(id=branch_filter).first()
    else:
        selected_branch = user.branch

    # Query based on branch
    branch_q_loans = Q(branch=selected_branch) if selected_branch else Q()
    branch_q_payments = Q(loan__branch=selected_branch) if selected_branch else Q()

    if role in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        all_branches = Branch.objects.all()
        context["branches"] = all_branches
        context["selected_branch"] = selected_branch
        loans = Loan.objects.filter(branch_q_loans)
        context["total_disbursed"] = loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(sum=Sum("principal_amount"))["sum"] or Decimal("0.00")
        context["total_repayments_expected"] = loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(sum=Sum("total_repayable"))["sum"] or Decimal("0.00")

        # Total collections
        context["total_collections"] = Payment.objects.filter(branch_q_payments).aggregate(sum=Sum("amount_paid"))["sum"] or Decimal("0.00")
        context["active_loans_count"] = loans.filter(status=Loan.Status.ACTIVE).count()
        context["overdue_loans_count"] = loans.filter(status=Loan.Status.OVERDUE).count()
        context["defaulted_loans_count"] = loans.filter(status=Loan.Status.DEFAULTED).count()
        context["pending_loans_count"] = loans.filter(status=Loan.Status.PENDING).count()
        context["net_cash_flow"] = context["total_collections"] - context["total_disbursed"]
        context["total_penalty_accumulated"] = loans.aggregate(sum=Sum("penalty_accumulated"))["sum"] or Decimal("0.00")

        clients_q = User.objects.filter(role=User.Role.CLIENT)
        if selected_branch:
            clients_q = clients_q.filter(branch=selected_branch)
        context["clients_count"] = clients_q.count()

        # Branch performance comparison
        branch_perf = []
        for b in all_branches:
            b_loans = Loan.objects.filter(branch=b)
            b_disb = b_loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(s=Sum("principal_amount"))["s"] or Decimal("0.00")
            b_coll = Payment.objects.filter(loan__branch=b).aggregate(s=Sum("amount_paid"))["s"] or Decimal("0.00")
            branch_perf.append({
                "branch": b,
                "clients": User.objects.filter(role=User.Role.CLIENT, branch=b).count(),
                "active_loans": b_loans.filter(status=Loan.Status.ACTIVE).count(),
                "overdue_loans": b_loans.filter(status__in=[Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).count(),
                "disbursed": b_disb,
                "collected": b_coll,
            })
        context["branch_performance"] = branch_perf

        # Monthly trend - last 6 months for chart
        monthly_data = []
        for i in range(5, -1, -1):
            date_check = today - datetime.timedelta(days=i*30)
            month_name = date_check.strftime("%B")
            m_disb = CashFlow.objects.filter(category="DISBURSEMENT", date__month=date_check.month, date__year=date_check.year).aggregate(s=Sum("amount"))["s"] or 0
            m_coll = CashFlow.objects.filter(category="COLLECTION", date__month=date_check.month, date__year=date_check.year).aggregate(s=Sum("amount"))["s"] or 0
            monthly_data.append({
                "month": month_name,
                "disbursement": float(m_disb),
                "collection": float(m_coll)
            })
        context["monthly_data"] = monthly_data
        context["chart_months"] = json.dumps([m["month"] for m in monthly_data])
        context["chart_disbursements"] = json.dumps([m["disbursement"] for m in monthly_data])
        context["chart_collections"] = json.dumps([m["collection"] for m in monthly_data])

        # Recent activity logs
        context["recent_logs"] = AuditLog.objects.all().order_by("-timestamp")[:10]
        context["recent_audit_logs"] = context["recent_logs"]
        return render(request, "dashboard/ceo_manager.html", context)

    elif role == User.Role.CASHIER:
        # Cashier Metrics
        if not user.branch:
            messages.warning(request, _("Hauna tawi ulilopangiwa. Wasiliana na Meneja."))
            return render(request, "dashboard/cashier.html", context)

        # Opening Cash flow calculations
        today_flows = CashFlow.objects.filter(branch=user.branch, date__date=today)
        context["today_cash_in"] = today_flows.filter(flow_type="IN").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        context["today_cash_out"] = today_flows.filter(flow_type="OUT").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        # Get yesterday's reconciliation for opening balance
        prev_recon = DailyReconciliation.objects.filter(branch=user.branch, status="CONFIRMED").order_by("-date").first()
        context["opening_balance"] = prev_recon.actual_cash if prev_recon else Decimal("0.00")
        context["calculated_closing"] = context["opening_balance"] + context["today_cash_in"] - context["today_cash_out"]

        # Today's received payments list and pending disbursements
        context["today_payments"] = Payment.objects.filter(loan__branch=user.branch, payment_date__date=today)
        context["pending_disbursements"] = Loan.objects.filter(branch=user.branch, status=Loan.Status.APPROVED)
        context["recon"] = DailyReconciliation.objects.filter(branch=user.branch, date=today).first()

        return render(request, "dashboard/cashier.html", context)

    elif role == User.Role.OFFICER:
        # Loan Officer Metrics
        context["assigned_clients_count"] = User.objects.filter(role=User.Role.CLIENT, officer_loans__officer=user).distinct().count()

        # Paid / unpaid today
        today_schedules = RepaymentSchedule.objects.filter(loan__officer=user, due_date=today)
        context["today_schedules_count"] = today_schedules.count()
        context["today_paid_count"] = today_schedules.filter(status="PAID").count()
        context["today_unpaid_count"] = today_schedules.filter(status__in=["UNPAID", "OVERDUE"]).count()
        context["overdue_loans_count"] = Loan.objects.filter(officer=user, status__in=[Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).count()

        context["pending_applications"] = Loan.objects.filter(officer=user, status=Loan.Status.PENDING)
        return render(request, "dashboard/officer.html", context)

    elif role == User.Role.CLIENT:
        # Client Metrics
        client_loans = Loan.objects.filter(client=user)
        context["loans"] = client_loans

        active_loan = client_loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE]).first()
        context["active_loan"] = active_loan
        context["credit_score"] = calculate_client_credit_score(user)

        if active_loan:
            context["next_schedule"] = active_loan.schedules.filter(status__in=["UNPAID", "OVERDUE"]).order_by("due_date").first()
            context["payment_history"] = active_loan.payments.all().order_by("-payment_date")
            context["full_schedule"] = active_loan.schedules.all().order_by("due_date")
            context["schedules"] = context["full_schedule"]
            context["total_paid"] = active_loan.payments.aggregate(s=Sum("amount_paid"))["s"] or Decimal("0.00")
            if active_loan.total_repayable and active_loan.total_repayable > 0:
                context["progress_percent"] = min(100, int((context["total_paid"] / active_loan.total_repayable) * 100))
            else:
                context["progress_percent"] = 0

        return render(request, "dashboard/client.html", context)

    return render(request, "dashboard/placeholder.html", context)



@login_required
def mark_notifications_read_view(request):
    """
    Marks all unread notifications for the logged in user as read
    and returns a JSON status update.
    """
    if request.method == "POST" or request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("ajax"):
        updated_count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({"status": "success", "marked_read": updated_count})

    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("dashboard")


# --- USER ACCOUNT MANAGEMENT ---

@login_required
def user_list_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))
    users = User.objects.all().order_by("role", "username")
    return render(request, "users/user_list.html", {"users": users})


@login_required
def user_create_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))
    if request.method == "POST":
        form = UserForm(request.POST, request.FILES)
        if form.is_valid():
            new_user = form.save()
            log_activity(request.user, "USER_CREATION", f"Created new system user: {new_user.username} ({new_user.get_role_display()})", request)
            messages.success(request, _("Mtumiaji mpya amesajiliwa kikamilifu!"))
            return redirect("user_list")
        else:
            messages.error(request, _("Kuna makosa kwenye fomu."))
    else:
        form = UserForm()
    return render(request, "users/user_form.html", {"form": form, "title": _("Sajili Mtumiaji Mpya")})


@login_required
def user_update_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))
    target_user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserForm(request.POST, request.FILES, instance=target_user)
        if form.is_valid():
            updated_user = form.save()
            log_activity(request.user, "USER_UPDATE", f"Updated user credentials/status for: {updated_user.username}", request)
            messages.success(request, _("Taarifa za mtumiaji zimesasishwa!"))
            return redirect("user_list")
        else:
            messages.error(request, _("Kuna makosa kwenye fomu."))
    else:
        form = UserForm(instance=target_user)
    return render(request, "users/user_form.html", {"form": form, "title": _("Hariri Mtumiaji")})


@login_required
def user_toggle_status_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))
    target_user = get_object_or_404(User, pk=pk)
    if target_user == request.user:
        messages.error(request, _("Huwezi kuzima akaunti yako mwenyewe!"))
    else:
        target_user.is_active = not target_user.is_active
        target_user.save()
        status_str = "ACTIVE" if target_user.is_active else "DEACTIVATED"
        log_activity(request.user, f"USER_STATUS_TOGGLE_{status_str}", f"Toggled user status to {status_str} for {target_user.username}", request)
        messages.success(request, _("Hali ya akaunti ya {} imesasishwa kikamilifu.").format(target_user.username))
    return redirect("user_list")


# --- BRANCH MANAGEMENT ---

@login_required
def branch_list_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))
    branches = Branch.objects.all().order_by("name")

    branch_data = []
    for b in branches:
        loans = Loan.objects.filter(branch=b)
        users = User.objects.filter(branch=b)
        clients = users.filter(role=User.Role.CLIENT)
        staff = users.exclude(role=User.Role.CLIENT)
        total_disb = loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(s=Sum("principal_amount"))["s"] or Decimal("0.00")
        total_bal = loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE]).aggregate(s=Sum("balance"))["s"] or Decimal("0.00")
        total_coll = Payment.objects.filter(loan__branch=b).aggregate(s=Sum("amount_paid"))["s"] or Decimal("0.00")

        branch_data.append({
            "branch": b,
            "staff_count": staff.count(),
            "client_count": clients.count(),
            "loan_count": loans.count(),
            "active_loans": loans.filter(status=Loan.Status.ACTIVE).count(),
            "overdue_loans": loans.filter(status__in=[Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).count(),
            "total_disbursed": total_disb,
            "total_collected": total_coll,
            "total_balance": total_bal,
        })

    return render(request, "branches/branch_list.html", {"branch_data": branch_data})


@login_required
def branch_create_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN]:
        raise Http404(_("Ruhusa imekataliwa."))
    if request.method == "POST":
        form = BranchForm(request.POST)
        if form.is_valid():
            branch = form.save()
            log_activity(request.user, "BRANCH_CREATE", f"Created branch: {branch.name}", request)
            messages.success(request, _("Tawi jipya la '{}' limesajiliwa kikamilifu!").format(branch.name))
            return redirect("branch_list")
        else:
            messages.error(request, _("Kuna makosa kwenye fomu."))
    else:
        form = BranchForm()
    return render(request, "branches/branch_form.html", {"form": form, "title": _("Sajili Tawi Jipya")})


@login_required
def branch_edit_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN]:
        raise Http404(_("Ruhusa imekataliwa."))
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == "POST":
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            branch = form.save()
            log_activity(request.user, "BRANCH_UPDATE", f"Updated branch: {branch.name}", request)
            messages.success(request, _("Taarifa za tawi la '{}' zimesasishwa!").format(branch.name))
            return redirect("branch_list")
        else:
            messages.error(request, _("Kuna makosa kwenye fomu."))
    else:
        form = BranchForm(instance=branch)
    return render(request, "branches/branch_form.html", {"form": form, "title": _("Hariri Tawi"), "branch": branch})


# --- CLIENT MANAGEMENT ---


@login_required
def client_register_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.OFFICER]:
        raise Http404(_("Ruhusa imekataliwa."))

    if request.method == "POST":
        user_form = ClientRegistrationForm(request.POST, request.FILES)
        profile_form = ClientProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            # Create user first
            client_user = user_form.save()
            # Link profile
            profile = profile_form.save(commit=False)
            profile.user = client_user
            profile.save()

            log_activity(request.user, "CLIENT_REGISTRATION", f"Registered new client: {client_user.get_full_name()} (Client No: {client_user.username})", request)
            messages.success(request, _("Mteja mpya amesajiliwa kwa mafanikio!"))
            return redirect("client_list")
        else:
            messages.error(request, _("Tafadhali rekebisha makosa kwenye fomu."))
    else:
        user_form = ClientRegistrationForm()
        profile_form = ClientProfileForm()

    return render(request, "clients/client_register.html", {
        "user_form": user_form,
        "profile_form": profile_form
    })


@login_required
def client_list_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.OFFICER, User.Role.CASHIER]:
        raise Http404(_("Ruhusa imekataliwa."))

    search_query = request.GET.get("q", "").strip()
    clients = User.objects.filter(role=User.Role.CLIENT).order_by("-date_joined")

    if search_query:
        clients = clients.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(nida__icontains=search_query) |
            Q(client_loans__loan_id__icontains=search_query)
        ).distinct()

    client_records = []
    for c in clients:
        c_loans = Loan.objects.filter(client=c)
        active_loans = c_loans.filter(status=Loan.Status.ACTIVE)
        overdue_loans = c_loans.filter(status__in=[Loan.Status.OVERDUE, Loan.Status.DEFAULTED])
        total_balance = c_loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(s=Sum("balance"))["s"] or Decimal("0.00")
        client_records.append({
            "client": c,
            "credit": calculate_client_credit_score(c),
            "active_loans_count": active_loans.count(),
            "overdue_loans_count": overdue_loans.count(),
            "total_balance": total_balance,
        })

    total_clients = User.objects.filter(role=User.Role.CLIENT).count()
    active_borrowers = Loan.objects.filter(status=Loan.Status.ACTIVE).values("client").distinct().count()
    overdue_borrowers = Loan.objects.filter(status__in=[Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).values("client").distinct().count()

    return render(request, "clients/client_list.html", {
        "client_records": client_records,
        "search_query": search_query,
        "total_clients": total_clients,
        "active_borrowers": active_borrowers,
        "overdue_borrowers": overdue_borrowers,
    })


@login_required
def client_detail_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.OFFICER, User.Role.CASHIER]:
        raise Http404(_("Ruhusa imekataliwa."))

    client_user = get_object_or_404(User, pk=pk, role=User.Role.CLIENT)
    loans = Loan.objects.filter(client=client_user).order_by("-created_at")

    total_borrowed = loans.aggregate(s=Sum("principal_amount"))["s"] or Decimal("0.00")
    total_repaid = Payment.objects.filter(loan__client=client_user).aggregate(s=Sum("amount_paid"))["s"] or Decimal("0.00")
    outstanding_balance = loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(s=Sum("balance"))["s"] or Decimal("0.00")

    return render(request, "clients/client_detail.html", {
        "client": client_user,
        "loans": loans,
        "credit": calculate_client_credit_score(client_user),
        "total_borrowed": total_borrowed,
        "total_repaid": total_repaid,
        "outstanding_balance": outstanding_balance,
    })



@login_required
def client_edit_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.OFFICER]:
        raise Http404(_("Ruhusa imekataliwa."))

    client_user = get_object_or_404(User, pk=pk, role=User.Role.CLIENT)
    profile = getattr(client_user, "client_profile", None)
    if not profile:
        profile = ClientProfile.objects.create(user=client_user, address="")

    if request.method == "POST":
        # Keep password unchanged during direct edit
        user_form = UserForm(request.POST, request.FILES, instance=client_user)
        profile_form = ClientProfileForm(request.POST, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            log_activity(request.user, "CLIENT_UPDATE", f"Updated details for client {client_user.username}", request)
            messages.success(request, _("Taarifa za mteja zimesasishwa."))
            return redirect("client_detail", pk=client_user.pk)
        else:
            messages.error(request, _("Tafadhali rekebisha fomu."))
    else:
        user_form = UserForm(instance=client_user)
        profile_form = ClientProfileForm(instance=profile)

    return render(request, "clients/client_edit.html", {
        "client": client_user,
        "user_form": user_form,
        "profile_form": profile_form
    })


# --- LOAN & REPAYMENT MANAGEMENT ---

@login_required
def loan_apply_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.OFFICER]:
        raise Http404(_("Ruhusa imekataliwa."))

    if request.method == "POST":
        form = LoanApplicationForm(request.POST)
        if form.is_valid():
            loan = form.save(commit=False)
            loan.status = Loan.Status.PENDING
            loan.save()
            log_activity(request.user, "LOAN_APPLICATION", f"Submitted loan application of TZS {loan.principal_amount} for client {loan.client.get_full_name()}", request)
            messages.success(request, _("Maombi ya mkopo yamewasilishwa kikamilifu!"))
            return redirect("loan_list")
        else:
            messages.error(request, _("Kuna makosa kwenye fomu."))
    else:
        form = LoanApplicationForm(initial={
            "branch": request.user.branch,
            "officer": request.user if request.user.role == User.Role.OFFICER else None,
            "interest_rate": 5.0,
            "penalty_rate": 1.0,
        })
    return render(request, "loans/loan_apply.html", {"form": form})


@login_required
def loan_list_view(request):
    user = request.user
    loans = Loan.objects.all().order_by("-created_at")

    # Filter based on role
    if user.role == User.Role.CLIENT:
        loans = loans.filter(client=user)
    elif user.role == User.Role.OFFICER:
        loans = loans.filter(officer=user)
    elif user.role == User.Role.CASHIER:
        if user.branch:
            loans = loans.filter(branch=user.branch)

    # Search and Filter Status
    status_filter = request.GET.get("status", "")
    search_query = request.GET.get("q", "")

    if status_filter:
        loans = loans.filter(status=status_filter)
    if search_query:
        loans = loans.filter(
            Q(loan_id__icontains=search_query) |
            Q(client__first_name__icontains=search_query) |
            Q(client__last_name__icontains=search_query)
        )

    return render(request, "loans/loan_list.html", {
        "loans": loans,
        "status_filter": status_filter,
        "search_query": search_query
    })


@login_required
def loan_detail_view(request, pk):
    loan = get_object_or_404(Loan, pk=pk)

    # Permission check
    if request.user.role == User.Role.CLIENT and loan.client != request.user:
        raise Http404(_("Ruhusa imekataliwa."))

    # Calculate penalty
    loan.calculate_penalties()

    schedules = loan.schedules.all().order_by("due_date")
    payments = loan.payments.all().order_by("-payment_date")

    return render(request, "loans/loan_detail.html", {
        "loan": loan,
        "schedules": schedules,
        "payments": payments
    })


@login_required
def loan_statement_pdf_view(request, pk):
    """
    Generates and returns an official PDF Loan Statement (Kauli ya Akaunti ya Mkopo).
    Accessible by the loan's client, loan officer, cashier, or management.
    """
    loan = get_object_or_404(Loan, pk=pk)

    # Permission check: client can only view their own loan
    if request.user.role == User.Role.CLIENT and loan.client != request.user:
        raise Http404(_("Ruhusa imekataliwa."))

    # For staff with branch assigned, verify matching branch
    if request.user.role in [User.Role.OFFICER, User.Role.CASHIER] and request.user.branch and loan.branch:
        if request.user.branch != loan.branch and loan.officer != request.user:
            raise Http404(_("Ruhusa imekataliwa."))

    loan.calculate_penalties()
    schedules = loan.schedules.all().order_by("due_date")
    payments = loan.payments.all().order_by("-payment_date")
    total_paid = payments.aggregate(s=Sum("amount_paid"))["s"] or Decimal("0.00")
    today = timezone.now()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'StatementTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        textColor=colors.HexColor('#114139'),
        spaceAfter=2,
        alignment=1
    )
    subtitle_style = ParagraphStyle(
        'StatementSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        textColor=colors.HexColor('#475569'),
        spaceAfter=8,
        alignment=1
    )
    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.HexColor('#114139'),
        spaceBefore=8,
        spaceAfter=3,
    )
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5
    )
    cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5
    )
    header_style = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        textColor=colors.white,
        leading=9.5
    )

    # Header
    elements.append(Paragraph("MEJAS ENTERPRISES MICROFINANCE", title_style))
    branch_name = loan.branch.name if loan.branch else "Tawi Kuu"
    elements.append(Paragraph(
        f"<b>KAULI YA AKAUNTI YA MKOPO (LOAN STATEMENT)</b><br/>"
        f"Namba ya Mkopo: <b>{loan.loan_id}</b> &bull; Tawi: <b>{branch_name}</b> &bull; Tarehe ya Kuchapishwa: <b>{today.strftime('%d/%m/%Y %H:%M')}</b>",
        subtitle_style
    ))
    elements.append(Spacer(1, 4))

    # Summary Info Table
    info_data = [
        [
            Paragraph("<b>Jina la Mteja:</b>", cell_bold),
            Paragraph(loan.client.get_full_name(), cell_style),
            Paragraph("<b>Kiasi cha Mkopo (Principal):</b>", cell_bold),
            Paragraph(f"TZS {loan.principal_amount:,.2f}", cell_style),
        ],
        [
            Paragraph("<b>Namba ya Simu:</b>", cell_bold),
            Paragraph(loan.client.phone or "-", cell_style),
            Paragraph("<b>Kiwango cha Riba:</b>", cell_bold),
            Paragraph(f"{loan.interest_rate}% ({loan.get_frequency_display()})", cell_style),
        ],
        [
            Paragraph("<b>NIDA / Kitambulisho:</b>", cell_bold),
            Paragraph(loan.client.nida or "-", cell_style),
            Paragraph("<b>Jumla ya Marejesho:</b>", cell_bold),
            Paragraph(f"TZS {loan.total_repayable:,.2f}", cell_style),
        ],
        [
            Paragraph("<b>Afisa Mkopo (Officer):</b>", cell_bold),
            Paragraph(loan.officer.get_full_name() if loan.officer else "-", cell_style),
            Paragraph("<b>Jumla Iliyolipwa:</b>", cell_bold),
            Paragraph(f"TZS {total_paid:,.2f}", cell_style),
        ],
        [
            Paragraph("<b>Tarehe ya Kutolewa:</b>", cell_bold),
            Paragraph(loan.disbursement_date.strftime("%d/%m/%Y") if loan.disbursement_date else "-", cell_style),
            Paragraph("<b>Salio Lililobaki:</b>", cell_bold),
            Paragraph(f"<b>TZS {loan.balance:,.2f}</b>", cell_style),
        ],
        [
            Paragraph("<b>Hali ya Mkopo:</b>", cell_bold),
            Paragraph(f"<b>{loan.get_status_display()}</b>", cell_style),
            Paragraph("<b>Adhabu / Faini (Penalties):</b>", cell_bold),
            Paragraph(f"TZS {loan.penalty_accumulated:,.2f}", cell_style),
        ],
    ]

    info_table = Table(info_data, colWidths=[125, 150, 140, 130])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 4))

    # Repayment Schedules Section
    elements.append(Paragraph("RATIBA YA MAREJESHO (REPAYMENT SCHEDULE)", section_title_style))
    sched_headers = [_("Awamu"), _("Tarehe ya Mwisho"), _("Kiasi Kinachotakiwa"), _("Kiasi Kilicholipwa"), _("Hali ya Awamu")]
    sched_rows = [[Paragraph(f"<b>{h}</b>", header_style) for h in sched_headers]]

    for idx, s in enumerate(schedules, 1):
        sched_rows.append([
            Paragraph(f"Awamu #{idx}", cell_style),
            Paragraph(s.due_date.strftime("%d/%m/%Y") if s.due_date else "-", cell_style),
            Paragraph(f"TZS {s.installment_amount:,.2f}", cell_style),
            Paragraph(f"TZS {s.paid_amount:,.2f}", cell_style),
            Paragraph(s.get_status_display(), cell_style),
        ])

    if not schedules.exists():
        sched_rows.append([Paragraph("Hakuna ratiba iliyotengenezwa bado.", cell_style)] + [Paragraph("-", cell_style)] * 4)

    sched_table = Table(sched_rows, colWidths=[80, 115, 125, 125, 100])
    sched_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#114139')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(sched_table)
    elements.append(Spacer(1, 4))

    # Payment History Section
    elements.append(Paragraph("HISTORIA YA MALIPO (PAYMENT TRANSACTIONS)", section_title_style))
    pay_headers = [_("Risiti No"), _("Tarehe na Muda"), _("Kiasi Kilicholipwa"), _("Mhazini / Afisa")]
    pay_rows = [[Paragraph(f"<b>{h}</b>", header_style) for h in pay_headers]]

    for p in payments:
        pay_rows.append([
            Paragraph(p.receipt_no, cell_style),
            Paragraph(p.payment_date.strftime("%d/%m/%Y %H:%M"), cell_style),
            Paragraph(f"TZS {p.amount_paid:,.2f}", cell_style),
            Paragraph(p.cashier_or_officer.get_full_name() if p.cashier_or_officer else "-", cell_style),
        ])

    if not payments.exists():
        pay_rows.append([Paragraph("Hakuna malipo yaliyofanyika bado.", cell_style)] + [Paragraph("-", cell_style)] * 3)

    pay_table = Table(pay_rows, colWidths=[145, 130, 130, 140])
    pay_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#114139')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(pay_table)
    elements.append(Spacer(1, 10))

    # Signoff and footer
    signoff = Paragraph(
        "<b>Imethibitishwa na (Afisa/Mhazini):</b> ___________________________ &nbsp;&nbsp;&nbsp;&nbsp; "
        "<b>Saini:</b> ____________ &nbsp;&nbsp;&nbsp;&nbsp; <b>Tarehe:</b> ____________",
        cell_style
    )
    elements.append(signoff)
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "<font size='7' color='#94a3b8'>Mfumo Rasmi wa Kidigitali wa Mejas Enterprises Microfinance &copy; 2026. Hati hii ni halali bila mabadiliko ya mkono.</font>",
        subtitle_style
    ))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="loan_statement_{loan.loan_id}.pdf"'
    return response


@login_required
def loan_approve_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))

    loan = get_object_or_404(Loan, pk=pk, status=Loan.Status.PENDING)

    if request.method == "POST":
        form = LoanApprovalForm(request.POST)
        decision = request.POST.get("decision")
        if decision in ["APPROVED", "REJECTED"]:
            loan.status = decision
            loan.approval_date = datetime.date.today()
            loan.approved_by = request.user
            loan.save()
            log_activity(request.user, f"LOAN_APPROVAL_{decision}", f"Loan {loan.loan_id} has been {decision} by {request.user.get_full_name()}", request)
            messages.success(request, _("Hali ya mkopo imesasishwa kuwa: {}").format(loan.get_status_display()))
            return redirect("loan_detail", pk=loan.pk)
    else:
        form = LoanApprovalForm()

    return render(request, "loans/loan_approve.html", {
        "loan": loan,
        "form": form
    })


@login_required
def loan_disburse_view(request, pk):
    """Cashier disburses funds, initiating active schedules and recording cash flow out"""
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER]:
        raise Http404(_("Ruhusa imekataliwa."))

    loan = get_object_or_404(Loan, pk=pk, status=Loan.Status.APPROVED)

    if request.method == "POST":
        # Check cashier branch matching
        if request.user.role == User.Role.CASHIER and request.user.branch != loan.branch:
            messages.error(request, _("Huwezi kutoa mikopo ya tawi lingine!"))
            return redirect("loan_detail", pk=loan.pk)

        # Update Loan Status
        loan.status = Loan.Status.ACTIVE
        loan.disbursement_date = datetime.date.today()
        loan.disbursed_by = request.user
        loan.balance = loan.total_repayable
        loan.save()

        # 1. Generate Repayment Schedule
        today = datetime.date.today()
        for i in range(1, loan.duration + 1):
            if loan.frequency == Loan.Frequency.DAILY:
                delta = datetime.timedelta(days=i)
            elif loan.frequency == Loan.Frequency.WEEKLY:
                delta = datetime.timedelta(weeks=i)
            else: # MONTHLY
                # Approx 30 days
                delta = datetime.timedelta(days=i*30)

            due_date = today + delta
            RepaymentSchedule.objects.create(
                loan=loan,
                due_date=due_date,
                installment_amount=loan.installment_amount,
                paid_amount=Decimal("0.00"),
                status=RepaymentSchedule.Status.UNPAID
            )

        # 2. Record CashFlow (Disbursement)
        CashFlow.objects.create(
            branch=loan.branch,
            flow_type=CashFlow.FlowType.OUT,
            category=CashFlow.Category.DISBURSEMENT,
            amount=loan.principal_amount,
            description=_("Disbursement for Loan {}").format(loan.loan_id),
            recorded_by=request.user
        )

        log_activity(request.user, "LOAN_DISBURSEMENT", f"Disbursed TZS {loan.principal_amount} for loan {loan.loan_id}", request)
        messages.success(request, _("Mikopo imetolewa kikamilifu na ratiba ya marejesho imetengenezwa!"))
        return redirect("loan_detail", pk=loan.pk)

    return render(request, "loans/loan_disburse.html", {"loan": loan})


@login_required
def payment_record_view(request, pk):
    """Recorded by Cashier or Officer"""
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER, User.Role.OFFICER]:
        raise Http404(_("Ruhusa imekataliwa."))

    loan = get_object_or_404(Loan, pk=pk, status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE])

    if request.method == "POST":
        form = PaymentRecordingForm(request.POST)
        if form.is_valid():
            amount_paid = form.cleaned_data["amount_paid"]
            if amount_paid <= 0:
                messages.error(request, _("Kiasi cha malipo lazima kiwe kikubwa kuliko sifuri!"))
                return render(request, "loans/payment_record.html", {"loan": loan, "form": form})

            # Create payment record
            payment = form.save(commit=False)
            payment.loan = loan
            payment.cashier_or_officer = request.user
            payment.save()

            # Log collection in CashFlow
            CashFlow.objects.create(
                branch=loan.branch,
                flow_type=CashFlow.FlowType.IN,
                category=CashFlow.Category.COLLECTION,
                amount=amount_paid,
                description=_("Repayment collection for loan {} via receipt {}").format(loan.loan_id, payment.receipt_no),
                recorded_by=request.user
            )

            # Update Loan Balance
            loan.balance = max(Decimal("0.00"), loan.balance - amount_paid)

            # Trigger Notifications for Manual Cashier/Officer Payment
            from .utils import send_sms
            from django.core.mail import send_mail
            from .models import Notification

            notif_text = _("Malipo ya TZS {} kwa ajili ya mkopo {} yamerekodiwa. Risiti: {}.").format(
                amount_paid, loan.loan_id, payment.receipt_no
            )

            # In-app notification to client
            Notification.objects.create(
                user=loan.client,
                title=_("Taarifa ya Malipo"),
                message=notif_text
            )

            # SMS notification to client
            client_sms = _("Habari {}, Tumepokea marejesho yako ya TZS {} kwa mkopo {}. Risiti: {}. Salio jipya: TZS {}.").format(
                loan.client.get_full_name(), amount_paid, loan.loan_id, payment.receipt_no, loan.balance
            )
            send_sms(loan.client.phone, client_sms)

            # In-app, SMS, Email to Admin/Managers
            staff_users = User.objects.filter(role__in=[User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER])
            if loan.branch:
                staff_users = staff_users.filter(branch=loan.branch)

            for admin_user in staff_users:
                Notification.objects.create(
                    user=admin_user,
                    title=_("Marejesho ya Mkopo"),
                    message=_("Mteja {} amelipa TZS {} kwa mkopo {}. Risiti: {}.").format(
                        loan.client.get_full_name(), amount_paid, loan.loan_id, payment.receipt_no
                    )
                )
                if admin_user.phone:
                    send_sms(admin_user.phone, _("MMS ARIFA: Mteja {} amelipa TZS {} kwa mkopo {}. Risiti: {}.").format(
                        loan.client.get_full_name(), amount_paid, loan.loan_id, payment.receipt_no
                    ))

            admin_emails = [s.email for s in staff_users if s.email]
            if admin_emails:
                try:
                    send_mail(
                        subject=_("MMS - Taarifa ya Marejesho ya Mkopo"),
                        message=notif_text,
                        from_email="noreply@mejas.co.tz",
                        recipient_list=admin_emails,
                        fail_silently=True
                    )
                except Exception as e:
                    print(f"Failed to send email alert: {e}")

            # Allocate payment across schedules sequentially
            remaining_payment = amount_paid
            schedules = loan.schedules.filter(status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE]).order_by("due_date")

            for sched in schedules:
                if remaining_payment <= 0:
                    break
                due_balance = sched.installment_amount - sched.paid_amount
                if remaining_payment >= due_balance:
                    sched.paid_amount = sched.installment_amount
                    sched.status = RepaymentSchedule.Status.PAID
                    remaining_payment -= due_balance
                    sched.save()
                else:
                    sched.paid_amount += remaining_payment
                    remaining_payment = Decimal("0.00")
                    sched.save()

            if loan.balance == Decimal("0.00"):
                loan.status = Loan.Status.COMPLETED

            loan.save()

            log_activity(request.user, "LOAN_REPAYMENT", f"Recorded payment of TZS {amount_paid} for loan {loan.loan_id}, receipt {payment.receipt_no}", request)
            messages.success(request, _("Malipo yamerekodiwa kwa mafanikio! Risiti: {}").format(payment.receipt_no))
            return redirect("loan_detail", pk=loan.pk)
    else:
        form = PaymentRecordingForm()

    return render(request, "loans/payment_record.html", {
        "loan": loan,
        "form": form
    })


@login_required
def client_lipa_payment_view(request, pk):
    """
    Simulates Lipa Number Mobile Money checkout using AzamPay integration gateway.
    Handles Airtel Money, Tigo Pesa, M-Pesa, Halopesa payments.
    """
    loan = get_object_or_404(Loan, pk=pk)

    # RBAC check: only client owner or staff can initiate payment
    if request.user.role == User.Role.CLIENT and loan.client != request.user:
        raise Http404(_("Ruhusa imekataliwa."))

    if request.method == "POST":
        operator = request.POST.get("operator", "").upper()
        phone = request.POST.get("phone", "").strip()
        amount_str = request.POST.get("amount", "").strip()

        if not operator or not phone or not amount_str:
            messages.error(request, _("Tafadhali jaza taarifa zote kwa usahihi."))
            return redirect("dashboard")

        try:
            amount_paid = Decimal(amount_str)
        except ValueError:
            messages.error(request, _("Kiasi kilichowekwa si sahihi."))
            return redirect("dashboard")

        if amount_paid <= 0:
            messages.error(request, _("Kiasi cha kulipa lazima kiwe zaidi ya 0."))
            return redirect("dashboard")

        # Simulate AzamPay payment processing payload
        print(f"--- Simulating AzamPay Integration request ---")
        print(f"POST https://api.azampay.co.tz/v1/checkout")
        print(f"Payload: {{ 'amount': '{amount_paid}', 'phone': '{phone}', 'operator': '{operator}', 'utility': 'MMS_REPAYMENT', 'loan_id': '{loan.loan_id}' }}")
        print(f"--- Response from AzamPay: Status: SUCCESS, reference_id: 'AZ-{timezone.now().strftime('%Y%m%d%H%M%S')}' ---")

        # Simulate successful processing:
        # Create payment receipt
        date_str = timezone.now().strftime("%Y%m%d%H%M%S")
        receipt_no = f"REC-AZ-{date_str}-{Payment.objects.count() + 1}"

        payment = Payment.objects.create(
            loan=loan,
            amount_paid=amount_paid,
            receipt_no=receipt_no,
            payment_date=timezone.now(),
            cashier_or_officer=None  # Client Self-Paid via AzamPay
        )

        # Log collection in CashFlow
        CashFlow.objects.create(
            branch=loan.branch,
            flow_type=CashFlow.FlowType.IN,
            category=CashFlow.Category.COLLECTION,
            amount=amount_paid,
            description=_("Repayment collection for loan {} via AzamPay ({})").format(loan.loan_id, operator),
            recorded_by=None
        )

        # Update Loan Balance
        loan.balance = max(Decimal("0.00"), loan.balance - amount_paid)

        # Allocate payment across schedules sequentially
        remaining_payment = amount_paid
        schedules = loan.schedules.filter(status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE]).order_by("due_date")

        for sched in schedules:
            if remaining_payment <= 0:
                break
            due_balance = sched.installment_amount - sched.paid_amount
            if remaining_payment >= due_balance:
                sched.paid_amount = sched.installment_amount
                sched.status = RepaymentSchedule.Status.PAID
                remaining_payment -= due_balance
                sched.save()
            else:
                sched.paid_amount += remaining_payment
                remaining_payment = Decimal("0.00")
                sched.save()

        if loan.balance == Decimal("0.00"):
            loan.status = Loan.Status.COMPLETED

        loan.save()

        # Trigger notifications (SMS, Email, System Notification)
        from .utils import send_sms
        from django.core.mail import send_mail
        from .models import Notification

        # 1. System notification to loan officer & branch cashier/managers
        notification_msg = _("Mteja {} amelipia TZS {} kupitia AzamPay ({}) kwa ajili ya Mkopo {}.").format(
            loan.client.get_full_name(), amount_paid, operator, loan.loan_id
        )

        # Find staff users associated with the loan branch/officer to notify
        staff_users = User.objects.filter(role__in=[User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER])
        if loan.branch:
            staff_users = staff_users.filter(branch=loan.branch)

        # Also notify the specific officer of this loan
        if loan.officer:
            staff_users = staff_users | User.objects.filter(id=loan.officer.id)

        for staff in staff_users.distinct():
            Notification.objects.create(
                user=staff,
                title=_("Malipo Mapya (AzamPay)"),
                message=notification_msg
            )

        # 2. Simulated SMS Notification
        sms_text = _("Habari, Malipo ya TZS {} kwa ajili ya Mkopo {} yamepokelewa. Risiti: {}. Asante!").format(
            amount_paid, loan.loan_id, receipt_no
        )
        send_sms(loan.client.phone, sms_text)

        # Send SMS notify to Admin too
        admin_sms = _("Arifa: Mteja {} amelipia TZS {} kwa mkopo {}. Risiti: {}").format(
            loan.client.get_full_name(), amount_paid, loan.loan_id, receipt_no
        )
        for staff in staff_users.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER]):
            if staff.phone:
                send_sms(staff.phone, admin_sms)

        # 3. Email Notification to Admin/Staff
        emails = [s.email for s in staff_users if s.email]
        if emails:
            try:
                send_mail(
                    subject=_("MMS - Arifa ya Malipo ya AzamPay"),
                    message=notification_msg,
                    from_email="noreply@mejas.co.tz",
                    recipient_list=emails,
                    fail_silently=True
                )
            except Exception as e:
                print(f"Email failed to send: {e}")

        log_activity(loan.client, "CLIENT_AZAMPAY_REPAYMENT", f"Self-paid TZS {amount_paid} via AzamPay ({operator}). Receipt: {receipt_no}", request)
        messages.success(request, _("Marejesho yako ya TZS {} yamepokelewa kikamilifu kupitia AzamPay! Risiti yako ni {}.").format(amount_paid, receipt_no))

    return redirect("dashboard")


# --- DAILY REPAYMENT TRACKING ---

@login_required
def daily_repayment_tracking_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER, User.Role.OFFICER]:
        raise Http404(_("Ruhusa imekataliwa."))

    # Sync overdue loans & penalties
    sync_overdue_loans_and_penalties()

    # Parse selected date (default to today)
    date_str = request.GET.get("date", "").strip()
    today = datetime.date.today()
    if date_str:
        try:
            selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    branch_id = request.GET.get("branch", "").strip()
    officer_id = request.GET.get("officer", "").strip()

    schedules = RepaymentSchedule.objects.filter(due_date=selected_date).select_related("loan", "loan__client", "loan__officer", "loan__branch")

    if branch_id:
        schedules = schedules.filter(loan__branch_id=branch_id)
    if officer_id:
        schedules = schedules.filter(loan__officer_id=officer_id)

    # Handle Bulk Reminder SMS to Unpaid Clients for the selected date
    if request.method == "POST" and "send_reminders" in request.POST:
        unpaid_schedules = schedules.filter(status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE])
        sent_count = 0
        for s in unpaid_schedules:
            client = s.loan.client
            pending_amt = s.installment_amount - s.paid_amount
            if client.phone:
                msg = _("MMS: Ndugu {}, tunakukumbusha rejesho lako la TZS {} kwa mkopo {}. Tafadhali fanya malipo kuepuka adhabu ya kuchelewa.").format(
                    client.get_full_name(), pending_amt, s.loan.loan_id
                )
                send_sms(client.phone, msg)
                sent_count += 1
            # In-app notification
            Notification.objects.create(
                user=client,
                title=_("Kikumbusho cha Malipo ya Leo"),
                message=_("Rejesho lako la TZS {} kwa mkopo {} linatakiwa kulipwa leo tarehe {}.").format(
                    pending_amt, s.loan.loan_id, selected_date.strftime("%d/%m/%Y")
                )
            )

        log_activity(request.user, "DAILY_TRACKING_REMINDERS_SENT", f"Dispatched {sent_count} SMS reminders for date {selected_date}", request)
        messages.success(request, _("Vikumbusho vya SMS {} vimetumwa kikamilifu kwa wateja ambao hawajalipa!").format(sent_count))
        return redirect(f"{request.path}?date={selected_date.strftime('%Y-%m-%d')}&branch={branch_id}&officer={officer_id}")

    # Compute KPI statistics for the selected date
    total_expected = schedules.aggregate(s=Sum("installment_amount"))["s"] or Decimal("0.00")
    total_collected = schedules.aggregate(s=Sum("paid_amount"))["s"] or Decimal("0.00")
    collection_rate_percent = ((total_collected / total_expected) * 100).quantize(Decimal("0.1")) if total_expected > 0 else Decimal("0.0")

    paid_count = schedules.filter(status=RepaymentSchedule.Status.PAID).count()
    unpaid_count = schedules.filter(status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE], paid_amount=Decimal("0.00")).count()
    partial_count = schedules.filter(status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE], paid_amount__gt=Decimal("0.00")).count()

    branches = Branch.objects.all()
    officers = User.objects.filter(role=User.Role.OFFICER)

    return render(request, "tracking/daily_tracking.html", {
        "schedules": schedules,
        "branches": branches,
        "officers": officers,
        "branch_id": branch_id,
        "officer_id": officer_id,
        "selected_date": selected_date,
        "total_expected": total_expected,
        "total_collected": total_collected,
        "collection_rate_percent": collection_rate_percent,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "partial_count": partial_count,
    })



# --- CASH FLOW & DAILY RECONCILIATION ---

@login_required
def cash_flow_list_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER]:
        raise Http404(_("Ruhusa imekataliwa."))

    flows = CashFlow.objects.all().order_by("-date")

    # Filter by branch if Cashier
    if request.user.role == User.Role.CASHIER:
        if request.user.branch:
            flows = flows.filter(branch=request.user.branch)

    branch_id = request.GET.get("branch", "")
    if branch_id and request.user.role in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        flows = flows.filter(branch_id=branch_id)

    category_filter = request.GET.get("category", "")
    if category_filter:
        flows = flows.filter(category=category_filter)

    branches = Branch.objects.all()

    return render(request, "cash_flow/flow_list.html", {
        "flows": flows,
        "branches": branches,
        "branch_id": branch_id,
        "category_filter": category_filter
    })


@login_required
def office_cash_flow_record_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER]:
        raise Http404(_("Ruhusa imekataliwa."))

    if request.method == "POST":
        form = OfficeCashFlowForm(request.POST)
        if form.is_valid():
            flow = form.save(commit=False)
            if flow.category == "OFFICE_INCOME":
                flow.flow_type = CashFlow.FlowType.IN
            else:
                flow.flow_type = CashFlow.FlowType.OUT
            flow.recorded_by = request.user
            flow.save()
            log_activity(request.user, f"OFFICE_CASHFLOW_RECORD", f"Recorded {flow.get_category_display()} of TZS {flow.amount} for branch {flow.branch.name}", request)
            messages.success(request, _("Mtiririko wa fedha za ofisi umerekodiwa!"))
            return redirect("cash_flow_list")
    else:
        form = OfficeCashFlowForm(initial={"branch": request.user.branch})

    return render(request, "cash_flow/record_flow.html", {"form": form})


@login_required
def daily_reconciliation_view(request):
    if request.user.role != User.Role.CASHIER:
        raise Http404(_("Ruhusa imekataliwa."))

    if not request.user.branch:
        messages.error(request, _("Hauna tawi ulilopangiwa! Wasiliana na meneja."))
        return redirect("dashboard")

    today = datetime.date.today()
    branch = request.user.branch

    # Calculate today's flow details
    today_flows = CashFlow.objects.filter(branch=branch, date__date=today)
    total_received = today_flows.filter(flow_type="IN").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    total_disbursed = today_flows.filter(flow_type="OUT").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

    # Yesterday's closing
    yesterday = today - datetime.timedelta(days=1)
    prev_recon = DailyReconciliation.objects.filter(branch=branch, status="CONFIRMED").order_by("-date").first()
    opening_balance = prev_recon.actual_cash if prev_recon else Decimal("0.00")

    existing_recon = DailyReconciliation.objects.filter(branch=branch, date=today).first()

    if request.method == "POST":
        form = DailyReconciliationForm(request.POST, instance=existing_recon)
        if form.is_valid():
            recon = form.save(commit=False)
            recon.branch = branch
            recon.date = today
            recon.cashier = request.user
            recon.opening_balance = opening_balance
            recon.total_received = total_received
            recon.total_disbursed = total_disbursed
            recon.status = DailyReconciliation.Status.PENDING
            recon.save()
            log_activity(request.user, "DAILY_RECONCILIATION_SUBMITTED", f"Submitted EOD Cash Reconciliation for branch {branch.name}", request)
            messages.success(request, _("Funga hesabu ya siku imewasilishwa kwa meneja kwa ajili ya uhakiki."))
            return redirect("dashboard")
    else:
        form = DailyReconciliationForm(instance=existing_recon)

    return render(request, "cash_flow/daily_reconciliation.html", {
        "form": form,
        "opening_balance": opening_balance,
        "total_received": total_received,
        "total_disbursed": total_disbursed,
        "calculated_closing": opening_balance + total_received - total_disbursed,
        "existing_recon": existing_recon
    })


@login_required
def reconciliation_list_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))

    recons = DailyReconciliation.objects.all().order_by("-date")
    return render(request, "cash_flow/recon_list.html", {"recons": recons})


@login_required
def reconciliation_approve_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))

    recon = get_object_or_404(DailyReconciliation, pk=pk, status=DailyReconciliation.Status.PENDING)

    if request.method == "POST":
        decision = request.POST.get("decision")
        if decision == "CONFIRMED":
            recon.status = DailyReconciliation.Status.CONFIRMED
            recon.confirmed_by = request.user
            recon.confirmation_date = timezone.now()
            recon.save()
            log_activity(request.user, "DAILY_RECONCILIATION_CONFIRMED", f"Confirmed EOD Reconciliation for branch {recon.branch.name} on {recon.date}", request)
            messages.success(request, _("Funga hesabu ya siku imethibitishwa kikamilifu."))
        elif decision == "REJECTED":
            recon.status = DailyReconciliation.Status.REJECTED
            recon.confirmed_by = request.user
            recon.confirmation_date = timezone.now()
            recon.save()
            log_activity(request.user, "DAILY_RECONCILIATION_REJECTED", f"Rejected EOD Reconciliation for branch {recon.branch.name} on {recon.date}", request)
            messages.warning(request, _("Funga hesabu ya siku imekataliwa."))
        return redirect("reconciliation_list")

    return render(request, "cash_flow/recon_approve.html", {"recon": recon})


# --- REPORTS GENERATION & EXPORT ---

@login_required
def reports_menu_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))
    return render(request, "reports/menu.html")


@login_required
def generate_report_view(request, report_type):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    export_format = request.GET.get("export") or request.GET.get("export_format", "")

    # Date filters
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=30)
    end_date = today

    if start_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    title = ""
    headers = []
    rows = []

    # 1. Daily Paid/Unpaid Report
    if report_type == "daily_status":
        title = _("Ripoti ya Wateja Waliolipa na Wasiolipa ya tarehe {}").format(end_date)
        headers = [_("Jina la Mteja"), _("Namba ya Simu"), _("Namba ya Mkopo"), _("Kiasi cha Kulipa Leo"), _("Kiasi Kilicholipwa"), _("Hali ya Malipo")]
        schedules = RepaymentSchedule.objects.filter(due_date=end_date)
        for sched in schedules:
            rows.append([
                sched.loan.client.get_full_name(),
                sched.loan.client.phone or "",
                sched.loan.loan_id,
                sched.installment_amount,
                sched.paid_amount,
                sched.get_status_display()
            ])

    # 2. Disbursement Report
    elif report_type == "disbursement":
        title = _("Ripoti ya Mikopo Iliyotolewa (Muda: {} hadi {})").format(start_date, end_date)
        headers = [_("Tarehe"), _("Tawi"), _("Namba ya Mkopo"), _("Mteja"), _("Principal Amount"), _("Riba (%)"), _("Jumla ya Rejesho")]
        loans = Loan.objects.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE], disbursement_date__range=[start_date, end_date])
        for l in loans:
            rows.append([
                l.disbursement_date,
                l.branch.name,
                l.loan_id,
                l.client.get_full_name(),
                l.principal_amount,
                l.interest_rate,
                l.total_repayable
            ])

    # 3. Collection Report
    elif report_type == "collection":
        title = _("Ripoti ya Marejesho / Makusanyo (Muda: {} hadi {})").format(start_date, end_date)
        headers = [_("Tarehe/Muda"), _("Namba ya Mkopo"), _("Mteja"), _("Kiasi Kilicholipwa"), _("Namba ya Risiti"), _("Mhazini / Officer")]
        payments = Payment.objects.filter(payment_date__date__range=[start_date, end_date])
        for p in payments:
            rows.append([
                p.payment_date,
                p.loan.loan_id,
                p.loan.client.get_full_name(),
                p.amount_paid,
                p.receipt_no,
                p.cashier_or_officer.get_full_name() if p.cashier_or_officer else ""
            ])

    # 4. Overdue/Defaulters Report
    elif report_type == "overdue":
        title = _("Ripoti ya Mikopo Chechefu na Iliyochelewa (Tarehe: {})").format(today)
        headers = [_("Namba ya Mkopo"), _("Mteja"), _("Simu"), _("Principal"), _("Salio Lililobaki"), _("Adhabu Iliyolimbikizwa"), _("Hali")]
        loans = Loan.objects.filter(status__in=[Loan.Status.OVERDUE, Loan.Status.DEFAULTED])
        for l in loans:
            l.calculate_penalties()
            rows.append([
                l.loan_id,
                l.client.get_full_name(),
                l.client.phone or "",
                l.principal_amount,
                l.balance,
                l.penalty_accumulated,
                l.get_status_display()
            ])

    # 5. Income & Expenditure Report
    elif report_type == "income_expense":
        title = _("Ripoti ya Mapato na Matumizi ya Ofisi (Muda: {} hadi {})").format(start_date, end_date)
        headers = [_("Tarehe/Muda"), _("Tawi"), _("Kundi"), _("Maelezo"), _("Aina"), _("Kiasi")]
        flows = CashFlow.objects.filter(category__in=["OFFICE_INCOME", "OFFICE_EXPENSE"], date__date__range=[start_date, end_date])
        for f in flows:
            rows.append([
                f.date,
                f.branch.name,
                f.get_category_display(),
                f.description or "",
                f.get_flow_type_display(),
                f.amount
            ])

    # 6. Portfolio Performance Report
    elif report_type == "portfolio":
        title = _("Ripoti ya Utendaji wa Kila Loan Officer (Tarehe: {})").format(today)
        headers = [_("Jina la Loan Officer"), _("Idadi ya Mikopo ya sasa"), _("Mikopo Active"), _("Mikopo Iliyochelewa"), _("Jumla ya Balance za Wateja")]
        officers = User.objects.filter(role=User.Role.OFFICER)
        for o in officers:
            o_loans = Loan.objects.filter(officer=o)
            tot_bal = o_loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE]).aggregate(s=Sum("balance"))["s"] or 0
            rows.append([
                o.get_full_name(),
                o_loans.count(),
                o_loans.filter(status=Loan.Status.ACTIVE).count(),
                o_loans.filter(status=Loan.Status.OVERDUE).count(),
                tot_bal
            ])

    # 7. Financial Summary Report (CEO Core)
    elif report_type == "financial_summary":
        title = _("Ripoti Kuu ya Kifedha kwa CEO (Muda: {} hadi {})").format(start_date, end_date)
        headers = [_("Kipengele cha Kifedha"), _("Kiasi cha Sasa (TZS)")]

        tot_disb = CashFlow.objects.filter(category="DISBURSEMENT", date__date__range=[start_date, end_date]).aggregate(s=Sum("amount"))["s"] or 0
        tot_coll = CashFlow.objects.filter(category="COLLECTION", date__date__range=[start_date, end_date]).aggregate(s=Sum("amount"))["s"] or 0
        tot_inc = CashFlow.objects.filter(category="OFFICE_INCOME", date__date__range=[start_date, end_date]).aggregate(s=Sum("amount"))["s"] or 0
        tot_exp = CashFlow.objects.filter(category="OFFICE_EXPENSE", date__date__range=[start_date, end_date]).aggregate(s=Sum("amount"))["s"] or 0

        rows = [
            [_("Jumla ya Mikopo Iliyotolewa (Disbursements)"), tot_disb],
            [_("Jumla ya Marejesho ya Mikopo (Collections)"), tot_coll],
            [_("Jumla ya Mapato Mengine ya Ofisi (Incomes)"), tot_inc],
            [_("Jumla ya Matumizi Mengine ya Ofisi (Expenses)"), tot_exp],
            [_("Bakaa ya Mtiririko wa Fedha (Net Cash flow)"), (tot_coll + tot_inc) - (tot_disb + tot_exp)]
        ]

    # Handle Exports
    if export_format == "pdf":
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=25,
            leftMargin=25,
            topMargin=25,
            bottomMargin=25
        )
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=15,
            textColor=colors.HexColor('#114139'),
            spaceAfter=3,
            alignment=1
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            textColor=colors.HexColor('#475569'),
            spaceAfter=12,
            alignment=1
        )
        cell_style = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=10
        )
        header_style = ParagraphStyle(
            'HeaderCell',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            textColor=colors.white,
            leading=10
        )

        elements.append(Paragraph("MEJAS ENTERPRISES MICROFINANCE", title_style))
        elements.append(Paragraph(f"<b>{title}</b><br/>Kipindi: {start_date.strftime('%d/%m/%Y')} hadi {end_date.strftime('%d/%m/%Y')} | Imetolewa: {today.strftime('%d/%m/%Y %H:%M')}", subtitle_style))
        elements.append(Spacer(1, 8))

        # Build table rows
        table_data = [[Paragraph(f"<b>{h}</b>", header_style) for h in headers]]
        for r in rows:
            row_items = []
            for cell in r:
                if isinstance(cell, (datetime.date, datetime.datetime)):
                    val_str = cell.strftime("%d/%m/%Y %H:%M") if isinstance(cell, datetime.datetime) else cell.strftime("%d/%m/%Y")
                elif isinstance(cell, (int, float, Decimal)):
                    val_str = f"TZS {cell:,.2f}" if isinstance(cell, Decimal) else str(cell)
                else:
                    val_str = str(cell) if cell is not None else "-"
                row_items.append(Paragraph(val_str, cell_style))
            table_data.append(row_items)

        col_count = len(headers) if headers else 1
        avail_width = 545
        col_w = avail_width / col_count

        t = Table(table_data, colWidths=[col_w] * col_count)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#114139')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 18))

        signoff = Paragraph(
            "<b>Afisa Aliyeidhinisha (Manager/CEO):</b> ___________________________ &nbsp;&nbsp;&nbsp;&nbsp; <b>Saini:</b> ____________ &nbsp;&nbsp;&nbsp;&nbsp; <b>Tarehe:</b> ____________",
            cell_style
        )
        elements.append(signoff)
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("<font size='7' color='#94a3b8'>Mfumo Rasmi wa Kidigitali wa Uendeshaji wa Microfinance (MMS) &copy; 2026 Mejas Microfinance.</font>", subtitle_style))

        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{today}.pdf"'
        return response

    elif export_format == "excel":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = report_type[:30]
        ws.append([title])
        ws.append([]) # empty row
        ws.append(headers)
        for r in rows:
            # format date objects as strings
            row_vals = [str(x) if not isinstance(x, (int, float, Decimal)) else float(x) for x in r]
            ws.append(row_vals)

        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{report_type}_report_{today}.xlsx"'
        wb.save(response)
        return response

    elif export_format == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{report_type}_report_{today}.csv"'
        writer = csv.writer(response)
        writer.writerow([title])
        writer.writerow([])
        writer.writerow(headers)
        for r in rows:
            writer.writerow([str(x) for x in r])
        return response


    return render(request, "reports/generate.html", {
        "title": title,
        "headers": headers,
        "rows": rows,
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date
    })


# --- PUBLIC PAGES ---

def home_view(request):
    # Some quick summary stats to display on home page
    stats = {
        "active_clients": User.objects.filter(role=User.Role.CLIENT).count() + 140,
        "disbursed_loans": Loan.objects.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE]).count() + 95,
        "branches_count": Branch.objects.count() if Branch.objects.count() > 0 else 3,
    }
    return render(request, "public/home.html", {"stats": stats})


def about_view(request):
    return render(request, "public/about.html")


def contact_view(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        subject = request.POST.get("subject")
        message_body = request.POST.get("message")

        messages.success(request, _("Asante {}, Ujumbe wako umepokelewa! Tutawasiliana nawe hivi karibuni.").format(name))
        return redirect("contact")

    return render(request, "public/contact.html")


@login_required
def audit_log_list_view(request):
    """
    Displays system-wide user activity logs with role-based restrictions.
    Only CEO, Admin, and Managers can view audit logs.
    """
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        raise Http404(_("Ruhusa imekataliwa."))

    logs = AuditLog.objects.all().order_by("-timestamp")

    # Search & filters
    q = request.GET.get("q", "")
    action_filter = request.GET.get("action", "")
    user_filter = request.GET.get("user", "")

    if q:
        logs = logs.filter(
            Q(description__icontains=q) |
            Q(ip_address__icontains=q)
        )
    if action_filter:
        logs = logs.filter(action=action_filter)
    if user_filter:
        logs = logs.filter(user_id=user_filter)

    # Distinct actions for filter dropdown
    available_actions = AuditLog.objects.values_list("action", flat=True).distinct()
    available_users = User.objects.all()

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 25)  # 25 logs per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "tracking/audit_logs.html", {
        "page_obj": page_obj,
        "search_query": q,
        "selected_action": action_filter,
        "selected_user": user_filter,
        "available_actions": available_actions,
        "available_users": available_users,
    })


from django.core import serializers
from django.apps import apps

@login_required
def db_backup_view(request):
    """
    Exports a complete serialized JSON backup of the system database.
    Strictly restricted to CEO and Admin roles.
    """
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN]:
        raise Http404(_("Ruhusa imekataliwa."))

    # Collect all model records
    mms_models = apps.get_app_config("mms_app").get_models()

    # Collect all querysets
    all_objects = []
    for model in mms_models:
        all_objects.extend(list(model.objects.all()))

    # Serialize
    data = serializers.serialize("json", all_objects, indent=4)

    # Create downloadable response
    response = HttpResponse(data, content_type="application/json")
    filename = f"mms_backup_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    log_activity(request.user, "DATABASE_BACKUP_DOWNLOAD", "User downloaded a full database backup snapshot", request)
    return response


@login_required
def db_restore_view(request):
    """
    Imports and deserializes a JSON backup file to restore database records.
    Strictly restricted to CEO and Admin roles.
    """
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN]:
        raise Http404(_("Ruhusa imekataliwa."))

    if request.method == "POST":
        backup_file = request.FILES.get("backup_file")
        if not backup_file:
            messages.error(request, _("Tafadhali chagua faili la backup la kurejesha."))
            return redirect("audit_log_list")

        try:
            data = backup_file.read().decode("utf-8")

            # Deserialize and save each object
            count = 0
            for obj in serializers.deserialize("json", data):
                obj.save()
                count += 1

            log_activity(request.user, "DATABASE_RESTORE_SUCCESS", f"Successfully restored {count} database objects from uploaded backup", request)
            messages.success(request, _("Database imerejeshwa kikamilifu! Jumla ya vitu vilivyorejeshwa: {}").format(count))
        except Exception as e:
            messages.error(request, _("Imeshindikana kurejesha database. Sababu: {}").format(e))
            log_activity(request.user, "DATABASE_RESTORE_FAILED", f"Database restore failed: {e}", request)

    return redirect("audit_log_list")
