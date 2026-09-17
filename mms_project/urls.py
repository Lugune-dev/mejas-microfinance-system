"""
URL configuration for mms_project project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),  # Language switching endpoint
]

from mms_app import views as mms_views

# Using i18n_patterns for internationalized URLs (e.g. /sw/dashboard/ or /en/dashboard/)
urlpatterns += i18n_patterns(
    path("admin/daily-tracking/", mms_views.admin_daily_tracking_view, name="admin_daily_tracking"),
    path("admin/reports/", mms_views.admin_reports_menu_view, name="admin_reports_menu"),
    path("admin/reports/<str:report_type>/", mms_views.admin_generate_report_view, name="admin_generate_report"),
    path("admin/", admin.site.urls),
    path("", include("mms_app.urls")),
    path("payments/", include("payments.urls")),
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
