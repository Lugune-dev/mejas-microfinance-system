import datetime
from decimal import Decimal
from django.utils import timezone
from django.utils.translation import gettext as _
from .models import AuditLog, Loan, RepaymentSchedule, Notification, User

def log_activity(user, action, description, request=None):
    """
    Utility function to log user activities for security auditing.
    """
    ip_addr = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_addr = x_forwarded_for.split(',')[0]
        else:
            ip_addr = request.META.get('REMOTE_ADDR')

    AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        action=action,
        description=description,
        ip_address=ip_addr
    )


def send_sms(to_phone, message_text):
    """
    Simulates sending an SMS through a Tanzanian SMS Gateway (e.g., Beem SMS, NextSMS).
    In development and testing, it logs beautifully to console and activity trail.
    """
    if not to_phone:
        return False
    print(f"============================================================")
    print(f"--- SMS GATEWAY TRANSMISSION ---")
    print(f"TO: {to_phone}")
    print(f"MESSAGE: {message_text}")
    print(f"STATUS: DELIVERED (Simulated)")
    print(f"============================================================")
    return True


def sync_overdue_loans_and_penalties():
    """
    Evaluates all active/overdue loans and schedules.
    Marks overdue schedules, calculates penalties, updates loan statuses (OVERDUE / DEFAULTED),
    and dispatches alerts to Officers and Managers.
    """
    today = datetime.date.today()
    loans = Loan.objects.filter(status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE])

    overdue_count = 0
    defaulted_count = 0
    total_penalty_applied = Decimal("0.00")

    for loan in loans:
        # Check schedules whose due date has passed and are not fully paid
        overdue_scheds = loan.schedules.filter(due_date__lt=today, status__in=[RepaymentSchedule.Status.UNPAID, RepaymentSchedule.Status.OVERDUE])

        if overdue_scheds.exists():
            # Mark each schedule as overdue
            overdue_scheds.update(status=RepaymentSchedule.Status.OVERDUE)

            # Determine maximum days overdue
            oldest_due = overdue_scheds.order_by("due_date").first().due_date
            days_overdue = (today - oldest_due).days

            # Classify Defaulted vs Overdue
            if days_overdue > 60:
                loan.status = Loan.Status.DEFAULTED
                defaulted_count += 1
            else:
                loan.status = Loan.Status.OVERDUE
                overdue_count += 1

            # Compute penalty (defaults to 5% late penalty if not specified, per SRS)
            effective_rate = loan.penalty_rate if loan.penalty_rate > 0 else Decimal("5.00")
            penalty_sum = Decimal("0.00")
            for sched in overdue_scheds:
                unpaid_part = sched.installment_amount - sched.paid_amount
                if unpaid_part > 0:
                    penalty_sum += (unpaid_part * (effective_rate / Decimal("100.0"))).quantize(Decimal("0.01"))
            loan.penalty_accumulated = penalty_sum
            total_penalty_applied += penalty_sum

            loan.save()

            # Create Alert for Loan Officer if not already alerted today
            if loan.officer:
                alert_title = f"Onyo: Mkopo {loan.loan_id} Umechelewa"
                already_alerted = Notification.objects.filter(
                    user=loan.officer,
                    title=alert_title,
                    created_at__date=today
                ).exists()

                if not already_alerted:
                    Notification.objects.create(
                        user=loan.officer,
                        title=alert_title,
                        message=f"Mteja {loan.client.get_full_name()} (Simu: {loan.client.phone or 'N/A'}) ana rejesho lililochelewa kwa siku {days_overdue}. Salio lililobaki: TZS {loan.balance}."
                    )
        else:
            # If loan has no overdue schedules and has remaining balance, keep ACTIVE
            if loan.balance > Decimal("0.00"):
                if loan.status != Loan.Status.ACTIVE:
                    loan.status = Loan.Status.ACTIVE
                    loan.save()
            else:
                loan.status = Loan.Status.COMPLETED
                loan.save()

    return {
        "overdue_count": overdue_count,
        "defaulted_count": defaulted_count,
        "total_penalty_applied": total_penalty_applied
    }


def calculate_client_credit_score(client_user):
    """
    Computes a smart Credit Standing badge and score for a client
    based on historical loan payments, completed loans, and overdue counts.
    Returns a dict with 'score', 'badge_class', 'label', and 'description'.
    """
    loans = Loan.objects.filter(client=client_user)
    if not loans.exists():
        return {
            "score": "MPYA",
            "rating": "A",
            "badge_class": "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
            "label": _("Mteja Mpya (New Client)"),
            "description": _("Hana historia ya mikopo ya awali.")
        }

    total_loans = loans.count()
    completed_loans = loans.filter(status=Loan.Status.COMPLETED).count()
    overdue_loans = loans.filter(status=Loan.Status.OVERDUE).count()
    defaulted_loans = loans.filter(status=Loan.Status.DEFAULTED).count()

    if defaulted_loans > 0:
        return {
            "score": "D",
            "rating": "D",
            "badge_class": "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
            "label": _("Chechefu (Defaulted / High Risk)"),
            "description": _("Ana mkopo usiorejeshwa uliopitisha muda mrefu.")
        }
    elif overdue_loans > 0:
        return {
            "score": "C",
            "rating": "C",
            "badge_class": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
            "label": _("Makini (Overdue / Attention Needed)"),
            "description": _("Ana marejesho yaliyochelewa kwa sasa.")
        }
    elif completed_loans >= 2:
        return {
            "score": "AAA",
            "rating": "AAA",
            "badge_class": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
            "label": _("Mteja Bora Sana (Excellent Client)"),
            "description": _("Ameshakamilisha mikopo kwa uaminifu wa hali ya juu.")
        }
    else:
        return {
            "score": "AA",
            "rating": "AA",
            "badge_class": "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
            "label": _("Mteja Mzuri (Good Standing)"),
            "description": _("Marejesho yake yanaendelea vizuri bila ucheleweshaji.")
        }

