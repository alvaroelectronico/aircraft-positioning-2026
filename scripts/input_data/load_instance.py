"""Backward-compatibility shim. All logic lives in instance_io.py."""
from instance_io import load_json as load_instance, validate_instance  # noqa: F401
