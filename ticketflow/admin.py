import csv
from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.text import slugify
from openpyxl import Workbook

from .models import (
    Form,
    FormField,
    FormEntry,
    FormEntryValue,
    TicketProcess,
)

# -------------------- INLINE FIELDS UNDER FORM --------------------


class FormFieldInlineForm(forms.ModelForm):
    class Meta:
        model = FormField
        fields = "__all__"
        widgets = {
            "choices": forms.TextInput(attrs={"size": 40}),
            "help_text": forms.TextInput(attrs={"size": 40}),
        }


class FormFieldInline(admin.TabularInline):
    model = FormField
    form = FormFieldInlineForm
    extra = 1
    fields = (
        "order",
        "label",
        "field_type",
        "role",              # <- shows as: Risk Representative / Risk Champion / Risk Approver / CRO
        "required",
        "max_length",
        "choices",
        "help_text",
        "placeholder",
        "default_value",
        "min_value",
        "max_value",
        "regex",
        "readonly",
        "hidden",
    )
    ordering = ("order",)


@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ("name", "created")
    search_fields = ("name",)
    inlines = [FormFieldInline]


# -------------------- EXPORT HELPERS FOR FORM ENTRIES --------------------


def _ensure_single_form_or_error(modeladmin, request, queryset):
    """Require that selected entries belong to exactly one form."""
    form_ids = set(queryset.values_list("form_id", flat=True))
    if len(form_ids) != 1:
        modeladmin.message_user(
            request,
            "Please filter to ONE Form first (use the right-side filter), "
            "then select entries to export.",
            level=messages.ERROR,
        )
        return None
    return queryset.first().form


def export_entries_csv(modeladmin, request, queryset):
    form = _ensure_single_form_or_error(modeladmin, request, queryset)
    if not form:
        return

    fields = list(form.fields.all())
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{slugify(form.name)}_entries.csv"'
    )
    writer = csv.writer(response)

    header = ["Entry ID", "Submitted by", "Submitted at"] + [f.label for f in fields]
    writer.writerow(header)

    qs = (
        queryset.select_related("form", "submitted_by")
        .prefetch_related("values", "values__field")
        .order_by("id")
    )

    for entry in qs:
        values_map = {
            v.field_id: (v.value_text or (v.value_file.url if v.value_file else ""))
            for v in entry.values.all()
        }
        row = [
            entry.id,
            getattr(entry.submitted_by, "username", "") or "",
            entry.submitted_at.strftime("%Y-%m-%d %H:%M"),
        ] + [values_map.get(f.id, "") for f in fields]
        writer.writerow(row)

    return response


export_entries_csv.short_description = "Export selected entries to CSV"


def export_entries_xlsx(modeladmin, request, queryset):
    form = _ensure_single_form_or_error(modeladmin, request, queryset)
    if not form:
        return

    fields = list(form.fields.all())
    wb = Workbook()
    ws = wb.active
    ws.title = "Entries"

    header = ["Entry ID", "Submitted by", "Submitted at"] + [f.label for f in fields]
    ws.append(header)

    qs = (
        queryset.select_related("form", "submitted_by")
        .prefetch_related("values", "values__field")
        .order_by("id")
    )

    for entry in qs:
        values_map = {
            v.field_id: (v.value_text or (v.value_file.url if v.value_file else ""))
            for v in entry.values.all()
        }
        row = [
            entry.id,
            getattr(entry.submitted_by, "username", "") or "",
            entry.submitted_at.strftime("%Y-%m-%d %H:%M"),
        ] + [values_map.get(f.id, "") for f in fields]
        ws.append(row)

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{slugify(form.name)}_entries.xlsx"'
    )
    wb.save(response)
    return response


export_entries_xlsx.short_description = "Export selected entries to XLSX"


# -------------------- ADMIN REGISTRATIONS --------------------


@admin.register(FormEntry)
class FormEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "form", "submitted_by", "submitted_at")
    list_filter = ("form", "submitted_at")
    date_hierarchy = "submitted_at"
    search_fields = ("id", "form__name", "submitted_by__username")
    actions = [export_entries_csv, export_entries_xlsx]


@admin.register(TicketProcess)
class TicketProcessAdmin(admin.ModelAdmin):
    readonly_fields = (
        "ticket_data",
        "entry",
        "approved_by_user",
        "approved_by_dev",
        "approved_by_ba",
        "approved_by_pm",
        "user_comment",
        "dev_comment",
        "ba_comment",
        "pm_comment",
        "user_decision",
        "dev_decision",
        "ba_decision",
        "pm_decision",
    )
    list_display = ("id", "form", "entry")
    search_fields = ("id", "form__name")