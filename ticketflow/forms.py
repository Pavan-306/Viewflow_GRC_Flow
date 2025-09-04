# ticketflow/forms.py
from django import forms
from django.core.validators import RegexValidator
from .models import Form as FormModel, FormField, TicketProcess
from .validators import validate_uploaded_file


def add_fields_to_form(
    django_form,
    form_obj: FormModel,
    role_code: str | None = None,
    role: str | None = None,
    initial_map: dict | None = None,
    exclude_labels: set[str] | None = None,   # <--- NEW
):
    """
    Add dynamic fields from FormField into the given Django form.

    - Pass either `role_code` or `role` (kept for backward compatibility).
    - If `exclude_labels` is provided, fields whose label is in that set are skipped.
    """
    if role_code is None:
        role_code = role

    if exclude_labels is None:
        exclude_labels = set()

    qs = form_obj.fields.all()
    if role_code:
        qs = qs.filter(role=role_code)

    for ff in qs:
        # Skip hidden fields or fields excluded by label
        if ff.hidden or (ff.label in exclude_labels):
            continue

        key = str(ff.id)
        init = (initial_map or {}).get(key, ff.default_value or None)

        # Build validators list from regex if provided
        base_validators = []
        if ff.regex:
            base_validators.append(RegexValidator(regex=ff.regex, message="Invalid format"))

        # Common kwargs used by most fields
        common_kwargs = dict(
            label=ff.label,
            required=ff.required,
            help_text=ff.help_text,
            initial=init,
            validators=base_validators,
        )

        # ---- Field types ----
        if ff.field_type == FormField.TEXT:
            django_form.fields[key] = forms.CharField(
                max_length=ff.max_length or 255,
                widget=forms.TextInput(attrs={"placeholder": ff.placeholder or ""}),
                **common_kwargs,
            )

        elif ff.field_type == FormField.TEXTAREA:
            django_form.fields[key] = forms.CharField(
                widget=forms.Textarea(attrs={"placeholder": ff.placeholder or "", "rows": 4}),
                **common_kwargs,
            )

        elif ff.field_type == FormField.SELECT:
            choices = [(c.strip(), c.strip()) for c in ff.choices.split(",") if c.strip()]
            django_form.fields[key] = forms.ChoiceField(
                choices=choices,
                **common_kwargs,
            )

        elif ff.field_type == FormField.FILE:
            # IMPORTANT: don’t pass validators twice; merge here explicitly
            file_validators = list(base_validators) + [validate_uploaded_file]
            file_kwargs = dict(common_kwargs)
            file_kwargs["validators"] = file_validators
            django_form.fields[key] = forms.FileField(**file_kwargs)

        elif ff.field_type == FormField.EMAIL:
            django_form.fields[key] = forms.EmailField(
                widget=forms.EmailInput(attrs={"placeholder": ff.placeholder or ""}),
                **common_kwargs,
            )

        elif ff.field_type == FormField.DATE:
            django_form.fields[key] = forms.DateField(
                input_formats=["%Y-%m-%d"],
                widget=forms.DateInput(attrs={"placeholder": "YYYY-MM-DD"}),
                **common_kwargs,
            )

        elif ff.field_type == FormField.NUMBER:
            django_form.fields[key] = forms.IntegerField(
                min_value=ff.min_value,
                max_value=ff.max_value,
                **common_kwargs,
            )

        elif ff.field_type == FormField.CHECKBOX:
            # BooleanField ignores validators; use required+initial semantics
            django_form.fields[key] = forms.BooleanField(
                required=ff.required,
                initial=(init in ("True", "true", True, "1", 1)),
                label=ff.label,
                help_text=ff.help_text,
            )

        elif ff.field_type == FormField.RADIO:
            choices = [(c.strip(), c.strip()) for c in ff.choices.split(",") if c.strip()]
            django_form.fields[key] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect,
                **common_kwargs,
            )

        # Readonly handling: disable field in the form (still rendered)
        if key in django_form.fields and ff.readonly:
            django_form.fields[key].widget.attrs["readonly"] = True
            django_form.fields[key].widget.attrs["disabled"] = True


class ApprovalForm(forms.ModelForm):
    class Meta:
        model = TicketProcess
        fields = []  # comment field is injected in the view per-role