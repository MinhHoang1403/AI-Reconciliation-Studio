import pytest
from pydantic import TypeAdapter, ValidationError
from studio.contracts import DatasetStatus, MappingStatus, Transform


def test_T14_forbidden_code_rejected():
    for injection in ["exec", "eval", "sql", "__import__"]:
        with pytest.raises(ValidationError):
            TypeAdapter(Transform).validate_python({"op": injection, "code": "DROP TABLE jobs"})
    with pytest.raises(ValidationError):
        TypeAdapter(Transform).validate_python(
            {"op": "cast_string_preserve", "code": '__import__("os")'}
        )


def test_status_dimensions_are_separate():
    assert "AMBIGUOUS" in MappingStatus
    assert "AMBIGUOUS" not in DatasetStatus
