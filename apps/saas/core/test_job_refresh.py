from django.test import TestCase

from .jobs import enqueue_job
from .models import Job
from .test_jobs import fixture


class JobRefreshTests(TestCase):
    def test_detail_refreshes_only_while_in_progress(self):
        user, workspace, job = fixture()
        self.client.force_login(user)
        url = f"/workspaces/{workspace.id}/jobs/{job.id}/"
        self.assertNotContains(self.client.get(url), 'http-equiv="refresh"')
        enqueue_job(user, workspace.id, job.id, 0)
        self.assertContains(self.client.get(url), 'http-equiv="refresh"')
        Job.objects.filter(pk=job.pk).update(status="running")
        self.assertContains(self.client.get(url), "refreshes every 15 seconds")
        Job.objects.filter(pk=job.pk).update(status="completed")
        self.assertNotContains(self.client.get(url), 'http-equiv="refresh"')
