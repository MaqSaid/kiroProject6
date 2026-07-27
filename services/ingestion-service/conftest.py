"""Root conftest for ingestion-service tests.

Handles module aliasing for the service_client library which is installed
as 'src' package from libs/service-client but imported as 'service_client'
in the service code.
"""

import importlib.util
import sys
from pathlib import Path

# Resolve path to service-client library
_service_client_src = Path(__file__).parent.parent.parent / "libs" / "service-client" / "src"

if "service_client" not in sys.modules:
    # Load the service-client's __init__.py as the 'service_client' module
    _init_path = _service_client_src / "__init__.py"
    _spec = importlib.util.spec_from_file_location(
        "service_client",
        str(_init_path),
        submodule_search_locations=[str(_service_client_src)],
    )
    if _spec and _spec.loader:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules["service_client"] = _module
        _spec.loader.exec_module(_module)  # type: ignore
