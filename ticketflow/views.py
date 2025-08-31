from django import forms
from django.core.mail import EmailMultiAlternatives
from viewflow.workflow.flow.views import CreateProcessView, UpdateProcessView

from .models import TicketProcess, Form as FormModel, FormEntry, FormEntryValue, FormField
from .forms import add_fields_to_form, ApprovalForm


def _values_map_for_entry(entry: FormEntry) -> dict[int, tuple[str, str]]:
    """
    Return {field_id -> (display_text, file_url_or_empty)} for the current entry.
    """
    out = {}
    for v in entry.values.all():
        if v.value_file:
            out[v.field_id] = (v.value_file.name, getattr(v.value_file, "url", ""))
        else:
            out[v.field_id] = (v.value_text or "", "")
    return out


def build_ticket_summary_html(process: TicketProcess) -> str:
    """
    Build an HTML table in form field order with latest values (from FormEntry).
    Files are rendered as clickable links when possible.
    """
    if not process.entry:
        return "<p><em>No data yet</em></p>"

    values_map = _values_map_for_entry(process.entry)
    rows = []
    for ff in process.form.fields.all():
        txt, url = values_map.get(ff.id, ("", ""))
        val_html = f'<a href="{url}" target="_blank" rel="noopener">{txt}</a>' if url else txt
        rows.append(
            f"<tr>"
            f"<th style='text-align:left;padding:4px 8px'>{ff.label}</th>"
            f"<td style='padding:4px 8px'>{val_html}</td>"
            f"</tr>"
        )
    return "<table border='1' cellpadding='0' cellspacing='0' style='border-collapse:collapse'>" + "".join(rows) + "</table>"


def _update_entry_values_for_role(entry: FormEntry, form_obj: FormModel, cleaned_data: dict, files, role: str):
    """
    Create/update FormEntryValue for fields of the given role using cleaned_data/files.
    `role` is the role code: 'user', 'dev', 'ba', or 'pm'.
    """
    for ff in form_obj.fields.filter(role=role):
        key = str(ff.id)
        if ff.field_type == FormField.FILE:
            file_obj = (files or {}).get(key)
            if file_obj:
                v, _ = FormEntryValue.objects.get_or_create(entry=entry, field=ff)
                v.value_text = ""
                v.value_file = file_obj
                v.save()
        else:
            val = cleaned_data.get(key, "")
            v, _ = FormEntryValue.objects.get_or_create(entry=entry, field=ff)
            v.value_file = None
            v.value_text = str(val) if val is not None else ""
            v.save()


def _snapshot_from_entry(entry: FormEntry) -> dict:
    """
    Flatten values into a {label: value} dict for quick display/email.
    If a value is a file, we store just the filename.
    """
    snap = {}
    for ff in entry.form.fields.all():
        try:
            v = entry.values.get(field=ff)
            snap[ff.label] = v.value_text or (v.value_file.name if v.value_file else "")
        except FormEntryValue.DoesNotExist:
            snap[ff.label] = ""
    return snap


def send_submission_emails(process: TicketProcess, subject_prefix="New submission"):
    """
    Email notify_emails (console backend in dev) with an HTML table snapshot.
    """
    form_obj = process.form
    emails = [e.strip() for e in (form_obj.notify_emails or "").split(",") if e.strip()]
    if not emails:
        return

    subject = f"{subject_prefix}: {form_obj.name}"
    rows = "".join(
        f"<tr><th align='left' style='padding:6px 10px'>{k}</th><td style='padding:6px 10px'>{v}</td></tr>"
        for k, v in (process.ticket_data or {}).items()
    )
    html = f"""
      <h3>{subject_prefix}: {form_obj.name}</h3>
      <table border="1" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{rows}</table>
      <p>Process ID: {process.pk}</p>
    """
    plain = "\n".join(f"{k}: {v}" for k, v in (process.ticket_data or {}).items())

    msg = EmailMultiAlternatives(subject, plain, to=emails)
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=True)


class DynamicStartView(CreateProcessView):
    """
    Start step: shows only 'Risk Representative' (user) fields + the 'form' selector.
    """
    model = TicketProcess

    def get_form_class(self):
        selected_form_id = self.request.POST.get("form") or self.request.GET.get("form")

        class StartForm(forms.ModelForm):
            class Meta:
                model = TicketProcess
                fields = ["form"]

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                form_obj = None
                if selected_form_id:
                    try:
                        form_obj = FormModel.objects.get(id=selected_form_id)
                    except FormModel.DoesNotExist:
                        form_obj = None
                if form_obj:
                    # Only Risk Representative fields at start
                    add_fields_to_form(self, form_obj, role_code=FormField.ROLE_USER)

        return StartForm


class ApprovalView(UpdateProcessView):
    """
    Approval step for each role:
    - shows read-only summary of all values so far
    - shows only this role's fields to fill/edit
    - has Approve / Reject buttons in the template (no radio)
    """
    model = TicketProcess
    template_name = "viewflow/workflow/task.html"
    role = None  # set via .as_view(role="user"/"dev"/"ba"/"pm")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ticket_summary_html"] = build_ticket_summary_html(self.object)
        ctx["is_approval"] = True
        ctx["role"] = self.role or self.kwargs.get("role")

        # Labels for status chips
        ctx["status_row"] = {
            "Risk Representative": (self.object.user_decision or "-"),
            "Risk Champion":       (self.object.dev_decision  or "-"),
            "Risk Approver":       (self.object.ba_decision   or "-"),
            "CRO":                 (self.object.pm_decision   or "-"),
        }
        return ctx

    def get_form_class(self):
        process = self.get_object()
        role = self.role or self.kwargs.get("role")
        comment_field = f"{role}_comment"
        form_obj = process.form

        # Build dynamic form with only this role's fields + the comment field
        class _Form(ApprovalForm):
            class Meta(ApprovalForm.Meta):
                model = TicketProcess
                fields = [comment_field]

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                initial_map = {}
                if process.entry:
                    # Pre-fill with existing values if present
                    for v in process.entry.values.all():
                        initial_map[str(v.field_id)] = v.value_text or (v.value_file.name if v.value_file else "")
                add_fields_to_form(self, form_obj, role_code=role, initial_map=initial_map)

        return _Form

    def form_valid(self, form):
        process = form.instance
        role = self.role or self.kwargs.get("role")

        decision = self.request.POST.get("decision")
        if decision not in ("approved", "rejected"):
            form.add_error(None, "Please click Approve or Reject.")
            return self.form_invalid(form)

        if not process.entry:
            process.entry = FormEntry.objects.create(form=process.form, submitted_by=self.request.user)

        _update_entry_values_for_role(process.entry, process.form, form.cleaned_data, self.request.FILES, role)

        process.ticket_data = _snapshot_from_entry(process.entry)

        setattr(process, f"{role}_decision", decision)
        setattr(process, f"approved_by_{role}", self.request.user.get_username())
        process.save()

        return super().form_valid(form)