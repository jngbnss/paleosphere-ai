import numpy as np
import pandas as pd

from paleosphere.ecosystem import COLUMNS
from training.forecasting.population import build_dataset, evaluate, pad_series, to_markdown


def synthetic(n_seeds: int = 40, samples: int = 120, extinct_seed: int | None = 31):
    """Predator-prey-like oscillations with a seed-dependent phase."""
    rows = []
    for seed in range(n_seeds):
        for i in range(samples):
            if seed == extinct_seed and i > 80:
                break  # series ended (everyone dead)
            phase = 2 * np.pi * i / 40 + seed
            row = dict.fromkeys(COLUMNS, 0.0)
            row.update(seed=seed, tick=i * 50, herbivores=round(25 + 15 * np.sin(phase)),
                       predators=round(3 + np.sin(phase - 1)), plant_food=300 + 50 * np.cos(phase))
            rows.append(row)
    return pd.DataFrame(rows)


def test_padding_keeps_extinct_series_at_zero():
    df = synthetic()
    padded = pad_series(df)
    g = padded[padded["seed"] == 31]
    assert len(g) == 120
    assert (g[g["tick"] > 80 * 50][["herbivores", "predators"]] == 0).all().all()


def test_dataset_excludes_dead_samples_and_has_future_target():
    ds = build_dataset(synthetic(), horizon=10)
    assert ds["tick"].min() >= 20 * 50
    assert ((ds["herbivores"] + ds["predators"]) > 0).all()
    assert not ds.isna().any().any()


def test_learned_models_beat_persistence_on_periodic_series():
    metrics, preds = evaluate(synthetic(), horizons=(10,))
    assert set(metrics["model"]) == {"persistence", "linear", "gbm"}
    herb = metrics[metrics["target"] == "herbivores"].set_index("model")["mae"]
    assert herb["gbm"] < herb["persistence"] and herb["linear"] < herb["persistence"]
    assert (preds["herbivores_gbm"] >= 0).all()
    assert "persistence" in to_markdown(metrics)
