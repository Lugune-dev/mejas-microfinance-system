import requests
from django.conf import settings
from django.utils import timezone


class AzamPayService:
    """
    Service class handling AzamPay API Integration.
    (Token Generation, MNO Checkout, Status Verification)

    IMPORTANT: This service NEVER marks a payment as SUCCESS.
    A successful checkout only means a push prompt was sent to the customer's phone.
    Final payment confirmation MUST come via the AzamPay webhook callback.
    """

    def __init__(self):
        self.app_name = getattr(settings, "AZAMPAY_APP_NAME", "MEJAS_MMS")
        self.client_id = getattr(settings, "AZAMPAY_CLIENT_ID", "")
        self.client_secret = getattr(settings, "AZAMPAY_CLIENT_SECRET", "")
        self.api_key = getattr(settings, "AZAMPAY_API_KEY", "")
        self.base_url = getattr(settings, "AZAMPAY_BASE_URL", "https://checkout.azampay.co.tz")

    def get_auth_token(self):
        """
        Retrieves bearer auth token from AzamPay API gateway.
        Returns the token string, or None if authentication fails.
        """
        url = f"{self.base_url}/azampay/mno/token"
        headers = {"Content-Type": "application/json"}
        payload = {
            "appName": self.app_name,
            "clientId": self.client_id,
            "clientSecret": self.client_secret
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                token = data.get("data", {}).get("accessToken")
                if token:
                    return token
                print(f"AzamPay Auth: Token field missing in response: {data}")
        except requests.exceptions.Timeout:
            print("AzamPay Auth Token request timed out.")
        except Exception as e:
            print(f"AzamPay Auth Token request exception: {e}")
        return None

    def initiate_checkout(self, amount, phone_number, operator, reference_id, loan_id):
        """
        Initiates mobile checkout payment via AzamPay API.
        Operators: AIRTEL, MPESA, TIGOPESA, HALOPESA

        Return values:
          - push_sent: True  → API accepted the request. A USSD/push prompt was sent to
                               the customer's phone. Transaction stays PENDING until the
                               AzamPay webhook confirms payment.
          - push_sent: False → API call failed entirely. Transaction should be marked FAILED
                               immediately. No push was sent to the customer.

        NOTE: `push_sent: True` does NOT mean payment was successful.
        """
        token = self.get_auth_token()
        if not token:
            return {
                "push_sent": False,
                "message": "Imeshindikana kupata idhini kutoka AzamPay. Tafadhali angalia mipangilio ya API au wasiliana na msaada wa kiufundi."
            }

        # Normalize operator name to AzamPay's expected format
        provider_map = {
            "AIRTEL": "Airtel",
            "MPESA": "Mpesa",
            "TIGOPESA": "Tigo",
            "HALOPESA": "Halopesa",
        }
        mno_provider = provider_map.get(operator.upper(), "Airtel")

        url = f"{self.base_url}/azampay/mno/checkout"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
        }
        payload = {
            "accountNumber": phone_number,
            "amount": str(amount),
            "currency": "TZS",
            "externalId": reference_id,
            "provider": mno_provider,
            "additionalProperties": {
                "loan_id": str(loan_id),
                "nmb_destination": getattr(settings, "NMB_BANK_ACCOUNT_NUMBER", "12345678901")
            }
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            res_data = {}
            try:
                res_data = response.json()
            except Exception:
                pass

            if response.status_code in [200, 201]:
                # AzamPay accepted the push. Transaction is now PENDING confirmation.
                return {
                    "push_sent": True,
                    "transaction_id": res_data.get("transactionId", f"AZ-{reference_id}"),
                    "message": res_data.get(
                        "message",
                        "Ombi la malipo limetumwa kwenye simu yako. Tafadhali thibitisha kwa kuingiza PIN yako ya mtandao wa simu."
                    ),
                    "raw": res_data
                }
            else:
                # Gateway returned a non-200 response — push was NOT sent
                error_text = res_data.get("message") or response.text[:200] or f"HTTP {response.status_code}"
                print(f"AzamPay Checkout returned {response.status_code}: {error_text}")
                return {
                    "push_sent": False,
                    "message": f"Gateway ilikataa ombi (Hitilafu {response.status_code}). Jaribu tena baadaye.",
                    "raw": res_data
                }

        except requests.exceptions.Timeout:
            print(f"AzamPay Checkout timed out for reference {reference_id}")
            return {
                "push_sent": False,
                "message": "Muunganisho na gateway ulishindwa (timeout). Angalia intaneti yako na ujaribu tena."
            }
        except Exception as e:
            print(f"AzamPay Checkout exception for ref {reference_id}: {e}")
            return {
                "push_sent": False,
                "message": "Kosa la kiufundi limetokea. Wasiliana na msaada wa kiufundi."
            }
