from uuid import uuid4

import pytest

from vsn_lead_engine.saas.contracts import Entitlement, SearchSpec
from vsn_lead_engine.saas.source_policy import (
    SearchAuthorizationError,
    SourcePolicy,
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
            _search(workspace_id, **change),
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
