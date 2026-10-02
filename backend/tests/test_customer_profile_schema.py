import pytest
from pydantic import ValidationError

from app.portal_schemas import (
    CustomerProfileCreate,
    CustomerProfileUpdate,
)


VALID_PROFILE = {
    "full_name": "John Doe",
    "mobile_number": "9876543210",
    "address": "12 Main Street",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "pincode": "600001",
    "company_name": "FieldOps Customer",
}


def test_customer_profile_create_accepts_valid_payload():
    profile = CustomerProfileCreate(
        **VALID_PROFILE
    )

    assert profile.full_name == "John Doe"
    assert profile.mobile_number == "9876543210"
    assert profile.address == "12 Main Street"
    assert profile.city == "Chennai"
    assert profile.state == "Tamil Nadu"
    assert profile.pincode == "600001"
    assert profile.company_name == "FieldOps Customer"


def test_customer_profile_create_trims_full_name_and_mobile():
    profile = CustomerProfileCreate(
        **{
            **VALID_PROFILE,
            "full_name": "  John Doe  ",
            "mobile_number": " 9876543210 ",
        }
    )

    assert profile.full_name == "John Doe"
    assert profile.mobile_number == "9876543210"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "A1",
        "John-Doe",
        "John_Doe",
        "John@Doe",
    ],
)
def test_customer_profile_create_rejects_invalid_full_name(
    value,
):
    payload = {
        **VALID_PROFILE,
        "full_name": value,
    }

    with pytest.raises(ValidationError):
        CustomerProfileCreate(**payload)


@pytest.mark.parametrize(
    "value",
    [
        "12345",
        "123456789",
        "12345678901",
        "98765432A0",
        "987654-210",
    ],
)
def test_customer_profile_create_rejects_invalid_mobile(
    value,
):
    payload = {
        **VALID_PROFILE,
        "mobile_number": value,
    }

    with pytest.raises(ValidationError):
        CustomerProfileCreate(**payload)


@pytest.mark.parametrize(
    "value",
    [
        "60000",
        "6000011",
        "60000A",
        "ABCDEF",
    ],
)
def test_customer_profile_create_rejects_invalid_pincode(
    value,
):
    payload = {
        **VALID_PROFILE,
        "pincode": value,
    }

    with pytest.raises(ValidationError):
        CustomerProfileCreate(**payload)


def test_customer_profile_create_allows_optional_address_fields_to_be_absent():
    profile = CustomerProfileCreate(
        full_name="John Doe",
        mobile_number="9876543210",
    )

    assert profile.address is None
    assert profile.city is None
    assert profile.state is None
    assert profile.pincode is None
    assert profile.company_name is None


def test_customer_profile_create_rejects_client_supplied_scope_fields():
    payload = {
        **VALID_PROFILE,
        "user_id": "another-user",
        "tenant_id": "another-tenant",
    }

    with pytest.raises(ValidationError):
        CustomerProfileCreate(**payload)


def test_customer_profile_update_supports_partial_updates():
    profile = CustomerProfileUpdate(
        city="Coimbatore",
    )

    assert profile.city == "Coimbatore"
    assert profile.full_name is None
    assert profile.mobile_number is None
    assert profile.address is None


def test_customer_profile_update_validates_changed_fields():
    with pytest.raises(ValidationError):
        CustomerProfileUpdate(
            mobile_number="12345",
        )

    with pytest.raises(ValidationError):
        CustomerProfileUpdate(
            pincode="12AB56",
        )

    with pytest.raises(ValidationError):
        CustomerProfileUpdate(
            full_name="John@Doe",
        )


def test_customer_profile_update_rejects_unknown_scope_fields():
    with pytest.raises(ValidationError):
        CustomerProfileUpdate(
            tenant_id="another-tenant",
            city="Chennai",
        )