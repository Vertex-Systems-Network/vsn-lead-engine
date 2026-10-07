from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Job, Membership, Workspace
from .serializers import (
    JobSerializer,
    MembershipRoleSerializer,
    MembershipSerializer,
    SearchSerializer,
    WorkspaceSerializer,
)
from .services import change_membership, create_draft, create_workspace, membership_for


def health(request):
    return JsonResponse({"status": "ok", "service": "vsn-lead-saas", "provider_dispatch": False})


@login_required
def overview(request):
    workspaces = Workspace.objects.filter(membership__user=request.user).order_by("name", "id")
    return render(request, "core/overview.html", {"workspaces": workspaces})


class WorkspaceList(generics.ListCreateAPIView):
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return Workspace.objects.filter(membership__user=self.request.user).order_by("name", "id")

    def perform_create(self, serializer):
        serializer.instance = create_workspace(self.request.user, serializer.validated_data)


class JobList(APIView):
    def get(self, request, workspace_id):
        membership_for(request.user, workspace_id)
        # Bounded cursor continuation; filter tenant before applying the cursor.
        query = Job.objects.filter(workspace_id=workspace_id).order_by("id")
        after = request.query_params.get("after")
        if after:
            from uuid import UUID

            from rest_framework.exceptions import ValidationError

            try:
                query = query.filter(id__gt=UUID(after))
            except ValueError:
                raise ValidationError({"after": "Invalid continuation cursor."}) from None
        rows = list(query[:26])
        return Response(
            {
                "results": JobSerializer(rows[:25], many=True).data,
                "next": str(rows[24].id) if len(rows) > 25 else None,
            }
        )

    def post(self, request, workspace_id):
        membership_for(request.user, workspace_id)
        serializer = SearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job, created = create_draft(
            request.user,
            workspace_id,
            serializer.validated_data,
            request.headers.get("Idempotency-Key"),
        )
        return Response(
            JobSerializer(job).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class JobDetail(APIView):
    def get(self, request, workspace_id, job_id):
        membership_for(request.user, workspace_id)
        job = get_object_or_404(Job, workspace_id=workspace_id, id=job_id)
        return Response(JobSerializer(job).data)


class MemberList(generics.ListAPIView):
    serializer_class = MembershipSerializer

    def get_queryset(self):
        from rest_framework.exceptions import PermissionDenied

        membership = membership_for(self.request.user, self.kwargs["workspace_id"])
        if membership.role not in {"owner", "admin"}:
            raise PermissionDenied("This role cannot manage members.")
        return Membership.objects.filter(workspace_id=self.kwargs["workspace_id"]).order_by(
            "user_id"
        )


class MemberDetail(APIView):
    def patch(self, request, workspace_id, user_id):
        membership_for(request.user, workspace_id)
        serializer = MembershipRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = change_membership(
            request.user, workspace_id, user_id, role=serializer.validated_data["role"]
        )
        return Response(MembershipSerializer(member).data)

    def delete(self, request, workspace_id, user_id):
        change_membership(request.user, workspace_id, user_id, remove=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
