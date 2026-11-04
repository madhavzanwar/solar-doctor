"""SolarDoctor — AI solar O&M platform (base: AxalonSystems, MIT)."""
__version__ = "0.1.0"

# Backward compatibility: deployments configured with the legacy AXALON_* variables keep working.
# A SOLARDOCTOR_* value always wins; AXALON_* is only mirrored when the new name is unset.
import os as _os

for _k, _v in list(_os.environ.items()):
    if _k.startswith("AXALON_") and ("SOLARDOCTOR_" + _k[7:]) not in _os.environ:
        _os.environ["SOLARDOCTOR_" + _k[7:]] = _v
