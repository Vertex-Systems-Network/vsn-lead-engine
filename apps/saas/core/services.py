import hashlib
import json
import re
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from .models import Job, Membership, MembershipAudit, Workspace


class IdempotencyConflict(APIException):
    status_code = 409
    default_detail = "Idempotency key was used for a different request."
    default_code = "idempotency_conflict"


def membership_for(user, workspace_id, *, lock=False):
    query = Membership.objects.filter(user=user, workspace_id=workspace_id)
    if lock:
        query = query.select_for_update()
    membership = query.first()
    if membership is None:
        raise Http404("Workspace resource not found.")
    return membership


@transaction.atomic
def create_workspace(user, data):
    workspace = Workspace.objects.create(**data)
    Membership.objects.create(workspace=workspace, user=user, role="owner")
    return workspace


@transaction.atomic
def create_draft(user, workspace_id, search, key):
    # Serialize creates within a workspace; membership is re-resolved and locked
    # in the same transaction. Revocation cannot race this write.
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    membership = membership_for(user, workspace_id, lock=True)
    if membership.role not in {"owner", "admin", "member"}:
        raise PermissionDenied("This role cannot create jobs.")
    if not key or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise ValidationError({"idempotency_key": "Use 1–128 letters, digits, dots, underscores, colons or hyphens."})
    request_hash = hashlib.sha256(json.dumps(search, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    previous = Job.objects.filter(workspace_id=workspace_id, idempotency_key=key).first()
    if previous:
        if previous.request_hash != request_hash:
            raise IdempotencyConflict()
        return previous, False
    job = Job.objects.create(workspace_id=workspace_id, created_by=user, search=search,
                             idempotency_key=key, request_hash=request_hash)
    return job, True


@transaction.atomic
def change_membership(user, workspace_id, target_user_id, *, role=None, remove=False):
    """Serialized owner-safe mutation. No client role or user lookup is trusted."""
    membership_for(user, workspace_id)
    Workspace.objects.select_for_update().get(pk=workspace_id)
    actor = membership_for(user, workspace_id, lock=True)
    if actor.role not in {"owner", "admin"}:
        raise PermissionDenied("This role cannot manage members.")
    target = membership_for(target_user_id, workspace_id, lock=True)
    if role is not None and role not in {"owner", "admin", "member", "viewer"}:
        raise ValidationError({"role": "Unsupported membership role."})
    if actor.role != "owner" and (target.role == "owner" or role == "owner"):
        raise PermissionDenied("Only an owner can change workspace ownership.")
    if target.role == "owner" and (remove or role != "owner"):
        if Membership.objects.filter(workspace_id=workspace_id, role="owner").count() <= 1:
            raise ValidationError({"role": "The workspace must retain at least one owner."})
    if not remove and role == target.role:
        return target
    previous = target.role
    MembershipAudit.objects.create(workspace_id=workspace_id, actor=user,
                                   target_user_id=target.user_id,
                                   action="removed" if remove else "role_changed",
                                   previous_role=previous, new_role="" if remove else role)
    if remove:
        target.delete()
        return None
    target.role = role
    target.save(update_fields=["role"])
    return target
