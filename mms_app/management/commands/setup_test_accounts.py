from decimal import Decimal
from django.core.management.base import BaseCommand
from mms_app.models import Branch, User, ClientProfile

class Command(BaseCommand):
    help = "Seeds the database with test accounts for the 5 different roles as requested in SRS."

    def handle(self, *args, **options):
        self.stdout.write("Seeding test accounts...")

        # 1. Create a Default Branch
        branch, created = Branch.objects.get_or_create(
            name="Dar es Salaam (HQ)",
            defaults={"location": "Sam Nujoma Road, Dar es Salaam"}
        )
        if created:
            self.stdout.write(f"Created branch: {branch.name}")
        else:
            self.stdout.write(f"Branch already exists: {branch.name}")

        # 2. CEO / Mkurugenzi
        ceo, created = User.objects.get_or_create(
            username="ceo",
            defaults={
                "first_name": "John",
                "last_name": "Meja",
                "email": "ceo@mejas.co.tz",
                "role": User.Role.CEO,
                "phone": "+255711111111",
                "nida": "19900101-11111-00001-11",
                "is_active": True
            }
        )
        if created:
            ceo.set_password("CEO_password123")
            ceo.save()
            self.stdout.write("Created CEO user: username 'ceo', password 'CEO_password123'")
        else:
            self.stdout.write("CEO user already exists.")

        # 3. Manager
        manager, created = User.objects.get_or_create(
            username="manager",
            defaults={
                "first_name": "Amina",
                "last_name": "Said",
                "email": "manager@mejas.co.tz",
                "role": User.Role.MANAGER,
                "branch": branch,
                "phone": "+255722222222",
                "nida": "19920202-22222-00002-22",
                "is_active": True
            }
        )
        if created:
            manager.set_password("Manager_password123")
            manager.save()
            self.stdout.write("Created Manager user: username 'manager', password 'Manager_password123'")
        else:
            self.stdout.write("Manager user already exists.")

        # 4. Cashier
        cashier, created = User.objects.get_or_create(
            username="cashier",
            defaults={
                "first_name": "David",
                "last_name": "Temu",
                "email": "cashier@mejas.co.tz",
                "role": User.Role.CASHIER,
                "branch": branch,
                "phone": "+255733333333",
                "nida": "19930303-33333-00003-33",
                "is_active": True
            }
        )
        if created:
            cashier.set_password("Cashier_password123")
            cashier.save()
            self.stdout.write("Created Cashier user: username 'cashier', password 'Cashier_password123'")
        else:
            self.stdout.write("Cashier user already exists.")

        # 5. Loan Officer
        officer, created = User.objects.get_or_create(
            username="officer",
            defaults={
                "first_name": "Grace",
                "last_name": "Lema",
                "email": "officer@mejas.co.tz",
                "role": User.Role.OFFICER,
                "branch": branch,
                "phone": "+255744444444",
                "nida": "19940404-44444-00004-44",
                "is_active": True
            }
        )
        if created:
            officer.set_password("Officer_password123")
            officer.save()
            self.stdout.write("Created Loan Officer user: username 'officer', password 'Officer_password123'")
        else:
            self.stdout.write("Loan Officer user already exists.")

        # 6. Client (Mteja)
        client, created = User.objects.get_or_create(
            username="client",
            defaults={
                "first_name": "Juma",
                "last_name": "Kaseja",
                "email": "client@gmail.com",
                "role": User.Role.CLIENT,
                "branch": branch,
                "phone": "+255755555555",
                "nida": "19950505-55555-00005-55",
                "is_active": True
            }
        )
        if created:
            client.set_password("Client_password123")
            client.save()

            # Create profile for client
            ClientProfile.objects.create(
                user=client,
                address="Kijitonyama, Dar es Salaam",
                guarantor_name="Rashid Juma",
                guarantor_phone="+255766666666",
                guarantor_nida="19850505-88888-00008-88",
                guarantor_address="Sinza, Dar es Salaam",
                guarantor_relationship="Kaka (Brother)"
            )
            self.stdout.write("Created Client user and profile: username 'client', password 'Client_password123'")
        else:
            self.stdout.write("Client user already exists.")

        self.stdout.write(self.style.SUCCESS("Successfully seeded all 5 test accounts!"))
