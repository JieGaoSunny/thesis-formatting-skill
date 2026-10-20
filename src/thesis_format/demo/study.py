"""Reproducible calculations for the fictional apple-leaf study."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from statistics import fmean, stdev
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Observation:
    round_id: str
    quadrat_id: str
    layer: str
    direction: str
    subquadrant_counts: tuple[int, int, int, int]
    occlusion_cues: int

    @property
    def base_count(self) -> int:
        return sum(self.subquadrant_counts)


@dataclass(frozen=True, slots=True)
class ScaleInputs:
    quadrat_area_m2: float
    crown_equivalent_area_m2: float
    simulated_truth: int
    layer_weights: tuple[tuple[str, float], ...]
    visible_ratios: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class MethodSummary:
    round_estimates: tuple[float, ...]
    mean_estimate: float
    rounded_estimate: int
    bias_percent: float
    cv_percent: float


@dataclass(frozen=True, slots=True)
class SensitivityEnvelope:
    lower: float
    upper: float
    rounded_bounds: tuple[int, int]


SIMULATED_OBSERVATIONS = (
    Observation("R1", "U-NE", "上层", "东北", (15, 16, 14, 15), 15),
    Observation("R1", "U-NW", "上层", "西北", (16, 17, 15, 16), 16),
    Observation("R1", "M-E", "中层", "东", (26, 27, 25, 26), 16),
    Observation("R1", "M-W", "中层", "西", (28, 27, 28, 27), 17),
    Observation("R1", "L-SE", "下层", "东南", (22, 22, 21, 22), 36),
    Observation("R1", "L-SW", "下层", "西南", (23, 23, 22, 23), 38),
    Observation("R2", "U-NE", "上层", "东北", (15, 15, 14, 16), 15),
    Observation("R2", "U-NW", "上层", "西北", (16, 15, 16, 15), 17),
    Observation("R2", "M-E", "中层", "东", (23, 25, 24, 22), 18),
    Observation("R2", "M-W", "中层", "西", (27, 28, 27, 27), 18),
    Observation("R2", "L-SE", "下层", "东南", (28, 27, 28, 27), 9),
    Observation("R2", "L-SW", "下层", "西南", (29, 28, 28, 28), 10),
    Observation("R3", "U-NE", "上层", "东北", (16, 16, 16, 16), 31),
    Observation("R3", "U-NW", "上层", "西北", (17, 17, 16, 17), 33),
    Observation("R3", "M-E", "中层", "东", (25, 24, 25, 24), 3),
    Observation("R3", "M-W", "中层", "西", (25, 25, 25, 25), 4),
    Observation("R3", "L-SE", "下层", "东南", (31, 31, 30, 31), 12),
    Observation("R3", "L-SW", "下层", "西南", (32, 32, 31, 32), 13),
)


DEFAULT_SCALE_INPUTS = ScaleInputs(
    quadrat_area_m2=0.25,
    crown_equivalent_area_m2=11.004869141813755,
    simulated_truth=4320,
    layer_weights=(("上层", 0.24), ("中层", 0.46), ("下层", 0.30)),
    visible_ratios=(("上层", 0.91), ("中层", 0.82), ("下层", 0.88)),
)


def _group_observations(
    observations: Iterable[Observation],
) -> dict[str, dict[str, list[Observation]]]:
    grouped: dict[str, dict[str, list[Observation]]] = {}
    for observation in observations:
        grouped.setdefault(observation.round_id, {}).setdefault(
            observation.layer, []
        ).append(observation)
    return grouped


def _round_estimates(
    observations: Iterable[Observation],
    inputs: ScaleInputs,
    *,
    visible_ratios: dict[str, float] | None = None,
    layer_weights: dict[str, float] | None = None,
    count_offset: int = 0,
) -> dict[str, tuple[float, ...]]:
    grouped = _group_observations(observations)
    weights = layer_weights or dict(inputs.layer_weights)
    visibility = visible_ratios or dict(inputs.visible_ratios)
    multiplier = inputs.crown_equivalent_area_m2 / inputs.quadrat_area_m2
    simple: list[float] = []
    stratified: list[float] = []
    corrected: list[float] = []

    for round_id in sorted(grouped):
        layers = grouped[round_id]
        rows = [row for layer_rows in layers.values() for row in layer_rows]
        simple.append(
            fmean(row.base_count + count_offset for row in rows) * multiplier
        )
        stratified.append(
            sum(
                weights[layer]
                * fmean(row.base_count + count_offset for row in layers[layer])
                for layer in weights
            )
            * multiplier
        )
        corrected.append(
            sum(
                weights[layer]
                * fmean(
                    row.base_count
                    + count_offset
                    + row.occlusion_cues * (1 / visibility[layer] - 1)
                    for row in layers[layer]
                )
                for layer in weights
            )
            * multiplier
        )
    return {
        "simple": tuple(simple),
        "stratified": tuple(stratified),
        "corrected": tuple(corrected),
    }


def calculate_reported_statistics(
    observations: Iterable[Observation], inputs: ScaleInputs
) -> dict[str, MethodSummary]:
    """Recompute every estimate, bias, and repeat-observation CV."""

    estimates = _round_estimates(observations, inputs)
    summaries: dict[str, MethodSummary] = {}
    for method, round_values in estimates.items():
        mean_estimate = fmean(round_values)
        summaries[method] = MethodSummary(
            round_estimates=round_values,
            mean_estimate=mean_estimate,
            rounded_estimate=round(mean_estimate),
            bias_percent=(mean_estimate - inputs.simulated_truth)
            / inputs.simulated_truth
            * 100,
            cv_percent=stdev(round_values) / mean_estimate * 100,
        )
    return summaries


def sensitivity_envelope(
    observations: Iterable[Observation], inputs: ScaleInputs
) -> SensitivityEnvelope:
    """Return the one-factor-at-a-time deterministic sensitivity envelope."""

    observations = tuple(observations)
    weights = dict(inputs.layer_weights)
    visibility = dict(inputs.visible_ratios)
    scenarios: list[float] = []

    for shifts in product((-0.03, 0.03), repeat=len(visibility)):
        shifted = {
            layer: visibility[layer] + shift
            for layer, shift in zip(visibility, shifts, strict=True)
        }
        scenarios.append(
            fmean(
                _round_estimates(
                    observations, inputs, visible_ratios=shifted
                )["corrected"]
            )
        )

    layers = tuple(weights)
    for source in layers:
        for target in layers:
            if source == target:
                continue
            shifted = weights.copy()
            shifted[source] -= 0.02
            shifted[target] += 0.02
            scenarios.append(
                fmean(
                    _round_estimates(
                        observations, inputs, layer_weights=shifted
                    )["corrected"]
                )
            )

    for count_offset in (-1, 1):
        scenarios.append(
            fmean(
                _round_estimates(
                    observations, inputs, count_offset=count_offset
                )["corrected"]
            )
        )

    lower = min(scenarios)
    upper = max(scenarios)
    return SensitivityEnvelope(
        lower=lower,
        upper=upper,
        rounded_bounds=(round(lower), round(upper)),
    )
