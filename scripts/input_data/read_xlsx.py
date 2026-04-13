"""Backward-compatibility shim. All logic lives in instance_io.py."""
from instance_io import (  # noqa: F401
    HANGAR,
    OUTPUT_DIR,
    SCENARIOS_DIR,
    convert_all_scenarios,
    load_json,
    read_xlsx,
    validate_instance,
    xlsx_to_json,
)
