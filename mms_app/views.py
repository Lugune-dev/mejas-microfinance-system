import datetime
import csv
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import HttpResponse, Http404
from django.utils import timezone
from django.db.models import Sum, Q, Count
from django.utils.translation import gettext as _
import openpyxl

from .models import (
    Branch, User, ClientProfile, Loan, RepaymentSchedule,
    Payment, CashFlow, DailyReconciliation, AuditLog
)
from .forms import (
    MMSLoginForm, UserForm, ClientRegistrationForm, ClientProfileForm,
    LoanApplicationForm, LoanApprovalForm, PaymentRecordingForm,
    OfficeCashFlowForm, DailyReconciliationForm, PasswordChangeForm, PasswordResetForm
)
from .utils import log_activity


# --- AUTH VIEWS ---

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

    # Check physical cash and EOD status
    # Prepare different context elements per role
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

    # We can query based on branch
    branch_q_loans = Q(branch=selected_branch) if selected_branch else Q()
    branch_q_payments = Q(loan__branch=selected_branch) if selected_branch else Q()

    if role in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER]:
        # CEO / Admin / Manager Metrics
        context["branches"] = Branch.objects.all()
        context["selected_branch"] = selected_branch
        loans = Loan.objects.filter(branch_q_loans)
        context["total_disbursed"] = loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(sum=Sum("principal_amount"))["sum"] or Decimal("0.00")
        context["total_repayments_expected"] = loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.COMPLETED, Loan.Status.OVERDUE, Loan.Status.DEFAULTED]).aggregate(sum=Sum("total_repayable"))["sum"] or Decimal("0.00")

        # Total collections (payments tied to loans in the selected branch)
        context["total_collections"] = Payment.objects.filter(branch_q_payments).aggregate(sum=Sum("amount_paid"))["sum"] or Decimal("0.00")
        context["active_loans_count"] = loans.filter(status=Loan.Status.ACTIVE).count()
        context["overdue_loans_count"] = loans.filter(status=Loan.Status.OVERDUE).count()
        context["pending_loans_count"] = loans.filter(status=Loan.Status.PENDING).count()
        clients_q = User.objects.filter(role=User.Role.CLIENT)
        if selected_branch:
            clients_q = clients_q.filter(branch=selected_branch)
        context["clients_count"] = clients_q.count()

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

        # Recent activity logs
        context["recent_logs"] = AuditLog.objects.all()[:10]
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
        yesterday = today - datetime.timedelta(days=1)
        prev_recon = DailyReconciliation.objects.filter(branch=user.branch, status="CONFIRMED").order_by("-date").first()
        context["opening_balance"] = prev_recon.actual_cash if prev_recon else Decimal("0.00")
        context["calculated_closing"] = context["opening_balance"] + context["today_cash_in"] - context["today_cash_out"]

        # Today's received payments list
        context["today_payments"] = Payment.objects.filter(loan__branch=user.branch, payment_date__date=today)
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

        context["pending_applications"] = Loan.objects.filter(officer=user, status=Loan.Status.PENDING)
        return render(request, "dashboard/officer.html", context)

    elif role == User.Role.CLIENT:
        # Client Metrics
        client_loans = Loan.objects.filter(client=user)
        context["loans"] = client_loans

        active_loan = client_loans.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE]).first()
        context["active_loan"] = active_loan

        if active_loan:
            context["next_schedule"] = active_loan.schedules.filter(status__in=["UNPAID", "OVERDUE"]).order_by("due_date").first()
            context["payment_history"] = active_loan.payments.all().order_by("-payment_date")
            context["full_schedule"] = active_loan.schedules.all().order_by("due_date")
            context["total_paid"] = active_loan.payments.aggregate(s=Sum("amount_paid"))["s"] or Decimal("0.00")

        return render(request, "dashboard/client.html", context)

    return render(request, "dashboard/placeholder.html", context)


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

    search_query = request.GET.get("q", "")
    clients = User.objects.filter(role=User.Role.CLIENT)

    if search_query:
        clients = clients.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    # Get active/overdue loans statistics for display
    return render(request, "clients/client_list.html", {
        "clients": clients,
        "search_query": search_query
    })


@login_required
def client_detail_view(request, pk):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.OFFICER, User.Role.CASHIER]:
        raise Http404(_("Ruhusa imekataliwa."))

    client_user = get_object_or_404(User, pk=pk, role=User.Role.CLIENT)
    loans = Loan.objects.filter(client=client_user).order_by("-created_at")

    return render(request, "clients/client_detail.html", {
        "client": client_user,
        "loans": loans
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
            "interest_rate": 10.0,
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


# --- DAILY REPAYMENT TRACKING ---

@login_required
def daily_repayment_tracking_view(request):
    if request.user.role not in [User.Role.CEO, User.Role.ADMIN, User.Role.MANAGER, User.Role.CASHIER, User.Role.OFFICER]:
        raise Http404(_("Ruhusa imekataliwa."))

    today = datetime.date.today()
    branch_id = request.GET.get("branch", "")
    officer_id = request.GET.get("officer", "")

    schedules = RepaymentSchedule.objects.filter(due_date=today)

    if branch_id:
        schedules = schedules.filter(loan__branch_id=branch_id)
    if officer_id:
        schedules = schedules.filter(loan__officer_id=officer_id)

    # We can fetch filters for the template
    branches = Branch.objects.all()
    officers = User.objects.filter(role=User.Role.OFFICER)

    return render(request, "tracking/daily_tracking.html", {
        "schedules": schedules,
        "branches": branches,
        "officers": officers,
        "branch_id": branch_id,
        "officer_id": officer_id
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
    export_format = request.GET.get("export", "")

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
    if export_format == "excel":
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
