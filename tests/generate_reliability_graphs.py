"""
Generate reliability threshold graphs for docs/reliability_thresholds.md (v4).

Produces:
  - docs/avg_reliability_comparison_n20_v4.png
  - docs/avg_reliability_comparison_n50_v4.png
  - docs/pairing_improvement_delta.png

Also prints threshold tables and calculator-vs-real calibration rows for the doc.
"""
from __future__ import annotations

import math
import os
import random
import sys
from typing import Dict, List, Optional, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np

# Allow `python tests/generate_reliability_graphs.py` from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.elo import Rating
from core.glicko2 import Glicko2Rating
from core.reliability_calculator import ReliabilityCalculator

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
SEEDS = [42, 123, 456, 508, 749, 862]
THRESHOLDS = [80, 85, 90, 95]
CHECK_EVERY = 5


class Media:
    def __init__(self, media_id: int, objective_score: int):
        self.id = media_id
        self.objective_score = objective_score
        self.elo_dyn = 1000.0
        self.elo_fixed = 1000.0
        self.glicko = {"mu": 1200.0, "phi": 350.0, "sigma": 0.06}
        self.vote_count = 0


def compute_real_reliability(original: List[Media], current: List[Media]) -> float:
    correct = 0
    total = 0
    position_map = {m: idx for idx, m in enumerate(current)}
    for i in range(len(original)):
        for j in range(i + 1, len(original)):
            m1, m2 = original[i], original[j]
            if position_map[m1] < position_map[m2]:
                correct += 1
            total += 1
    return (correct / total) * 100 if total else 0.0


def old_calculate_reliability(n: int, v: int) -> float:
    """Pre-v4 formula (single curve, no system/phi awareness)."""
    if n <= 0 or v < 0:
        return 0.0
    vpi = v / n
    return min(
        100.0,
        50.0
        + 25.0 * (1 - math.exp(-vpi / 2))
        + 20.0 * (1 - math.exp(-vpi / 10))
        + 5.0 * (1 - math.exp(-vpi / 50)),
    )


def _edge_key(a: Media, b: Media) -> Tuple[int, int]:
    return (min(a.id, b.id), max(a.id, b.id))


def pick_legacy(medias: List[Media], seen: Set[Tuple[int, int]]) -> Tuple[Media, Media]:
    min_votes = min(m.vote_count for m in medias)
    candidates = [m for m in medias if m.vote_count == min_votes]
    a = random.choice(candidates)
    b = random.choice([m for m in medias if m is not a])
    return a, b


def pick_smart_shared(medias: List[Media], seen: Set[Tuple[int, int]]) -> Tuple[Media, Media]:
    """
    Shared-outcome pairing for multi-method comparison.

    Uses least-voted primary + Dynamic-Elo nearby opponents with rematch
    avoidance. Glicko-φ-first pairing is Glicko-optimal and unfairly starves
    Elo when all three systems share the same edges (Elo real reliability
    collapses after ~90%). Production Glicko pairing is measured separately
    in the pairing-delta graph via pick_smart_glicko().
    """
    min_votes = min(m.vote_count for m in medias)
    candidates = [m for m in medias if m.vote_count == min_votes]
    a = random.choice(candidates)
    others = [m for m in medias if m is not a]
    for max_diff in (100, 200, None):
        pool = others
        if max_diff is not None:
            pool = [m for m in others if abs(m.elo_dyn - a.elo_dyn) <= max_diff] or others
        fresh = [m for m in pool if _edge_key(a, m) not in seen]
        pool = fresh or pool
        pool = sorted(pool, key=lambda m: (abs(m.elo_dyn - a.elo_dyn), m.vote_count))
        return a, pool[0]
    return a, others[0]


def pick_smart_glicko(medias: List[Media], seen: Set[Tuple[int, int]]) -> Tuple[Media, Media]:
    """Production-like Glicko pairing: high φ primary, rating-nearby, no rematches."""
    ordered = sorted(medias, key=lambda m: (-m.glicko["phi"], m.vote_count, random.random()))
    a = ordered[0]
    others = [m for m in medias if m is not a]
    for max_diff in (100, 200, None):
        pool = others
        if max_diff is not None:
            pool = [m for m in others if abs(m.glicko["mu"] - a.glicko["mu"]) <= max_diff] or others
        fresh = [m for m in pool if _edge_key(a, m) not in seen]
        candidates = fresh or pool
        candidates = sorted(
            candidates,
            key=lambda m: (abs(m.glicko["mu"] - a.glicko["mu"]), -m.glicko["phi"], m.vote_count),
        )
        return a, candidates[0]
    return a, others[0]


