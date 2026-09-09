import pytest

from app.models.profile import Profile
from tests.test_academic_info import SUBFIELD_ID, TARGET_ID, payload
from tests.test_academic_info import (
    api as api,  # noqa: PLC0414 -- re-export the shared pytest fixture
)


def preferences_payload(degree="MASTER", **changes):
    data = {
        "desired_degree_level": degree,
        "target_field_of_study": "Artificial Intelligence",
        "target_field_of_study_openalex_id": TARGET_ID,
        "detailed_specialization": "Distributed Systems" if degree == "PHD" else None,
        "funding_type": "FULL",
        "preferred_countries": ["DE", "PS"],
        "open_to_all_countries": False,
    }
    return data | changes


@pytest.mark.parametrize("degree", ["BACHELOR", "MASTER", "PHD", "DIPLOMA", "OTHER"])
def test_preferences_save_and_aggregate_match_with_shared_openalex_taxonomy(
    api, degree
):
    client, sessions, user_id = api
    data = preferences_payload(degree)
    response = client.put("/profile/preferences", json=data)
    assert response.status_code == 200, response.text
    assert response.json() == data | {"is_profile_completed": True}
    assert client.get("/profile/preferences").json() == response.json()
    assert client.get("/profile").json()["preferences"] == response.json()
    assert client.get("/profile").json()["academic_info"] is None
    with sessions() as db:
        profile = db.get(Profile, client.get("/profile").json()["id"])
        assert profile.user_id == user_id
        assert profile.target_field_of_study == data["target_field_of_study"]
        assert profile.detailed_specialization == data["detailed_specialization"]


def test_existing_academic_target_is_exposed_only_in_preferences_and_archive_untouched(
    api,
):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        profile.target_field_of_study = "Existing target"
        profile.target_field_of_study_openalex_id = TARGET_ID
        profile.legacy_preferred_fields_of_study = ["Different field", "Another field"]
        db.commit()
    assert (
        client.get("/profile/preferences").json()["target_field_of_study"]
        == "Existing target"
    )
    assert client.put("/profile/academic-info", json=payload()).status_code == 200
    full = client.get("/profile").json()
    assert "target_field_of_study" not in full["academic_info"]
    assert "target_field_of_study_openalex_id" not in full["academic_info"]
    assert "preferred_fields_of_study" not in full["preferences"]
    assert full["academic_info"]["field_of_study"] == "Software Engineering"
    assert full["academic_info"]["field_of_study_openalex_id"] == SUBFIELD_ID
    assert full["preferences"]["target_field_of_study"] == "Existing target"
    client.put("/profile/preferences", json=preferences_payload())
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        assert profile.legacy_preferred_fields_of_study == [
            "Different field",
            "Another field",
        ]
        assert profile.field_of_study == "Software Engineering"


def test_multiple_legacy_preferences_are_not_arbitrarily_selected(api):
    client, sessions, user_id = api
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        profile.legacy_preferred_fields_of_study = ["Computer Science", "Medicine"]
        db.commit()
    assert client.get("/profile/preferences").json()["target_field_of_study"] is None
    assert client.get("/profile").json()["profile_completion_percentage"] == 0


@pytest.mark.parametrize("degree", ["BACHELOR", "MASTER", "DIPLOMA", "OTHER"])
def test_changing_away_from_phd_clears_specialization_even_when_omitted(api, degree):
    client, sessions, user_id = api
    assert (
        client.put("/profile/preferences", json=preferences_payload("PHD")).status_code
        == 200
    )
    changed = client.put("/profile/preferences", json={"desired_degree_level": degree})
    assert changed.status_code == 200
    assert changed.json()["detailed_specialization"] is None
    assert changed.json()["target_field_of_study"] == "Artificial Intelligence"
    with sessions() as db:
        assert (
            db.query(Profile).filter_by(user_id=user_id).one().detailed_specialization
            is None
        )
    assert (
        client.put(
            "/profile/preferences", json={"desired_degree_level": "PHD"}
        ).status_code
        == 422
    )


def test_non_phd_specialization_normalizes_to_null_and_partial_phd_update_preserves_it(
    api,
):
    client = api[0]
    assert (
        client.put("/profile/preferences", json=preferences_payload("PHD")).status_code
        == 200
    )
    funding_only = client.put("/profile/preferences", json={"funding_type": "PARTIAL"})
    assert funding_only.status_code == 200
    assert funding_only.json()["detailed_specialization"] == "Distributed Systems"
    changed = client.put(
        "/profile/preferences",
        json={
            "desired_degree_level": "MASTER",
            "detailed_specialization": "Should be cleared",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["detailed_specialization"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"desired_degree_level": "UNKNOWN"},
        {"funding_type": "UNKNOWN"},
        {"target_field_of_study": "   "},
        {"target_field_of_study": 42},
        {"target_field_of_study": "x" * 256},
        {"target_field_of_study_openalex_id": "https://example.com/subfields/1706"},
        {"target_field_of_study_openalex_id": "https://openalex.org/T1234"},
        {"target_field_of_study": None, "target_field_of_study_openalex_id": TARGET_ID},
        {"desired_degree_level": "PHD", "detailed_specialization": None},
        {"desired_degree_level": "PHD", "detailed_specialization": " "},
        {"detailed_specialization": "x" * 256},
        {"preferred_countries": ["Germany"]},
        {"preferred_countries": ["D1"]},
        {"preferred_countries": [42]},
        {"open_to_all_countries": "invalid"},
        {"preferred_fields_of_study": ["Computer Science"]},
        {"unknown_field": "value"},
    ],
)
def test_invalid_updates_are_422_and_do_not_change_stored_preferences(api, changes):
    client = api[0]
    before = client.put("/profile/preferences", json=preferences_payload()).json()
    response = client.put("/profile/preferences", json=changes)
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)
    assert response.json()["detail"][0]["loc"][0] == "body"
    assert client.get("/profile/preferences").json() == before


