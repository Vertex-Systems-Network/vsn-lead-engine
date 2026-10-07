from uuid import uuid4

import pytest

from vsn_lead_engine.saas.contracts import Entitlement, ExportSpec, SearchSpec
from vsn_lead_engine.saas.source_policy import (
    SearchAuthorizationError,
    SourcePolicy,
    authorize_export,
    authorize_search,
)


def _search(workspace_id, **overrides):
    values = {
        "workspace_id": workspace_id,
        "countries": ("US",),
        "categories": ("spa",),
        "required_fields": ("phone",),
        "source_codes": ("overture-free",),
        "result_limit": 25,
    }
    values.update(overrides)
    return SearchSpec(**values)


def test_authorize_search_accepts_matching_policy():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
        lead_limit=100,
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US", "CA"}),
        categories=frozenset({"spa"}),
        allowed_required_fields=frozenset({"phone"}),
    )

    authorize_search(_search(workspace_id), entitlement, {policy.code: policy})


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"workspace_id": uuid4()}, "workspace"),
        ({"source_codes": ("unknown",)}, "included"),
        ({"countries": ("GB",)}, "countries"),
        ({"result_limit": 101}, "limit"),
    ],
)
def test_authorize_search_rejects_out_of_boundary(change, expected):
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
        lead_limit=100,
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        categories=frozenset({"spa"}),
        allowed_required_fields=frozenset({"phone"}),
    )

    with pytest.raises(SearchAuthorizationError, match=expected):
        authorize_search(
            _search(**({"workspace_id": workspace_id} | change)),
            entitlement,
            {policy.code: policy},
        )


def test_authorize_search_rejects_disabled_source():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        enabled=False,
    )

    with pytest.raises(SearchAuthorizationError, match="unavailable"):
        authorize_search(_search(workspace_id), entitlement, {policy.code: policy})



def test_authorize_search_rejects_misidentified_policy_entry():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
    )
    mislabeled_policy = SourcePolicy(
        code="different-source",
        countries=frozenset({"US"}),
        categories=frozenset({"spa"}),
        allowed_required_fields=frozenset({"phone"}),
    )

    with pytest.raises(SearchAuthorizationError, match="identity mismatch"):
        authorize_search(
            _search(workspace_id),
            entitlement,
            {"overture-free": mislabeled_policy},
        )



def test_search_is_allowed_when_source_policy_forbids_export():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        categories=frozenset({"spa"}),
        allowed_required_fields=frozenset({"phone"}),
        export_allowed=False,
    )

    authorize_search(_search(workspace_id), entitlement, {policy.code: policy})


def test_authorize_export_accepts_only_plan_and_policy_allowed_fields():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
        export_enabled=True,
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        allowed_required_fields=frozenset({"phone", "website"}),
        export_allowed=True,
    )

    authorize_export(
        ExportSpec(workspace_id, ("overture-free",), ("phone",)),
        entitlement,
        {policy.code: policy},
    )


def test_authorize_export_rejects_source_policy_export_denial():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        allowed_required_fields=frozenset({"phone"}),
        export_allowed=False,
    )

    with pytest.raises(SearchAuthorizationError, match="does not permit export"):
        authorize_export(
            ExportSpec(workspace_id, ("overture-free",), ("phone",)),
            entitlement,
            {policy.code: policy},
        )


def test_authorize_export_rejects_fields_not_allowed_by_source():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        allowed_required_fields=frozenset({"phone"}),
        export_allowed=True,
    )

    with pytest.raises(SearchAuthorizationError, match="exported fields"):
        authorize_export(
            ExportSpec(workspace_id, ("overture-free",), ("email",)),
            entitlement,
            {policy.code: policy},
        )


def test_authorize_export_rejects_inactive_or_cross_tenant_entitlement():
    workspace_id = uuid4()
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        allowed_required_fields=frozenset({"phone"}),
    )
    export = ExportSpec(workspace_id, ("overture-free",), ("phone",))

    with pytest.raises(SearchAuthorizationError, match="workspace"):
        authorize_export(
            export,
            Entitlement(workspace_id=uuid4(), plan_code="free"),
            {policy.code: policy},
        )
    with pytest.raises(SearchAuthorizationError, match="inactive"):
        authorize_export(
            export,
            Entitlement(workspace_id=workspace_id, plan_code="free", active=False),
            {policy.code: policy},
        )


def test_authorize_export_rejects_plan_export_disabled():
    workspace_id = uuid4()
    entitlement = Entitlement(
        workspace_id=workspace_id,
        plan_code="free",
        source_codes=frozenset({"overture-free"}),
        export_enabled=False,
    )
    policy = SourcePolicy(
        code="overture-free",
        countries=frozenset({"US"}),
        allowed_required_fields=frozenset({"phone"}),
    )

    with pytest.raises(SearchAuthorizationError, match="export is disabled"):
        authorize_export(
            ExportSpec(workspace_id, ("overture-free",), ("phone",)),
            entitlement,
            {policy.code: policy},
        )
