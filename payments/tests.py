from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from mms_app.models import Branch, User, Loan
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
            interest_rate=Decimal("10.00"),
            duration=10,
            status=Loan.Status.ACTIVE
        )
        self.client = Client()

    def test_initiate_payment_view(self):
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
        self.assertEqual(tx.status, PaymentTransaction.Status.SUCCESS)
