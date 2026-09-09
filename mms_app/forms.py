import re
from decimal import Decimal
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.utils.translation import gettext_lazy as _
from .models import User, ClientProfile, Loan, RepaymentSchedule, Payment, DailyReconciliation, Branch, CashFlow

class MMSLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            "class": "w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600",
            "placeholder": _("Username / Staff ID / Client No.")
        }),
        label=_("Staff ID / Client No / Username")
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600",
            "placeholder": "••••••••"
        }),
        label=_("Password")
    )


class UserForm(forms.ModelForm):
    """Form to create or update users (CEO, Manager, Cashier, Loan Officer)"""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "class": "w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600",
            "placeholder": "••••••••"
        }),
        required=False,
        label=_("Password (Leave blank to keep current)")
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "branch", "phone", "nida", "photo", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "first_name": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "last_name": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "email": forms.EmailInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "role": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "branch": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "phone": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "nida": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "photo": forms.FileInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"}),
        }

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            if len(password) < 8:
                raise forms.ValidationError(_("Password must be at least 8 characters long."))
            if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
                raise forms.ValidationError(_("Password must contain a mix of letters and numbers."))
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class ClientRegistrationForm(forms.ModelForm):
    """Client registration requires creating a User (username is Client No) with CLIENT role"""
    first_name = forms.CharField(widget=forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}), label=_("First Name"))
    last_name = forms.CharField(widget=forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}), label=_("Last Name"))
    phone = forms.CharField(widget=forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}), label=_("Phone Number"))
    nida = forms.CharField(widget=forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}), label=_("NIDA ID"))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}), label=_("Client Portal Password"), initial="Client123")
    branch = forms.ModelChoiceField(queryset=Branch.objects.all(), widget=forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}), label=_("Branch"))
    photo = forms.ImageField(required=False, widget=forms.FileInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}), label=_("Client Photo"))

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "phone", "nida", "branch", "photo", "password"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "placeholder": "e.g. CLI001"}),
        }

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            if len(password) < 8:
                raise forms.ValidationError(_("Password must be at least 8 characters long."))
            if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
                raise forms.ValidationError(_("Password must contain a mix of letters and numbers."))
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CLIENT
        user.set_password(self.cleaned_data.get("password"))
        if commit:
            user.save()
        return user


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = ClientProfile
        fields = ["address", "guarantor_name", "guarantor_phone", "guarantor_nida", "guarantor_address", "guarantor_relationship"]
        widgets = {
            "address": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "guarantor_name": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "guarantor_phone": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "guarantor_nida": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "guarantor_address": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "guarantor_relationship": forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
        }


class LoanApplicationForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ["client", "officer", "branch", "principal_amount", "interest_rate", "duration", "frequency", "penalty_rate"]
        widgets = {
            "client": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "officer": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "branch": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "principal_amount": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "interest_rate": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "duration": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "placeholder": _("Number of installments (e.g. 30 for 30 daily payments)")}),
            "frequency": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "penalty_rate": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "placeholder": _("e.g. 1% late payment penalty")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = User.objects.filter(role=User.Role.CLIENT)
        self.fields["officer"].queryset = User.objects.filter(role=User.Role.OFFICER)


class LoanApprovalForm(forms.ModelForm):
    decision = forms.ChoiceField(
        choices=[("APPROVED", _("Idhinisha / Approve")), ("REJECTED", _("Kataa / Reject"))],
        widget=forms.RadioSelect(attrs={"class": "inline-flex items-center"}),
        label=_("Decision")
    )

    class Meta:
        model = Loan
        fields = [] # Will only capture the custom decision and change state on submit


class PaymentRecordingForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount_paid"]
        widgets = {
            "amount_paid": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "placeholder": _("Enter amount paid")}),
        }


class OfficeCashFlowForm(forms.ModelForm):
    class Meta:
        model = CashFlow
        fields = ["branch", "category", "amount", "description"]
        widgets = {
            "branch": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "category": forms.Select(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "amount": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
            "description": forms.Textarea(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only allow Office Income and Office Expense in this general form (Disbursement and Collection are automatically logged)
        self.fields["category"].choices = [
            ("OFFICE_INCOME", _("Mapato ya Ofisi (Office Income)")),
            ("OFFICE_EXPENSE", _("Matumizi ya Ofisi (Office Expense)")),
        ]


class DailyReconciliationForm(forms.ModelForm):
    class Meta:
        model = DailyReconciliation
        fields = ["actual_cash"]
        widgets = {
            "actual_cash": forms.NumberInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "placeholder": _("Enter actual cash physical count")}),
        }


class PasswordResetForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "placeholder": _("Your Staff ID / Client No.")}),
        label=_("Staff ID / Client No / Username")
    )
    nida = forms.CharField(
        widget=forms.TextInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600", "placeholder": _("Your NIDA ID")}),
        label=_("NIDA ID")
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600"}),
        label=_("New Password")
    )

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if password:
            if len(password) < 8:
                raise forms.ValidationError(_("Password must be at least 8 characters long."))
            if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
                raise forms.ValidationError(_("Password must contain a mix of letters and numbers."))
        return password


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ["name", "location"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600",
                "placeholder": _("Mf. Tawi la Arusha, Dodoma, n.k.")
            }),
            "location": forms.TextInput(attrs={
                "class": "w-full px-4 py-2 border rounded-lg bg-white text-gray-900 dark:bg-gray-700 dark:text-white dark:border-gray-600",
                "placeholder": _("Mf. Barabara ya Sokoine, Arusha")
            }),
        }

