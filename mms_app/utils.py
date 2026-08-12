from django.utils import timezone
from .models import AuditLog

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
    In development, it prints beautifully to the console.
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