def _first_crossings(series: List[Tuple[int, float]]) -> Dict[int, Optional[int]]:
    """series: list of (votes, reliability). Return first votes at each threshold."""
    found = {t: None for t in THRESHOLDS}
    for votes, rel in series:
        for t in THRESHOLDS:
            if found[t] is None and rel >= t:
                found[t] = votes
    return found


def simulate_methods(
    n: int,
    smart: bool,
    max_votes: Optional[int] = None,
    record_curves: bool = True,
) -> dict:
    """
    Run one simulation updating Dynamic Elo, Fixed Elo, and Glicko on the same
    objective outcomes. Smart mode uses least-voted + Elo-nearby rematch-aware
    pairing so shared edges remain fair to all three rating systems.
    """
    if max_votes is None:
        max_votes = n * 100

    original = [Media(i, n - i) for i in range(n)]
    medias = list(original)
    random.shuffle(medias)
    seen: Set[Tuple[int, int]] = set()
    pick = pick_smart_shared if smart else pick_legacy

    curves = {
        "votes": [],
        "dynamic": [],
        "fixed": [],
        "glicko": [],
        "calc_elo": [],
        "calc_glicko": [],
        "calc_old": [],
    }
    crossings = {
        "dynamic": {t: None for t in THRESHOLDS},
        "fixed": {t: None for t in THRESHOLDS},
        "glicko": {t: None for t in THRESHOLDS},
    }
    # Also track 94% for threshold justification section
    cross_94 = {"dynamic": None, "fixed": None, "glicko": None}

    total_votes = 0
    while total_votes < max_votes:
        a, b = pick(medias, seen)
        if a.objective_score > b.objective_score:
            winner, loser = a, b
        else:
            winner, loser = b, a

        # Dynamic Elo K based on calculator (Elo curve)
        calc_rel = ReliabilityCalculator.calculate_reliability(n, total_votes, "elo")
        k_factor = 32 if calc_rel < 85 else 16
        dyn = Rating(winner.elo_dyn, loser.elo_dyn, Rating.WIN, Rating.LOST, k_factor)
        new_dyn = dyn.get_new_ratings()
        winner.elo_dyn = new_dyn["a"]
        loser.elo_dyn = new_dyn["b"]

        fixed = Rating(winner.elo_fixed, loser.elo_fixed, Rating.WIN, Rating.LOST, 16)
        new_fixed = fixed.get_new_ratings()
        winner.elo_fixed = new_fixed["a"]
        loser.elo_fixed = new_fixed["b"]

        updated = Glicko2Rating(
            winner.glicko["mu"], winner.glicko["phi"], winner.glicko["sigma"],
            loser.glicko["mu"], loser.glicko["phi"], loser.glicko["sigma"],
            1.0, 0.0,
        ).get_new_ratings()
        winner.glicko = updated["a"]
        loser.glicko = updated["b"]

        a.vote_count += 1
        b.vote_count += 1
        seen.add(_edge_key(a, b))
        total_votes += 1

        if total_votes % CHECK_EVERY == 0:
            dyn_order = sorted(medias, key=lambda m: -m.elo_dyn)
            fix_order = sorted(medias, key=lambda m: -m.elo_fixed)
            gli_order = sorted(medias, key=lambda m: -m.glicko["mu"])
            r_dyn = compute_real_reliability(original, dyn_order)
            r_fix = compute_real_reliability(original, fix_order)
            r_gli = compute_real_reliability(original, gli_order)

            for key, rel in (("dynamic", r_dyn), ("fixed", r_fix), ("glicko", r_gli)):
                for t in THRESHOLDS:
                    if crossings[key][t] is None and rel >= t:
                        crossings[key][t] = total_votes
                if cross_94[key] is None and rel >= 94:
                    cross_94[key] = total_votes

            if record_curves:
                curves["votes"].append(total_votes)
                curves["dynamic"].append(r_dyn)
                curves["fixed"].append(r_fix)
                curves["glicko"].append(r_gli)
                curves["calc_elo"].append(
                    ReliabilityCalculator.calculate_reliability(n, total_votes, "elo")
                )
                mean_phi = sum(m.glicko["phi"] for m in medias) / n
                curves["calc_glicko"].append(
                    ReliabilityCalculator.calculate_reliability(
                        n, total_votes, "glicko2", mean_phi=mean_phi
                    )
                )
                curves["calc_old"].append(old_calculate_reliability(n, total_votes))

            # Stop once all methods reached 95%
            if all(crossings[k][95] is not None for k in crossings):
                break

    return {"crossings": crossings, "cross_94": cross_94, "curves": curves, "votes": total_votes}


