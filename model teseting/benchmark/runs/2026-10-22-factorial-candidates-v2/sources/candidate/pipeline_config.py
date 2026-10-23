"""Explicit immutable configuration; candidates require opt-in and client targeting."""
from dataclasses import asdict, dataclass
import math
import os


@dataclass(frozen=True)
class ScoringConfig:
    current_enabled: bool = False
    quiet_enabled: bool = False
    horizon_sec: float = 16.0
    current_mode: str = "mean"
    min_usable_sec: float = 3.0
    entry_usable_sec: float = 3.0
    recovery_usable_sec: float = 3.0
    warning_usable_sec: float = 6.0
    half_life_sec: float = 8.0
    wire_version: str = "call-evidence-v1"

    def __post_init__(self):
        if self.current_mode not in ("mean", "decay"):
            raise ValueError("Unknown current evidence mode")
        if self.wire_version not in ("call-evidence-v1", "call-evidence-v2"):
            raise ValueError("Unknown scoring wire version")
        if self.current_enabled and self.wire_version != "call-evidence-v2":
            raise ValueError("Current evidence requires explicitly targeted v2 clients")
        for name in ("horizon_sec", "min_usable_sec", "entry_usable_sec", "recovery_usable_sec",
                     "warning_usable_sec", "half_life_sec"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"Invalid {name}")

    def metadata(self):
        return asdict(self)

    @classmethod
    def from_env(cls):
        def flag(name):
            value = os.environ.get(name, "0")
            if value not in ("0", "1"):
                raise ValueError(f"{name} must be 0 or 1")
            return value == "1"
        return cls(current_enabled=flag("CURRENT_EVIDENCE_ENABLED"),
                   quiet_enabled=flag("QUIET_ELIGIBILITY_ENABLED"),
                   wire_version=os.environ.get("SCORING_WIRE_VERSION", "call-evidence-v1"),
                   horizon_sec=float(os.environ.get("CURRENT_HORIZON_SEC", "16")),
                   current_mode=os.environ.get("CURRENT_EVIDENCE_MODE", "mean"))
