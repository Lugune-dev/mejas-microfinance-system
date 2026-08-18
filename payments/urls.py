from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("initiate/<int:loan_id>/", views.initiate_payment_view, name="initiate_payment"),
    path("webhook/azampay/", views.azampay_webhook_view, name="azampay_webhook"),
]
