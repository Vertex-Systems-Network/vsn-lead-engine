from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from rest_framework import serializers
from .models import Job, Membership, Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["id", "name", "timezone", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Choose a valid IANA timezone.")
        return value


class SearchSerializer(serializers.Serializer):
    countries = serializers.ListField(child=serializers.ChoiceField(choices=["US", "CA"]), min_length=1, max_length=2)
    categories = serializers.ListField(child=serializers.CharField(max_length=120), min_length=1, max_length=12)
    statuses = serializers.ListField(child=serializers.ChoiceField(choices=["active", "closed", "opening_soon"]), default=list, max_length=3)
    required_fields = serializers.ListField(child=serializers.ChoiceField(choices=["phone", "name", "website", "address"]), default=list, max_length=4)
    source_codes = serializers.ListField(child=serializers.CharField(max_length=64), default=list, max_length=12)
    result_limit = serializers.IntegerField(min_value=1, max_value=1000, default=100)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"unknown_fields": "Unknown search fields are not accepted."})
        return super().to_internal_value(data)

    def validate(self, attrs):
        for key in ("countries", "categories", "statuses", "required_fields", "source_codes"):
            attrs[key] = sorted(set(attrs[key]))
        if "phone" not in attrs["required_fields"]:
            attrs["required_fields"].append("phone")
            attrs["required_fields"].sort()
        return attrs


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ["id", "workspace_id", "search", "status", "revision", "result_count", "created_at", "updated_at"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ["user_id", "role"]
        read_only_fields = fields


class MembershipRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["owner", "admin", "member", "viewer"])

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) != {"role"}:
            raise serializers.ValidationError({"role": "Supply only the new role."})
        return super().to_internal_value(data)