def average_crossings(n: int, smart: bool = True) -> dict:
    agg = {
        method: {t: [] for t in THRESHOLDS}
        for method in ("dynamic", "fixed", "glicko")
    }
    cross_94 = {method: [] for method in ("dynamic", "fixed", "glicko")}
    curve_runs = []

    for seed in SEEDS:
        random.seed(seed)
        result = simulate_methods(n, smart=smart, record_curves=True)
        curve_runs.append(result["curves"])
        for method in agg:
            for t in THRESHOLDS:
                val = result["crossings"][method][t]
                if val is not None:
                    agg[method][t].append(val)
            if result["cross_94"][method] is not None:
                cross_94[method].append(result["cross_94"][method])

    averaged = {
        method: {
            t: int(round(float(np.mean(vals)))) if vals else None
            for t, vals in thresholds.items()
        }
        for method, thresholds in agg.items()
    }
    avg_94 = {
        method: int(round(float(np.mean(vals)))) if vals else None
        for method, vals in cross_94.items()
    }

    # Average curves onto a common vote grid (interpolate)
    max_len = max(len(c["votes"]) for c in curve_runs)
    # Use first run's vote axis if lengths differ; better: resample to shared votes
    all_vote_ends = [c["votes"][-1] for c in curve_runs if c["votes"]]
    vote_max = min(all_vote_ends) if all_vote_ends else 0
    vote_axis = list(range(CHECK_EVERY, vote_max + 1, CHECK_EVERY))

    def interp_series(votes, values, axis):
        if not votes:
            return [float("nan")] * len(axis)
        return list(np.interp(axis, votes, values))

    avg_curves = {"votes": vote_axis}
    for key in ("dynamic", "fixed", "glicko", "calc_elo", "calc_glicko", "calc_old"):
        series = [interp_series(c["votes"], c[key], vote_axis) for c in curve_runs]
        avg_curves[key] = list(np.nanmean(series, axis=0))

    return {"crossings": averaged, "cross_94": avg_94, "curves": avg_curves}


def plot_avg_comparison(n: int, data: dict, filename: str):
    curves = data["curves"]
    plt.figure(figsize=(12, 6))
    plt.plot(curves["votes"], curves["dynamic"], label="Dynamic ELO", color="#1f77b4")
    plt.plot(curves["votes"], curves["fixed"], label="Fixed ELO (K=16)", color="#ff7f0e")
    plt.plot(curves["votes"], curves["glicko"], label="Glicko2", color="#2ca02c")
    for t in (85, 94):
        plt.axhline(t, color="gray", linestyle=":", linewidth=1, alpha=0.7)
    plt.title(
        f"Average Real Reliability vs Votes "
        f"(n={n}, nearby+rematch pairing, {len(SEEDS)} seeds)"
    )
    plt.xlabel("Total Votes")
    plt.ylabel("Real Reliability (%)")
    plt.ylim(50, 100)
    plt.legend()
    plt.grid(True, alpha=0.3)
    path = os.path.join(DOCS_DIR, filename)
    plt.savefig(path, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"Wrote {path}")


def simulate_glicko_until(n: int, threshold: float, smart: bool, max_votes: int = 100000) -> int:
    original = [Media(i, n - i) for i in range(n)]
    medias = list(original)
    random.shuffle(medias)
    seen: Set[Tuple[int, int]] = set()
    pick = pick_smart_glicko if smart else pick_legacy
    total = 0
    while total < max_votes:
        a, b = pick(medias, seen)
        winner, loser = (a, b) if a.objective_score > b.objective_score else (b, a)
        updated = Glicko2Rating(
            winner.glicko["mu"], winner.glicko["phi"], winner.glicko["sigma"],
            loser.glicko["mu"], loser.glicko["phi"], loser.glicko["sigma"],
            1.0, 0.0,
        ).get_new_ratings()
        winner.glicko = updated["a"]
        loser.glicko = updated["b"]
        a.vote_count += 1
        b.vote_count += 1
        seen.add(_edge_key(a, b))
        total += 1
        if total % 25 == 0:
            ranked = sorted(medias, key=lambda m: -m.glicko["mu"])
            if compute_real_reliability(original, ranked) >= threshold:
                return total
    return max_votes


