"""Energy / hunger / thirst / health rules. Pure ecosystem rules, not AI."""

from __future__ import annotations

from paleosphere.config import MetabolismConfig, SpeciesConfig
from paleosphere.entities import DeathCause, Dino


def apply_metabolism(
    dino: Dino, sp: SpeciesConfig, cfg: MetabolismConfig, resting: bool, moved: bool
) -> DeathCause | None:
    """Update one living dino for one tick. Returns a death cause if it died."""
    dino.hunger = min(100.0, dino.hunger + sp.hunger_rate)
    thirst_gain = sp.thirst_rate + (sp.sprint_thirst_extra if dino.sprinting else 0.0)
    dino.thirst = min(100.0, dino.thirst + thirst_gain)

    if resting:
        dino.energy += sp.energy_rest_gain
    elif dino.sprinting:
        dino.energy -= sp.energy_sprint_cost
    elif moved:
        dino.energy -= sp.energy_walk_cost
    dino.energy = min(100.0, max(0.0, dino.energy))

    damage: dict[DeathCause, float] = {}
    if dino.hunger >= cfg.starving_threshold:
        damage[DeathCause.STARVATION] = cfg.starvation_damage
    if dino.thirst >= cfg.starving_threshold:
        damage[DeathCause.DEHYDRATION] = cfg.dehydration_damage
    if dino.energy <= 0.0:
        damage[DeathCause.EXHAUSTION] = cfg.exhaustion_damage

    if damage:
        dino.health -= sum(damage.values())
    elif dino.hunger < 80.0 and dino.thirst < 80.0:
        dino.health = min(100.0, dino.health + cfg.health_regen)

    if dino.health <= 0.0:
        dino.health = 0.0
        # Attribute death to the largest damage source this tick (ties: enum order).
        return max(damage, key=lambda c: damage[c]) if damage else DeathCause.EXHAUSTION
    return None
