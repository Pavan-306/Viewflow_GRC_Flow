from viewflow import this
from viewflow.workflow import flow, lock

from .models import TicketProcess, FormEntry, FormField
from .views import (
    DynamicStartView,
    ApprovalView,
    _update_entry_values_for_role,
    _snapshot_from_entry,
    send_submission_emails,
)


class TicketFlow(flow.Flow):
    """
    RISK Management
    """
    # 👇 This controls the big purple header and the card title
    label = "RISK Management"

    process_class = TicketProcess
    lock_impl = lock.select_for_update_lock

    # ---- 1) Start ----
    start = (
        flow.Start(DynamicStartView.as_view())
        .Annotation(title="Start Request")
        .Permission(auto_create=True)
        .Next(this.save_user_fields)
    )

    save_user_fields = (
        flow.Function(lambda activation: _save_user_start_data(activation))
        .Annotation(title="Save Risk Representative Fields")
        .Next(this.user_approval)
    )

    # ---- 2) Risk Representative ----
    user_approval = (
        flow.View(ApprovalView.as_view(role="user"))
        .Annotation(title="Risk Representative Approval")
        .Permission(auto_create=True)
        .Next(this.user_decision)
    )
    user_decision = (
        flow.If(lambda activation: activation.process.user_decision == "approved")
        .Then(this.dev_approval)
        .Else(this.start)
    )

    # ---- 3) Risk Champion ----
    dev_approval = (
        flow.View(ApprovalView.as_view(role="dev"))
        .Annotation(title="Risk Champion Approval")
        .Permission(auto_create=True)
        .Next(this.dev_decision)
    )
    dev_decision = (
        flow.If(lambda activation: activation.process.dev_decision == "approved")
        .Then(this.ba_approval)
        .Else(this.user_approval)
    )

    # ---- 4) Risk Approver ----
    ba_approval = (
        flow.View(ApprovalView.as_view(role="ba"))
        .Annotation(title="Risk Approver Approval")
        .Permission(auto_create=True)
        .Next(this.ba_decision)
    )
    ba_decision = (
        flow.If(lambda activation: activation.process.ba_decision == "approved")
        .Then(this.pm_approval)
        .Else(this.dev_approval)
    )

    # ---- 5) CRO ----
    pm_approval = (
        flow.View(ApprovalView.as_view(role="pm"))
        .Annotation(title="CRO Approval")
        .Permission(auto_create=True)
        .Next(this.pm_decision)
    )
    pm_decision = (
        flow.If(lambda activation: activation.process.pm_decision == "approved")
        .Then(this.end)
        .Else(this.ba_approval)
    )

    end = flow.End()


def _save_user_start_data(activation):
    """Persist requester fields and refresh snapshot."""
    process = activation.process

    if not process.entry:
        submitted_by = getattr(getattr(activation, "request", None), "user", None)
        process.entry = FormEntry.objects.create(
            form=process.form,
            submitted_by=submitted_by,
        )

    if hasattr(activation, "form") and activation.form.is_valid():
        files = getattr(getattr(activation, "request", None), "FILES", None)
        _update_entry_values_for_role(
            process.entry,
            process.form,
            activation.form.cleaned_data,
            files,
            role=FormField.ROLE_USER,
        )

    process.ticket_data = _snapshot_from_entry(process.entry)
    process.save()

    try:
        send_submission_emails(process, subject_prefix="New submission")
    except Exception:
        pass