def test_required_phd_specialization_is_validated_against_merged_degree(api):
    client = api[0]
    assert (
        client.put("/profile/preferences", json=preferences_payload("PHD")).status_code
        == 200
    )
    assert (
        client.put(
            "/profile/preferences", json={"detailed_specialization": None}
        ).status_code
        == 422
    )
    assert (
        client.get("/profile/preferences").json()["detailed_specialization"]
        == "Distributed Systems"
    )


def test_countries_normalize_and_open_to_all_clears_persisted_list(api):
    client, sessions, user_id = api
    response = client.put(
        "/profile/preferences", json={"preferred_countries": [" de ", "ps"]}
    )
    assert response.status_code == 200
    assert response.json()["preferred_countries"] == ["DE", "PS"]
    response = client.put("/profile/preferences", json={"open_to_all_countries": True})
    assert response.json()["preferred_countries"] == []
    response = client.put("/profile/preferences", json={"preferred_countries": ["FR"]})
    assert response.json()["preferred_countries"] == []
    with sessions() as db:
        profile = db.query(Profile).filter_by(user_id=user_id).one()
        assert profile.open_to_all_countries is True
        assert profile.preferred_countries == []
    response = client.put(
        "/profile/preferences",
        json={"open_to_all_countries": False, "preferred_countries": ["FR"]},
    )
    assert response.json()["preferred_countries"] == ["FR"]


def test_target_changes_clear_stale_id_and_explicit_null_clears_target(api):
    client = api[0]
    client.put("/profile/preferences", json=preferences_payload())
    response = client.put(
        "/profile/preferences", json={"target_field_of_study": "  Medicine  "}
    )
    assert response.status_code == 200
    assert response.json()["target_field_of_study"] == "Medicine"
    assert response.json()["target_field_of_study_openalex_id"] is None
    response = client.put("/profile/preferences", json={"target_field_of_study": None})
    assert response.json()["target_field_of_study"] is None
    assert response.json()["target_field_of_study_openalex_id"] is None
    assert response.json()["is_profile_completed"] is False


def test_existing_null_no_change_and_empty_update_semantics(api):
    client = api[0]
    before = client.put("/profile/preferences", json=preferences_payload()).json()
    assert client.put("/profile/preferences", json={}).json() == before
    assert (
        client.put(
            "/profile/preferences",
            json={
                "desired_degree_level": None,
                "funding_type": None,
                "preferred_countries": None,
                "open_to_all_countries": None,
            },
        ).json()
        == before
    )


def test_missing_profile_and_legacy_phd_remain_readable(api):
    client, sessions, user_id = api
    with sessions() as db:
        db.delete(db.query(Profile).filter_by(user_id=user_id).one())
        db.commit()
    response = client.get("/profile/preferences")
    assert response.status_code == 200
    assert response.json()["target_field_of_study"] is None
    assert response.json()["detailed_specialization"] is None
    assert (
        client.put("/profile/preferences", json=preferences_payload()).status_code
        == 200
    )
    with sessions() as db:
        db.query(Profile).filter_by(user_id=user_id).one().desired_degree_level = "PHD"
        db.commit()
    response = client.get("/profile/preferences")
    assert response.status_code == 200
    assert response.json()["detailed_specialization"] is None
    assert response.json()["is_profile_completed"] is False
    assert client.get("/profile").status_code == 200


def test_preferences_target_only_awards_its_existing_eight_points(api):
    client = api[0]
    client.put("/profile/academic-info", json=payload())
    assert client.get("/profile").json()["profile_completion_percentage"] == 22
    client.put(
        "/profile/preferences",
        json={"target_field_of_study": "Artificial Intelligence"},
    )
    assert client.get("/profile").json()["profile_completion_percentage"] == 30
    client.put("/profile/preferences", json={"target_field_of_study": None})
    assert client.get("/profile").json()["profile_completion_percentage"] == 22


def test_preferences_authentication(api):
    client = api[0]
    del client.headers["Authorization"]
    assert client.get("/profile/preferences").status_code == 401
    assert (
        client.put("/profile/preferences", json=preferences_payload()).status_code
        == 401
    )


def test_preferences_openapi_contract(api):
    models = api[0].get("/openapi.json").json()["components"]["schemas"]
    expected = set(preferences_payload())
    assert set(models["PreferencesUpdate"]["properties"]) == expected
    assert set(models["PreferencesResponse"]["properties"]) == expected | {
        "is_profile_completed"
    }
    assert models["PreferencesUpdate"]["additionalProperties"] is False
    for name in ("AcademicInfoUpdate", "AcademicInfoResponse"):
        assert "target_field_of_study" not in models[name]["properties"]
        assert "target_field_of_study_openalex_id" not in models[name]["properties"]
        assert "field_of_study" in models[name]["properties"]
