# ticketflow/models.py
from django.conf import settings
from django.db import models
from viewflow.workflow.models import Process
from viewflow import jsonstore


class Form(models.Model):
    name = models.CharField(max_length=200)
    notify_emails = models.TextField(
        blank=True,
        help_text="Comma-separated emails to notify when this form is submitted",
    )
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class FormField(models.Model):
    # Field types
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    FILE = "file"
    EMAIL = "email"
    DATE = "date"
    NUMBER = "number"
    CHECKBOX = "checkbox"
    RADIO = "radio"

    FIELD_TYPES = [
        (TEXT, "Text"),
        (TEXTAREA, "Long text"),
        (SELECT, "Drop-down"),
        (FILE, "File upload"),
        (EMAIL, "Email"),
        (DATE, "Date (YYYY-MM-DD)"),
        (NUMBER, "Number"),
        (CHECKBOX, "Checkbox"),
        (RADIO, "Radio"),
    ]

    # Role keys (internal, do not change)
    ROLE_USER = "user"
    ROLE_DEV = "dev"
    ROLE_BA = "ba"
    ROLE_PM = "pm"

    # Visible labels (your requested names)
    ROLE_CHOICES = [
        (ROLE_USER, "Risk Representative"),
        (ROLE_DEV, "Risk Champion"),
        (ROLE_BA, "Risk Approver"),
        (ROLE_PM, "CRO"),
    ]

    form = models.ForeignKey(Form, related_name="fields", on_delete=models.CASCADE)

    label = models.CharField(max_length=200)
    field_type = models.CharField(
        max_length=20, choices=FIELD_TYPES, default=TEXT
    )
    required = models.BooleanField(default=False)
    help_text = models.CharField(max_length=300, blank=True)
    choices = models.TextField(
        blank=True,
        help_text='For "Drop-down/Radio": comma-separated options',
    )
    max_length = models.PositiveIntegerField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    # Which stage fills this field
    role = models.CharField(
        max_length=10, choices=ROLE_CHOICES, default=ROLE_USER
    )

    placeholder = models.CharField(
        max_length=200, blank=True, help_text="Placeholder for inputs", default=""
    )
    default_value = models.CharField(
        max_length=200, blank=True, help_text="Default text/value", default=""
    )
    min_value = models.IntegerField(null=True, blank=True)
    max_value = models.IntegerField(null=True, blank=True)
    regex = models.CharField(
        max_length=200, blank=True, help_text="Optional regex validation", default=""
    )
    readonly = models.BooleanField(
        default=False, help_text="Show as read-only"
    )
    hidden = models.BooleanField(
        default=False, help_text="Hide field in forms (but store value if present)"
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.form.name} / {self.label}"


class FormEntry(models.Model):
    form = models.ForeignKey(
        Form, related_name="entries", on_delete=models.CASCADE
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Entry #{self.id} / {self.form.name}"


class FormEntryValue(models.Model):
    entry = models.ForeignKey(
        FormEntry, related_name="values", on_delete=models.CASCADE
    )
    field = models.ForeignKey(FormField, on_delete=models.CASCADE)
    value_text = models.TextField(blank=True)
    value_file = models.FileField(
        upload_to="form_uploads/", null=True, blank=True
    )

    def __str__(self):
        val = self.value_text or (
            self.value_file.name if self.value_file else ""
        )
        return f"{self.field.label} = {val}"


class TicketProcess(Process):
    form = models.ForeignKey(Form, on_delete=models.PROTECT)
    # One unified entry over the whole flow
    entry = models.OneToOneField(
        FormEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_process",
    )

    # Snapshot for quick display/emails
    ticket_data = jsonstore.JSONField(default=dict)

    # Decisions/comments per stage
    user_decision = jsonstore.CharField(max_length=10, blank=True)
    dev_decision = jsonstore.CharField(max_length=10, blank=True)
    ba_decision = jsonstore.CharField(max_length=10, blank=True)
    pm_decision = jsonstore.CharField(max_length=10, blank=True)

    approved_by_user = jsonstore.CharField(max_length=100, blank=True)
    approved_by_dev = jsonstore.CharField(max_length=100, blank=True)
    approved_by_ba = jsonstore.CharField(max_length=100, blank=True)
    approved_by_pm = jsonstore.CharField(max_length=100, blank=True)

    user_comment = jsonstore.TextField(blank=True)
    dev_comment = jsonstore.TextField(blank=True)
    ba_comment = jsonstore.TextField(blank=True)
    pm_comment = jsonstore.TextField(blank=True)

    def __str__(self):
        return f"TicketProcess for {self.form.name}"