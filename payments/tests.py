from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from mms_app.models import Branch, User, Loan, Payment
from payments.models import PaymentTransaction


class PaymentsIntegrationTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Tawi Kuu")
        self.client_user = User.objects.create_user(
            username="testclient",
            password="password123",
            role=User.Role.CLIENT,
            branch=self.branch,
            phone="0784000111"
        )
        self.loan = Loan.objects.create(
            client=self.client_user,
            branch=self.branch,
            principal_amount=Decimal("100000.00"),
            interest_rate=Decimal("5.00"),
            duration=10,
            status=Loan.Status.ACTIVE
        )
        self.client = Client()

    @patch("payments.views.AzamPayService.initiate_checkout")
    def test_initiate_payment_view(self, mock_checkout):
        mock_checkout.return_value = {
            "success": True,
            "push_sent": True,
            "transaction_id": "AZAM-TX-999",
            "message": "Push prompt sent"
        }
        self.client.login(username="testclient", password="password123")
        url = reverse("payments:initiate_payment", args=[self.loan.pk])
        response = self.client.post(url, {
            "operator": "AIRTEL",
            "phone": "0784000111",
            "amount": "10000.00"
        })
        self.assertEqual(response.status_code, 302)
        tx = PaymentTransaction.objects.filter(loan=self.loan).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("10000.00"))
        self.assertEqual(tx.operator, "AIRTEL")
        self.assertEqual(tx.status, PaymentTransaction.Status.PENDING)

        # Now test webhook callback confirming payment
        webhook_url = reverse("payments:azampay_webhook")
        webhook_res = self.client.post(
            webhook_url,
            data={
                "externalId": tx.reference_id,
                "transactionStatus": "SUCCESS",
                "transactionId": "MNO-999888"
            },
            content_type="application/json"
        )
        self.assertEqual(webhook_res.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.status, PaymentTransaction.Status.SUCCESS)
        self.assertTrue(Payment.objects.filter(loan=self.loan).exists())