def plot_pairing_delta():
    n_values = [20, 50, 100]
    thresholds = [85, 90, 94]
    # results[threshold][n] = (legacy_avg, smart_avg)
    results: Dict[int, Dict[int, Tuple[float, float]]] = {t: {} for t in thresholds}

    for threshold in thresholds:
        print(f"\nPairing delta @ {threshold}%:")
        for n in n_values:
            legacy_votes = []
            smart_votes = []
            for seed in SEEDS:
                random.seed(seed)
                legacy_votes.append(simulate_glicko_until(n, threshold, smart=False))
                random.seed(seed)
                smart_votes.append(simulate_glicko_until(n, threshold, smart=True))
            leg = float(np.mean(legacy_votes))
            sm = float(np.mean(smart_votes))
            results[threshold][n] = (leg, sm)
            savings = (leg - sm) / leg * 100 if leg else 0
            print(f"  n={n}: legacy={leg:.0f} smart={sm:.0f} save={savings:.1f}%")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: grouped bars of votes
    x = np.arange(len(n_values))
    width = 0.12
    colors_leg = ["#aec7e8", "#ffbb78", "#98df8a"]
    colors_sm = ["#1f77b4", "#ff7f0e", "#2ca02c"]
    for i, threshold in enumerate(thresholds):
        leg = [results[threshold][n][0] for n in n_values]
        sm = [results[threshold][n][1] for n in n_values]
        offset = (i - 1) * width * 2
        axes[0].bar(x + offset - width / 2, leg, width, label=f"Legacy {threshold}%",
                    color=colors_leg[i], edgecolor="black", linewidth=0.3)
        axes[0].bar(x + offset + width / 2, sm, width, label=f"Smart {threshold}%",
                    color=colors_sm[i], edgecolor="black", linewidth=0.3)

    axes[0].set_xticks(x)
    axes[0].set_xticklabels([str(n) for n in n_values])
    axes[0].set_xlabel("Media Items (n)")
    axes[0].set_ylabel("Votes to Threshold")
    axes[0].set_title("Legacy vs Smart Pairing (Glicko2)")
    axes[0].legend(fontsize=8, ncol=2)
    axes[0].grid(True, axis="y", alpha=0.3)

    # Right: % savings
    for threshold, color, marker in zip(thresholds, colors_sm, ["o", "s", "^"]):
        savings = [
            (results[threshold][n][0] - results[threshold][n][1]) / results[threshold][n][0] * 100
            for n in n_values
        ]
        axes[1].plot(n_values, savings, marker=marker, color=color, label=f"{threshold}% threshold")
    axes[1].set_xlabel("Media Items (n)")
    axes[1].set_ylabel("Vote Savings (%)")
    axes[1].set_title("Improvement from Smart Pairing")
    axes[1].set_ylim(0, 80)
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    path = os.path.join(DOCS_DIR, "pairing_improvement_delta.png")
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"Wrote {path}")
    return results


def print_calibration_table(n: int, data: dict):
    """Print old/new calc vs measured Glicko real reliability at selected vote counts."""
    curves = data["curves"]
    sample_votes = [40, 110, 290, 510] if n >= 50 else [20, 40, 80, 150]
    print(f"\nCalibration sample (n={n}, Glicko real vs calculators):")
    print(f"{'Votes':<8} {'Old Calc':<10} {'Elo Calc':<10} {'Glicko Calc':<12} {'Actual Glicko':<14}")
    for v in sample_votes:
        if not curves["votes"] or v > curves["votes"][-1]:
            continue
        # nearest index
        idx = min(range(len(curves["votes"])), key=lambda i: abs(curves["votes"][i] - v))
        print(
            f"{curves['votes'][idx]:<8} "
            f"{curves['calc_old'][idx]:<10.1f} "
            f"{curves['calc_elo'][idx]:<10.1f} "
            f"{curves['calc_glicko'][idx]:<12.1f} "
            f"{curves['glicko'][idx]:<14.1f}"
        )


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)

    print("=" * 60)
    print("Average method comparison (smart pairing)")
    print("=" * 60)
    results_by_n = {}
    for n in (20, 50):
        print(f"\n--- n={n} ---")
        data = average_crossings(n, smart=True)
        results_by_n[n] = data
        plot_avg_comparison(n, data, f"avg_reliability_comparison_n{n}_v4.png")
        print(f"{'Method':<14} {'80%':<8} {'85%':<8} {'90%':<8} {'95%':<8} {'94%':<8}")
        labels = {"dynamic": "Dynamic ELO", "fixed": "Fixed ELO", "glicko": "Glicko2"}
        for key, label in labels.items():
            c = data["crossings"][key]
            r94 = data["cross_94"][key]
            print(
                f"{label:<14} "
                f"{c[80] or '-':<8} {c[85] or '-':<8} {c[90] or '-':<8} "
                f"{c[95] or '-':<8} {r94 or '-':<8}"
            )
        print_calibration_table(n, data)

    print("\n" + "=" * 60)
    print("Pairing improvement delta")
    print("=" * 60)
    delta = plot_pairing_delta()

    # Machine-readable summary for doc authoring
    print("\n=== DOC SUMMARY ===")
    for n, data in results_by_n.items():
        print(f"CASE n={n}")
        for key in ("dynamic", "fixed", "glicko"):
            c = data["crossings"][key]
            print(f"  {key}: 80={c[80]} 85={c[85]} 90={c[90]} 95={c[95]} 94={data['cross_94'][key]}")


if __name__ == "__main__":
    main()
