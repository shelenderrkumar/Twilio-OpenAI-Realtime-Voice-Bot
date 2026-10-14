"""Agent personas. Each call gets a fresh profile so per-call state never leaks between callers."""

from voicebot.profiles.base import AgentProfile
from voicebot.profiles.grocery import build_grocery_profile
from voicebot.profiles.logistics import build_logistics_profile

BUILDERS = {"logistics": build_logistics_profile, "grocery": build_grocery_profile}


def build_profile(name: str, deps) -> AgentProfile:
    try:
        return BUILDERS[name](deps)
    except KeyError:
        raise ValueError(
            f"Unknown agent profile '{name}'. Choose from {sorted(BUILDERS)}"
        ) from None


__all__ = ["AgentProfile", "build_profile"]
