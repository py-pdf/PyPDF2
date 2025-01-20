"""Test the pypdf.constants module."""
import re
from typing import Callable

import pytest

from pypdf.constants import PDF_KEYS, GraphicsStateParameters, UserAccessPermissions


def test_slash_prefix():
    """
    Naming conventions of PDF_KEYS (constant names) are followed.

    This test function validates if PDF key names follow the required pattern:
    - Starts with a slash "/"
    - Followed by an uppercase letter
    - Contains alphanumeric characters (letters and digits)
    - The attribute name should be a case-insensitive match, with underscores removed
    """
    pattern = re.compile(r"^\/[A-Z]+[a-zA-Z0-9]*$")
    for cls in PDF_KEYS:
        for attr in dir(cls):
            # Skip magic methods
            if attr.startswith("__") and attr.endswith("__"):
                continue

            # Skip methods
            constant_value = getattr(cls, attr)
            if isinstance(constant_value, Callable):
                continue

            assert constant_value.startswith("/")
            assert attr.replace("_", "").casefold() == constant_value[1:].casefold()

            # There are a few exceptions that may be lowercase
            if cls == GraphicsStateParameters and attr in ["ca", "op"]:
                continue

            assert pattern.match(constant_value)


def test_user_access_permissions__dict_handling():
    # Value is mix of configurable and reserved bits.
    # Reserved bits should not be part of the dictionary.
    as_dict = UserAccessPermissions(512 + 64 + 8).to_dict()
    assert as_dict == {
        "add_or_modify": False,
        "assemble_doc": False,
        "extract": False,
        "extract_text_and_graphics": True,
        "fill_form_fields": False,
        "modify": True,
        "print": False,
        "print_to_representation": False,
    }

    # Convert the dictionary back to an integer.
    # This should add the reserved bits automatically.
    permissions = UserAccessPermissions.from_dict(as_dict)
    assert permissions == 4294963912

    # Roundtrip for valid dictionary.
    data = {
        "add_or_modify": True,
        "assemble_doc": False,
        "extract": False,
        "extract_text_and_graphics": True,
        "fill_form_fields": False,
        "modify": True,
        "print": False,
        "print_to_representation": True,
    }
    assert UserAccessPermissions.from_dict(data).to_dict() == data

    # Empty inputs.
    assert UserAccessPermissions.from_dict({}) == 4294963392  # Reserved bits.
    assert UserAccessPermissions(0).to_dict() == {
        "add_or_modify": False,
        "assemble_doc": False,
        "extract": False,
        "extract_text_and_graphics": False,
        "fill_form_fields": False,
        "modify": False,
        "print": False,
        "print_to_representation": False,
    }

    # Unknown dictionary keys.
    data = {
        "add_or_modify": True,
        "key1": False,
        "key2": True,
    }
    unknown = {
        "key1": False,
        "key2": True,
    }
    with pytest.raises(
        ValueError,
        match=f"Unknown dictionary keys: {unknown!r}"
    ):
        UserAccessPermissions.from_dict(data)


def test_user_access_permissions__all():
    all_permissions = UserAccessPermissions.all()
    all_int = int(all_permissions)
    all_string = bin(all_permissions)

    assert all_string.startswith("0b")
    assert len(all_string[2:]) == 32  # 32-bit integer

    assert all_int & UserAccessPermissions.R1 == 0
    assert all_int & UserAccessPermissions.R2 == 0
    assert all_int & UserAccessPermissions.PRINT == UserAccessPermissions.PRINT
    assert all_int & UserAccessPermissions.R7 == UserAccessPermissions.R7
    assert all_int & UserAccessPermissions.R31 == UserAccessPermissions.R31


def test_user_access_permissions__minimal():
    minimal_permissions = UserAccessPermissions.minimal()

    assert int(minimal_permissions) == 4294963392  # All reserved bits which should be one.

    assert minimal_permissions & UserAccessPermissions.R1 == 0
    assert minimal_permissions & UserAccessPermissions.R2 == 0
    assert minimal_permissions & UserAccessPermissions.PRINT == 0
    assert minimal_permissions & UserAccessPermissions.R7 == UserAccessPermissions.R7
    assert minimal_permissions & UserAccessPermissions.R31 == UserAccessPermissions.R31


def test_user_access_permissions__check():
    all_permissions = UserAccessPermissions.all()
    all_permissions.check()

    r1_set = all_permissions | UserAccessPermissions.R1
    with pytest.raises(ValueError, match="Invalid value for reserved bit R1."):
        r1_set.check()
    r2_set = all_permissions | UserAccessPermissions.R2
    with pytest.raises(ValueError, match="Invalid value for reserved bit R2."):
        r2_set.check()

    r8_unset = UserAccessPermissions(all_permissions - UserAccessPermissions.R8)
    with pytest.raises(ValueError, match="Invalid value for reserved bit R8."):
        r8_unset.check()
