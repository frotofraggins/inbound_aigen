"""
Shared test fixtures and path setup for EOD trading strategy tests.
Handles the relative import issue in services/position_manager/ modules.
"""
import sys
import os
import types
import importlib

_PM_DIR = os.path.join(os.path.dirname(__file__), '..', 'services', 'position_manager')
_PM_DIR = os.path.abspath(_PM_DIR)


def _load_pm_module(name: str):
    """Load a position_manager module, patching relative imports."""
    # If already loaded, return it
    full = f"services.position_manager.{name}"
    if full in sys.modules:
        return sys.modules[full]

    filepath = os.path.join(_PM_DIR, f"{name}.py")
    if not os.path.exists(filepath):
        raise ImportError(f"Cannot find {filepath}")

    spec = importlib.util.spec_from_file_location(full, filepath,
        submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)

    # Register under both names so relative imports resolve
    sys.modules[full] = mod
    sys.modules[name] = mod

    # Ensure the parent package exists
    if 'services' not in sys.modules:
        pkg = types.ModuleType('services')
        pkg.__path__ = [os.path.join(_PM_DIR, '..')]
        sys.modules['services'] = pkg
    if 'services.position_manager' not in sys.modules:
        pkg = types.ModuleType('services.position_manager')
        pkg.__path__ = [_PM_DIR]
        pkg.__package__ = 'services.position_manager'
        sys.modules['services.position_manager'] = pkg

    mod.__package__ = 'services.position_manager'
    spec.loader.exec_module(mod)

    # Also set as attribute on parent
    setattr(sys.modules['services.position_manager'], name, mod)
    return mod


# Pre-load modules in dependency order
_load_pm_module('eod_config')
_load_pm_module('eod_models')
_load_pm_module('eod_engine')
_load_pm_module('earnings_client')
_load_pm_module('close_loop')
