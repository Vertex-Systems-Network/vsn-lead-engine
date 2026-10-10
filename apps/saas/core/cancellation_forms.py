"""Short-lived, state-bound confirmations for pre-dispatch cancel and submit."""

from django import forms
from django.core import signing

TOKEN_SALT = "saas.pending-cancellation.v1"
SUBMIT_SALT = "saas.job-submission.v1"


def cancellation_token(user, workspace_id, job, salt=TOKEN_SALT):
    return signing.dumps(
        {
            "user": str(user.pk),
            "workspace": str(workspace_id),
            "job": str(job.pk),
            "revision": job.revision,
        },
        salt=salt,
    )


def submission_token(user, workspace_id, job):
    return cancellation_token(user, workspace_id, job, salt=SUBMIT_SALT)


class PendingCancellationForm(forms.Form):
    salt = TOKEN_SALT
    confirmation = forms.CharField(max_length=1024, widget=forms.HiddenInput)

    def __init__(self, *args, user, workspace_id, job_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user, self.workspace_id, self.job_id = user, workspace_id, job_id
        self.expected_revision = None

    def clean_confirmation(self):
        value = self.cleaned_data["confirmation"]
        try:
            token = signing.loads(value, salt=self.salt, max_age=600)
            if not isinstance(token, dict) or set(token) != {
                "user",
                "workspace",
                "job",
                "revision",
            }:
                raise ValueError
            if (token["user"], token["workspace"], token["job"]) != (
                str(self.user.pk),
                str(self.workspace_id),
                str(self.job_id),
            ):
                raise ValueError
            revision = token["revision"]
            if type(revision) is not int or not 0 <= revision <= 2147483646:
                raise ValueError
            self.expected_revision = revision
        except (signing.BadSignature, ValueError, TypeError):
            raise forms.ValidationError(
                "Invalid or expired confirmation. Review the job again."
            ) from None
        return value


class JobSubmissionForm(PendingCancellationForm):
    """Same revision-bound confirmation, under a separate salt so tokens never cross."""

    salt = SUBMIT_SALT
