import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Branch, User, ClientProfile, Loan, RepaymentSchedule, Payment, CashFlow, DailyReconciliation, AuditLog

class MMSCoreBusinessTests(TestCase):
    def setUp(self):
        # Create Branch
        self.branch = Branch.objects.create(name="Arusha Branch", location="Arusha Town")

        # Create Staff Users
        self.ceo = User.objects.create_user(
            username="test_ceo",
            password="CEO_password123",
            role=User.Role.CEO,
            branch=self.branch,
            phone="+255111",
            nida="12345-12345-12345"
        )
        self.manager = User.objects.create_user(
            username="test_manager",
            password="Manager_password123",
            role=User.Role.MANAGER,
            branch=self.branch,
            phone="+255222",
            nida="22345-22345-22345"
        )
        self.cashier = User.objects.create_user(
            username="test_cashier",
            password="Cashier_password123",
            role=User.Role.CASHIER,
            branch=self.branch,
            phone="+255333",
            nida="32345-32345-32345"
        )
        self.officer = User.objects.create_user(
            username="test_officer",
            password="Officer_password123",
            role=User.Role.OFFICER,
            branch=self.branch,
            phone="+255444",
            nida="42345-42345-42345"
        )
        self.client_user = User.objects.create_user(
            username="test_client",
            password="Client_password123",
            role=User.Role.CLIENT,
            branch=self.branch,
            phone="+255555",
            nida="52345-52345-52345"
        )

        # Create Client Profile
        self.profile = ClientProfile.objects.create(
            user=self.client_user,
            address="Arusha Area A",
            guarantor_name="Guarantor One",
            guarantor_phone="+255999",
            guarantor_nida="92345-92345-92345",
            guarantor_address="Arusha Area B",
            guarantor_relationship="Rafiki"
        )

    def test_user_creation_and_deactivation(self):
        """Verify that user role is assigned and account deactivation works."""
        self.assertEqual(self.client_user.role, User.Role.CLIENT)
        self.assertEqual(self.officer.role, User.Role.OFFICER)

        # Deactivation test
        self.officer.is_active = False
        self.officer.save()
        self.assertFalse(self.officer.is_active)

    def test_loan_calculations_and_disbursement(self):
        """Test loan interest calculations, approval, and repayment schedule creation upon disbursement."""
        # Create Loan Application (Status: PENDING)
        loan = Loan.objects.create(
            client=self.client_user,
            officer=self.officer,
            branch=self.branch,
            principal_amount=Decimal("100000.00"),
            interest_rate=Decimal("5.00"), # 5%
            duration=5, # 5 installments
            frequency=Loan.Frequency.DAILY
        )

        # Verify automatic calculation of total repayable and installment amounts
        # 100,000 + 5,000 (5%) = 105,000
        self.assertEqual(loan.total_repayable, Decimal("105000.00"))
        # 105,000 / 5 installments = 21,000 each
        self.assertEqual(loan.installment_amount, Decimal("21000.00"))
        self.assertEqual(loan.status, Loan.Status.PENDING)

        # Approve Loan by Manager
        loan.status = Loan.Status.APPROVED
        loan.approval_date = datetime.date.today()
        loan.approved_by = self.manager
        loan.save()
        self.assertEqual(loan.status, Loan.Status.APPROVED)

        # Disburse Loan by Cashier (Simulate views flow manually to test underlying objects/triggers)
        loan.status = Loan.Status.ACTIVE
        loan.disbursement_date = datetime.date.today()
        loan.disbursed_by = self.cashier
        loan.balance = loan.total_repayable
        loan.save()

        # Create repayment schedules sequentially
        today = datetime.date.today()
        for i in range(1, loan.duration + 1):
            RepaymentSchedule.objects.create(
                loan=loan,
                due_date=today + datetime.timedelta(days=i),
                installment_amount=loan.installment_amount,
                paid_amount=Decimal("0.00"),
                status=RepaymentSchedule.Status.UNPAID
            )

        # Log CashFlow OUT
        CashFlow.objects.create(
            branch=loan.branch,
            flow_type=CashFlow.FlowType.OUT,
            category=CashFlow.Category.DISBURSEMENT,
            amount=loan.principal_amount,
            recorded_by=self.cashier
        )

        self.assertEqual(loan.schedules.count(), 5)
        self.assertEqual(CashFlow.objects.filter(category=CashFlow.Category.DISBURSEMENT).count(), 1)

        # Verify outstanding balance remains 105,000 initially
        self.assertEqual(loan.balance, Decimal("105000.00"))

    def test_repayment_recording_and_allocation(self):
        """Test recording partial and full payments and sequential allocation across schedules."""
        loan = Loan.objects.create(
            client=self.client_user,
            officer=self.officer,
            branch=self.branch,
            principal_amount=Decimal("100000.00"),
            interest_rate=Decimal("5.00"),
            duration=5,
            frequency=Loan.Frequency.DAILY,
            status=Loan.Status.ACTIVE,
            balance=Decimal("105000.00")
        )

        # Create 5 schedules
        today = datetime.date.today()
        for i in range(1, 6):
            RepaymentSchedule.objects.create(
                loan=loan,
                due_date=today + datetime.timedelta(days=i),
                installment_amount=Decimal("21000.00"),
                paid_amount=Decimal("0.00"),
                status=RepaymentSchedule.Status.UNPAID
            )

        # 1. Record partial payment of TZS 30,000 (covers 1st schedule fully [21,000] and 2nd schedule partially [9,000])
        amount_paid = Decimal("30000.00")
        Payment.objects.create(
            loan=loan,
            cashier_or_officer=self.cashier,
            amount_paid=amount_paid
        )
        CashFlow.objects.create(
            branch=loan.branch,
            flow_type=CashFlow.FlowType.IN,
            category=CashFlow.Category.COLLECTION,
            amount=amount_paid,
            recorded_by=self.cashier
        )

        # Update Loan Balance
        loan.balance = max(Decimal("0.00"), loan.balance - amount_paid)
        loan.save()
        self.assertEqual(loan.balance, Decimal("75000.00"))

        # Allocate Payment sequentially
        remaining = amount_paid
        schedules = loan.schedules.all().order_by("due_date")
        for sched in schedules:
            if remaining <= 0:
                break
            due_balance = sched.installment_amount - sched.paid_amount
            if remaining >= due_balance:
                sched.paid_amount = sched.installment_amount
                sched.status = RepaymentSchedule.Status.PAID
                remaining -= due_balance
                sched.save()
            else:
                sched.paid_amount += remaining
                remaining = Decimal("0.00")
                sched.save()

        # Check first schedule status is PAID (Green)
        first_sched = loan.schedules.all().order_by("due_date")[0]
        self.assertEqual(first_sched.status, RepaymentSchedule.Status.PAID)
        self.assertEqual(first_sched.paid_amount, Decimal("21000.00"))

        # Check second schedule status is UNPAID but has partial payment of 9,000
        second_sched = loan.schedules.all().order_by("due_date")[1]
        self.assertEqual(second_sched.status, RepaymentSchedule.Status.UNPAID)
        self.assertEqual(second_sched.paid_amount, Decimal("9000.00"))

    def test_daily_reconciliation(self):
        """Test daily reconciliation workflow, opening balance, discrepancy computation and manager approval."""
        today = datetime.date.today()

        # Cashier records Collections flow
        CashFlow.objects.create(
            branch=self.branch,
            flow_type=CashFlow.FlowType.IN,
            category=CashFlow.Category.COLLECTION,
            amount=Decimal("50000.00"),
            recorded_by=self.cashier
        )
        # Cashier records Office expense flow
        CashFlow.objects.create(
            branch=self.branch,
            flow_type=CashFlow.FlowType.OUT,
            category=CashFlow.Category.OFFICE_EXPENSE,
            amount=Decimal("10000.00"),
            recorded_by=self.cashier
        )

        # Calculated ending should be Opening (0) + IN (50,000) - OUT (10,000) = 40,000
        # Cashier performs reconciliation with actual physical cash counted as 40,000 (No difference)
        recon = DailyReconciliation.objects.create(
            branch=self.branch,
            date=today,
            cashier=self.cashier,
            opening_balance=Decimal("0.00"),
            total_received=Decimal("50000.00"),
            total_disbursed=Decimal("10000.00"),
            actual_cash=Decimal("40000.00"),
            status=DailyReconciliation.Status.PENDING
        )
        self.assertEqual(recon.calculated_closing, Decimal("40000.00"))
        self.assertEqual(recon.difference, Decimal("0.00"))
        self.assertEqual(recon.status, DailyReconciliation.Status.PENDING)

        # Manager approves
        recon.status = DailyReconciliation.Status.CONFIRMED
        recon.confirmed_by = self.manager
        recon.confirmation_date = timezone.now()
        recon.save()

        self.assertEqual(recon.status, DailyReconciliation.Status.CONFIRMED)
        self.assertEqual(recon.confirmed_by, self.manager)

    def test_audit_logging_mechanism(self):
        """Ensure audit logs are written for core activities."""
        AuditLog.objects.create(
            user=self.ceo,
            action="USER_LOGIN",
            description="CEO logged in from main terminal"
        )
        self.assertEqual(AuditLog.objects.filter(action="USER_LOGIN").count(), 1)
        self.assertEqual(AuditLog.objects.first().user, self.ceo)

    def test_public_pages(self):
        """Verify that Home, About, and Contact public pages load and render successfully."""
        client = Client()

        # Test Home Page
        res_home = client.get(reverse("home"), follow=True)
        self.assertEqual(res_home.status_code, 200)
        self.assertContains(res_home, "Mejas Enterprises")

        # Test About Page
        res_about = client.get(reverse("about"), follow=True)
        self.assertEqual(res_about.status_code, 200)
        self.assertContains(res_about, "Sisi ni Nani?")

        # Test Contact Page
        res_contact = client.get(reverse("contact"), follow=True)
        self.assertEqual(res_contact.status_code, 200)
        self.assertContains(res_contact, "Tutumie Ujumbe")

        # Test Contact Form Submit
        post_data = {
            "name": "Juma Hamisi",
            "email": "juma@hamisi.com",
            "subject": "Inquiry about business loan",
            "message": "I need a loan for my retail shop."
        }
        res_submit = client.post(reverse("contact"), post_data, follow=True)
        self.assertEqual(res_submit.status_code, 200)
        self.assertContains(res_submit, "Asante Juma Hamisi")

    def test_rbac_restrictions(self):
        """Verify that role-based access control blocks clients from accessing management URLs."""
        client = Client()
        # Log in as client
        client.login(username="test_client", password="Client_password123")

        # Client should be blocked from user management
        res_users = client.get(reverse("user_list"))
        self.assertEqual(res_users.status_code, 404)

        # Client should be blocked from office cash flow record
        res_cf = client.get(reverse("record_office_cash_flow"))
        self.assertEqual(res_cf.status_code, 404)

        # Client should be blocked from generating reports
        res_rep = client.get(reverse("reports_menu"))
        self.assertEqual(res_rep.status_code, 404)

    def test_two_factor_authentication_flow(self):
        """Verify the 2FA intercept flow, session storing, and verification view."""
        # Enable 2FA for the cashier user
        self.cashier.two_factor_enabled = True
        self.cashier.save()

        client = Client()
        # Post credentials to standard login
        res_login = client.post(reverse("login"), {"username": "test_cashier", "password": "Cashier_password123"}, follow=True)

        # Verify redirect to 2FA verification page
        self.assertContains(res_login, "Thibitisha 2FA")
        self.assertIn("pre_2fa_user_id", client.session)
        self.assertIn("otp_code", client.session)

        # Retrieve generated code from session
        otp_code = client.session["otp_code"]

        # Submit incorrect OTP code
        res_fail = client.post(reverse("verify_2fa"), {"otp_code": "000000"}, follow=True)
        self.assertContains(res_fail, "si sahihi")

        # Submit correct OTP code
        res_success = client.post(reverse("verify_2fa"), {"otp_code": otp_code}, follow=True)
        self.assertRedirects(res_success, reverse("dashboard"))

    def test_database_backup_and_restore(self):
        """Verify backup download as JSON and successful database restore mechanism."""
        client = Client()
        client.login(username="test_ceo", password="CEO_password123")

        # 1. Trigger Backup download
        res_backup = client.get(reverse("db_backup"))
        self.assertEqual(res_backup.status_code, 200)
        self.assertEqual(res_backup["content-type"], "application/json")
        backup_data = res_backup.content.decode("utf-8")
        self.assertIn("Arusha Branch", backup_data)  # checks serialized branch name is present

        # 2. Trigger Restore upload simulation
        import io
        backup_file = io.BytesIO(res_backup.content)
        backup_file.name = "backup.json"

        res_restore = client.post(reverse("db_restore"), {"backup_file": backup_file}, follow=True)
        self.assertEqual(res_restore.status_code, 200)
        self.assertContains(res_restore, "imerejeshwa kikamilifu")

    def test_branch_management_crud(self):
        """Verify branch list, creation, and update."""
        client = Client()
        client.login(username="test_ceo", password="CEO_password123")

        # List branches
        res_list = client.get(reverse("branch_list"))
        self.assertEqual(res_list.status_code, 200)
        self.assertContains(res_list, "Arusha Branch")

        # Create branch
        res_create = client.post(reverse("branch_create"), {
            "name": "Mwanza Branch",
            "location": "Nyamagana, Mwanza"
        }, follow=True)
        self.assertEqual(res_create.status_code, 200)
        self.assertTrue(Branch.objects.filter(name="Mwanza Branch").exists())

    def test_sync_overdue_and_penalties(self):
        """Verify overdue loan auto-flagging and penalty computation."""
        from mms_app.utils import sync_overdue_loans_and_penalties
        
        # Create an active loan with past due date
        loan = Loan.objects.create(
            client=self.client_user,
            branch=self.branch,
            principal_amount=Decimal("200000.00"),
            interest_rate=Decimal("5.00"),
            penalty_rate=Decimal("5.00"),
            duration=3,
            status=Loan.Status.ACTIVE
        )
        past_date = timezone.now().date() - datetime.timedelta(days=10)
        schedule = RepaymentSchedule.objects.create(
            loan=loan,
            due_date=past_date,
            installment_amount=Decimal("70000.00"),
            status=RepaymentSchedule.Status.UNPAID
        )
        
        results = sync_overdue_loans_and_penalties()
        schedule.refresh_from_db()
        loan.refresh_from_db()
        
        self.assertEqual(schedule.status, RepaymentSchedule.Status.OVERDUE)
        self.assertEqual(loan.status, Loan.Status.OVERDUE)
        self.assertGreater(loan.penalty_accumulated, Decimal("0.00"))

    def test_client_credit_score(self):
        """Verify calculation of client credit scores."""
        from mms_app.utils import calculate_client_credit_score
        score_data = calculate_client_credit_score(self.client_user)
        self.assertIn(score_data["rating"], ["A", "AAA", "AA", "C", "D"])

    def test_daily_repayment_tracking(self):
        """Verify daily repayment tracking view and reminder trigger."""
        client = Client()
        client.login(username="test_officer", password="Officer_password123")

        today_str = timezone.now().date().strftime("%Y-%m-%d")
        res = client.get(reverse("daily_repayment_tracking"), {"date": today_str})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ufuatiliaji wa Marejesho ya Kila Siku")

        # Test bulk reminders action
        res_remind = client.post(reverse("daily_repayment_tracking"), {
            "date": today_str,
            "send_reminders": "1"
        }, follow=True)
        self.assertEqual(res_remind.status_code, 200)

    def test_pdf_report_generation(self):
        """Verify ReportLab PDF generation for reports."""
        client = Client()
        client.login(username="test_ceo", password="CEO_password123")

        res_pdf = client.get(reverse("generate_report", kwargs={"report_type": "disbursement"}), {
            "export": "pdf"
        })
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf["content-type"], "application/pdf")
        self.assertIn("attachment; filename=", res_pdf["content-disposition"])

    def test_client_dashboard_and_loan_statement_pdf(self):
        """Verify client dashboard with active loan loads without NoReverseMatch and statement PDF works."""
        # Create an active loan with schedule and payment for client_user
        loan = Loan.objects.create(
            client=self.client_user,
            officer=self.officer,
            branch=self.branch,
            principal_amount=Decimal("50000.00"),
            interest_rate=Decimal("5.00"),
            duration=2,
            frequency=Loan.Frequency.DAILY,
            status=Loan.Status.ACTIVE,
            disbursement_date=timezone.now().date()
        )
        RepaymentSchedule.objects.create(
            loan=loan,
            due_date=timezone.now().date(),
            installment_amount=Decimal("26250.00"),
            status=RepaymentSchedule.Status.UNPAID
        )
        Payment.objects.create(
            loan=loan,
            amount_paid=Decimal("10000.00"),
            cashier_or_officer=self.officer
        )

        client = Client()
        client.login(username="test_client", password="Client_password123")

        # 1. Test Client Dashboard
        res_dash = client.get(reverse("dashboard"))
        self.assertEqual(res_dash.status_code, 200)
        self.assertContains(res_dash, "Pakua Statement (PDF)")
        self.assertContains(res_dash, reverse("loan_statement_pdf", kwargs={"pk": loan.pk}))

        # 2. Test Loan Statement PDF Generation
        res_pdf = client.get(reverse("loan_statement_pdf", kwargs={"pk": loan.pk}))
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf["content-type"], "application/pdf")
        self.assertIn(f'filename="loan_statement_{loan.loan_id}.pdf"', res_pdf["content-disposition"])
        self.assertGreater(len(res_pdf.content), 500)

        # 3. Test Permission: Another client cannot access this loan statement
        other_client = User.objects.create_user(
            username="other_client",
            password="Other_password123",
            role=User.Role.CLIENT,
            branch=self.branch,
            phone="+255888"
        )
        client.login(username="other_client", password="Other_password123")
        res_unauthorized = client.get(reverse("loan_statement_pdf", kwargs={"pk": loan.pk}))
        self.assertEqual(res_unauthorized.status_code, 404)

        # 4. Test Staff (CEO/Officer) can access statement PDF
        client.login(username="test_officer", password="Officer_password123")
        res_officer = client.get(reverse("loan_statement_pdf", kwargs={"pk": loan.pk}))
        self.assertEqual(res_officer.status_code, 200)
        self.assertEqual(res_officer["content-type"], "application/pdf")

    def test_admin_dashboard_metrics_and_bars(self):
        """Verify the modernized Django admin dashboard renders financial metrics, spline charts, and recent activity."""
        self.ceo.is_staff = True
        self.ceo.is_superuser = True
        self.ceo.save()

        client = Client()
        client.login(username="test_ceo", password="CEO_password123")

        res_admin = client.get(reverse("admin:index"))
        self.assertEqual(res_admin.status_code, 200)
        self.assertContains(res_admin, "Dashboard")
        self.assertContains(res_admin, "Total Active Portfolio")
        self.assertContains(res_admin, "Yield on Portfolio")
        self.assertContains(res_admin, "Revenue & Capital Flow")
        self.assertContains(res_admin, "Portfolio Breakdown")
        self.assertContains(res_admin, "Recent Loans")
        self.assertContains(res_admin, "Recent Activity")
        self.assertContains(res_admin, "mms-kpi-sparkline")
        self.assertContains(res_admin, "mms-svg-chart")






