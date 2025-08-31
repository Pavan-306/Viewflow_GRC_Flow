from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from viewflow.urls import Site, Application
from viewflow.workflow.flow import FlowAppViewset

from ticketflow.flows import TicketFlow

# ---- Viewflow Site & Application titles ----
site = Site(
    title="RISK Management",   # top-left site title
    viewsets=[
        Application(
            title="GRC Functional Requests",   # Applications menu item
            app_name="ticketflow",
            viewsets=[FlowAppViewset(TicketFlow, icon="assignment")],
        )
    ],
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)