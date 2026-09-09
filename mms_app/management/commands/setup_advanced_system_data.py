import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from mms_app.models import (
    Branch, User, ClientProfile, Loan, RepaymentSchedule,
    Payment, CashFlow, DailyReconciliation, AuditLog, Notification
)
from mms_app.utils import sync_overdue_loans_and_penalties

class Command(BaseCommand):
    help = "Seeds the database (including Supabase) with complete, advanced microfinance data for all 5 roles, branches, loans, and schedules."

    def handle(self, *args, **options):
        self.stdout.write("--- Starting Advanced MMS Database Seeding ---")

        today = datetime.date.today()

        # 1. Create Branches
        b_hq, _ = Branch.objects.get_or_create(
            name="Dar es Salaam (HQ)",
            defaults={"location": "Sam Nujoma Road, Dar es Salaam"}
        )
        b_arusha, _ = Branch.objects.get_or_create(
            name="Arusha Branch",
            defaults={"location": "Sokoine Road, Arusha City"}
        )
        b_mwanza, _ = Branch.objects.get_or_create(
            name="Mwanza Branch",
            defaults={"location": "Kenyatta Road, Mwanza"}
        )
        b_dodoma, _ = Branch.objects.get_or_create(
            name="Dodoma Branch",
            defaults={"location": "Kuu Street, Dodoma Capital"}
        )
        self.stdout.write(self.style.SUCCESS("✓ 4 Branches created/verified"))

        # 2. Setup 5 Core Test Accounts (+ Admin)
        # CEO
        ceo, _ = User.objects.get_or_create(
            username="ceo",
            defaults={
                "first_name": "John",
                "last_name": "Meja",
                "email": "ceo@mejas.co.tz",
                "role": User.Role.CEO,
                "phone": "+255711111111",
                "nida": "19900101-11111-00001-11",
                "is_active": True,
                "branch": b_hq
            }
        )
        ceo.set_password("CEO_password123")
        ceo.save()

        # Manager
        manager, _ = User.objects.get_or_create(
            username="manager",
            defaults={
                "first_name": "Amina",
                "last_name": "Said",
                "email": "manager@mejas.co.tz",
                "role": User.Role.MANAGER,
                "phone": "+255722222222",
                "nida": "19920202-22222-00002-22",
                "is_active": True,
                "branch": b_hq
            }
        )
        manager.set_password("Manager_password123")
        manager.save()

        # Cashier
        cashier, _ = User.objects.get_or_create(
            username="cashier",
            defaults={
                "first_name": "David",
                "last_name": "Temu",
                "email": "cashier@mejas.co.tz",
                "role": User.Role.CASHIER,
                "phone": "+255733333333",
                "nida": "19930303-33333-00003-33",
                "is_active": True,
                "branch": b_hq
            }
        )
        cashier.set_password("Cashier_password123")
        cashier.save()

        # Loan Officer
        officer, _ = User.objects.get_or_create(
            username="officer",
            defaults={
                "first_name": "Grace",
                "last_name": "Lema",
                "email": "officer@mejas.co.tz",
                "role": User.Role.OFFICER,
                "phone": "+255744444444",
                "nida": "19940404-44444-00004-44",
                "is_active": True,
                "branch": b_hq
            }
        )
        officer.set_password("Officer_password123")
        officer.save()

        # Client 1 (Primary Test Client)
        client1, _ = User.objects.get_or_create(
            username="client",
            defaults={
                "first_name": "Juma",
                "last_name": "Kaseja",
                "email": "client@gmail.com",
                "role": User.Role.CLIENT,
                "phone": "+255755555555",
                "nida": "19950505-55555-00005-55",
                "is_active": True,
                "branch": b_hq
            }
        )
        client1.set_password("Client_password123")
        client1.save()

        ClientProfile.objects.get_or_create(
            user=client1,
            defaults={
                "address": "Kijitonyama, Dar es Salaam",
                "guarantor_name": "Rashid Juma",
                "guarantor_phone": "+255766666666",
                "guarantor_nida": "19850505-88888-00008-88",
                "guarantor_address": "Sinza, Dar es Salaam",
                "guarantor_relationship": "Kaka (Brother)"
            }
        )

        # Admin
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "first_name": "Admin",
                "last_name": "User",
                "email": "admin@mejas.co.tz",
                "role": User.Role.ADMIN,
                "phone": "+255766666666",
                "nida": "19960606-66666-00006-66",
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
                "branch": b_hq
            }
        )
        admin.set_password("Admin_password123")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

        # Additional clients for testing diverse scenarios
        client2, _ = User.objects.get_or_create(
            username="baraka",
            defaults={
                "first_name": "Baraka",
                "last_name": "Mushi",
                "email": "baraka@gmail.com",
                "role": User.Role.CLIENT,
                "phone": "+255754111222",
                "nida": "19910101-22222-00002-22",
                "is_active": True,
                "branch": b_arusha
            }
        )
        client2.set_password("Baraka_password123")
        client2.save()
        ClientProfile.objects.get_or_create(
            user=client2,
            defaults={
                "address": "Sanawari, Arusha",
                "guarantor_name": "Anna Mushi",
                "guarantor_phone": "+255754999888",
                "guarantor_nida": "19920202-33333-00003-33",
                "guarantor_address": "Kijenge, Arusha",
                "guarantor_relationship": "Mke (Wife)"
            }
        )

        client3, _ = User.objects.get_or_create(
            username="asha",
            defaults={
                "first_name": "Asha",
                "last_name": "Bakari",
                "email": "asha@gmail.com",
                "role": User.Role.CLIENT,
                "phone": "+255715333444",
                "nida": "19930303-44444-00004-44",
                "is_active": True,
                "branch": b_hq
            }
        )
        client3.set_password("Asha_password123")
        client3.save()
        ClientProfile.objects.get_or_create(
            user=client3,
            defaults={
                "address": "Ilala Boma, Dar es Salaam",
                "guarantor_name": "Bakari Omari",
                "guarantor_phone": "+255715777666",
                "guarantor_nida": "19700101-55555-00005-55",
                "guarantor_address": "Buguruni, Dar es Salaam",
                "guarantor_relationship": "Baba (Father)"
            }
        )

        self.stdout.write(self.style.SUCCESS("✓ 5 Core Roles & Test Accounts configured"))

        # 3. Create Diverse Loans
        # Loan 1: Active Loan for client1 (Juma Kaseja)
        loan1, created = Loan.objects.get_or_create(
            loan_id="LN-20260810-0001",
            defaults={
                "client": client1,
                "officer": officer,
                "branch": b_hq,
                "principal_amount": Decimal("500000.00"),
                "interest_rate": Decimal("5.00"),
                "duration": 10,
                "frequency": Loan.Frequency.DAILY,
                "total_repayable": Decimal("525000.00"),
                "installment_amount": Decimal("52500.00"),
                "balance": Decimal("367500.00"),
                "status": Loan.Status.ACTIVE,
                "application_date": today - datetime.timedelta(days=10),
                "approval_date": today - datetime.timedelta(days=9),
                "approved_by": manager,
                "disbursement_date": today - datetime.timedelta(days=8),
                "disbursed_by": cashier,
                "penalty_rate": Decimal("2.00"),
                "penalty_accumulated": Decimal("0.00")
            }
        )

        # Repayment schedules for Loan 1
        if not loan1.schedules.exists():
            for i in range(1, 11):
                due_d = (today - datetime.timedelta(days=8)) + datetime.timedelta(days=i)
                status = RepaymentSchedule.Status.PAID if i <= 3 else RepaymentSchedule.Status.UNPAID
                paid_amt = Decimal("52500.00") if i <= 3 else Decimal("0.00")
                RepaymentSchedule.objects.create(
                    loan=loan1,
                    due_date=due_d,
                    installment_amount=Decimal("52500.00"),
                    paid_amount=paid_amt,
                    status=status
                )

        # Record Payments for Loan 1 (3 payments of 52,500)
        if not loan1.payments.exists():
            for i in range(1, 4):
                Payment.objects.create(
                    loan=loan1,
                    cashier_or_officer=cashier,
                    amount_paid=Decimal("52500.00"),
                    payment_date=timezone.now() - datetime.timedelta(days=8-i),
                    receipt_no=f"REC-20260812-000{i}"
                )

        # Loan 2: Overdue Loan for client2 (Neema Mollel)
        loan2, _ = Loan.objects.get_or_create(
            loan_id="LN-20260815-0002",
            defaults={
                "client": client2,
                "officer": officer,
                "branch": b_arusha,
                "principal_amount": Decimal("300000.00"),
                "interest_rate": Decimal("5.00"),
                "duration": 5,
                "frequency": Loan.Frequency.WEEKLY,
                "total_repayable": Decimal("315000.00"),
                "installment_amount": Decimal("63000.00"),
                "balance": Decimal("315000.00"),
                "status": Loan.Status.OVERDUE,
                "application_date": today - datetime.timedelta(days=25),
                "approval_date": today - datetime.timedelta(days=24),
                "approved_by": manager,
                "disbursement_date": today - datetime.timedelta(days=23),
                "disbursed_by": cashier,
                "penalty_rate": Decimal("3.00"),
                "penalty_accumulated": Decimal("3780.00")
            }
        )

        if not loan2.schedules.exists():
            for i in range(1, 6):
                due_d = (today - datetime.timedelta(days=23)) + datetime.timedelta(weeks=i)
                status = RepaymentSchedule.Status.OVERDUE if due_d < today else RepaymentSchedule.Status.UNPAID
                RepaymentSchedule.objects.create(
                    loan=loan2,
                    due_date=due_d,
                    installment_amount=Decimal("63000.00"),
                    paid_amount=Decimal("0.00"),
                    status=status
                )

        # Loan 3: Completed Loan for Asha Bakari
        loan3, _ = Loan.objects.get_or_create(
            loan_id="LN-20260701-0003",
            defaults={
                "client": client3,
                "officer": officer,
                "branch": b_hq,
                "principal_amount": Decimal("200000.00"),
                "interest_rate": Decimal("5.00"),
                "duration": 4,
                "frequency": Loan.Frequency.WEEKLY,
                "total_repayable": Decimal("210000.00"),
                "installment_amount": Decimal("52500.00"),
                "balance": Decimal("0.00"),
                "status": Loan.Status.COMPLETED,
                "application_date": today - datetime.timedelta(days=40),
                "approval_date": today - datetime.timedelta(days=39),
                "approved_by": manager,
                "disbursement_date": today - datetime.timedelta(days=38),
                "disbursed_by": cashier,
                "penalty_rate": Decimal("0.00"),
                "penalty_accumulated": Decimal("0.00")
            }
        )

        if not loan3.schedules.exists():
            for i in range(1, 5):
                RepaymentSchedule.objects.create(
                    loan=loan3,
                    due_date=(today - datetime.timedelta(days=38)) + datetime.timedelta(weeks=i),
                    installment_amount=Decimal("52500.00"),
                    paid_amount=Decimal("52500.00"),
                    status=RepaymentSchedule.Status.PAID
                )
            Payment.objects.create(
                loan=loan3,
                cashier_or_officer=cashier,
                amount_paid=Decimal("210000.00"),
                payment_date=timezone.now() - datetime.timedelta(days=10),
                receipt_no="REC-20260715-0010"
            )

        # Loan 4: Pending Loan Application for Asha Bakari
        Loan.objects.get_or_create(
            loan_id="LN-20260908-0004",
            defaults={
                "client": client3,
                "officer": officer,
                "branch": b_hq,
                "principal_amount": Decimal("800000.00"),
                "interest_rate": Decimal("12.00"),
                "duration": 8,
                "frequency": Loan.Frequency.WEEKLY,
                "total_repayable": Decimal("896000.00"),
                "installment_amount": Decimal("112000.00"),
                "balance": Decimal("896000.00"),
                "status": Loan.Status.PENDING,
                "application_date": today,
                "penalty_rate": Decimal("2.00"),
                "penalty_accumulated": Decimal("0.00")
            }
        )

        self.stdout.write(self.style.SUCCESS("✓ Active, Overdue, Completed, and Pending Loans configured"))

        # 4. Seed CashFlow Entries
        if not CashFlow.objects.exists():
            # Initial disbursements
            CashFlow.objects.create(
                branch=b_hq,
                flow_type=CashFlow.FlowType.OUT,
                category=CashFlow.Category.DISBURSEMENT,
                amount=Decimal("500000.00"),
                date=timezone.now() - datetime.timedelta(days=8),
                description="Disbursement for Loan LN-20260810-0001",
                recorded_by=cashier
            )
            CashFlow.objects.create(
                branch=b_arusha,
                flow_type=CashFlow.FlowType.OUT,
                category=CashFlow.Category.DISBURSEMENT,
                amount=Decimal("300000.00"),
                date=timezone.now() - datetime.timedelta(days=23),
                description="Disbursement for Loan LN-20260815-0002",
                recorded_by=cashier
            )
            # Collections
            CashFlow.objects.create(
                branch=b_hq,
                flow_type=CashFlow.FlowType.IN,
                category=CashFlow.Category.COLLECTION,
                amount=Decimal("165000.00"),
                date=timezone.now() - datetime.timedelta(days=5),
                description="Repayment collections for Loan LN-20260810-0001",
                recorded_by=cashier
            )
            # Office Income & Expenses
            CashFlow.objects.create(
                branch=b_hq,
                flow_type=CashFlow.FlowType.IN,
                category=CashFlow.Category.OFFICE_INCOME,
                amount=Decimal("45000.00"),
                date=timezone.now() - datetime.timedelta(days=3),
                description="Loan application processing and ledger registration fees",
                recorded_by=cashier
            )
            CashFlow.objects.create(
                branch=b_hq,
                flow_type=CashFlow.FlowType.OUT,
                category=CashFlow.Category.OFFICE_EXPENSE,
                amount=Decimal("25000.00"),
                date=timezone.now() - datetime.timedelta(days=2),
                description="Office stationery and receipt printing roll supplies",
                recorded_by=cashier
            )

        # 5. Seed Daily Reconciliation
        DailyReconciliation.objects.get_or_create(
            branch=b_hq,
            date=today - datetime.timedelta(days=1),
            defaults={
                "cashier": cashier,
                "opening_balance": Decimal("500000.00"),
                "total_received": Decimal("165000.00"),
                "total_disbursed": Decimal("25000.00"),
                "calculated_closing": Decimal("640000.00"),
                "actual_cash": Decimal("640000.00"),
                "difference": Decimal("0.00"),
                "status": DailyReconciliation.Status.CONFIRMED,
                "confirmed_by": manager,
                "confirmation_date": timezone.now() - datetime.timedelta(days=1)
            }
        )

        # 6. Seed In-app Notifications
        Notification.objects.get_or_create(
            user=officer,
            title="Kikumbusho cha Marejesho ya Leo",
            defaults={
                "message": f"Wateja walioratibiwa kulipa leo wanahitaji ufuatiliaji wa marejesho.",
                "is_read": False
            }
        )
        Notification.objects.get_or_create(
            user=manager,
            title="Ombi Jipya la Mkopo Linasubiri Idhini",
            defaults={
                "message": f"Ombi jipya la mkopo la TZS 800,000 limewasilishwa na Grace Lema kwa mteja Asha Bakari.",
                "is_read": False
            }
        )

        # 7. Run overdue synchronization
        sync_result = sync_overdue_loans_and_penalties()
        self.stdout.write(f"Sync Results: Overdue loans: {sync_result['overdue_count']}, Defaulted: {sync_result['defaulted_count']}, Penalties: TZS {sync_result['total_penalty_applied']}")

        self.stdout.write(self.style.SUCCESS("=== Advanced Microfinance System Seeding Complete! ==="))
        self.stdout.write("Credentials ready for instant 1-click test login:")
        self.stdout.write("  - CEO:         username 'ceo',     password 'CEO_password123'")
        self.stdout.write("  - Manager:     username 'manager', password 'Manager_password123'")
        self.stdout.write("  - Cashier:     username 'cashier', password 'Cashier_password123'")
        self.stdout.write("  - Officer:     username 'officer', password 'Officer_password123'")
        self.stdout.write("  - Client:      username 'client',  password 'Client_password123'")
        self.stdout.write("  - Admin:       username 'admin',   password 'Admin_password123'")
