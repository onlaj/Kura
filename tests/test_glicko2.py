import random
from statistics import mean
from typing import List, Tuple
import matplotlib.pyplot as plt
import numpy as np
import pytest

from core.elo import ReliabilityCalculator, Rating
from core.glicko2 import Glicko2Rating


class Media:
    """Represents a media item with an objective score and multiple ratings."""

    def __init__(self, media_id: int, objective_score: int):
        self.id = media_id
        self.objective_score = objective_score
        self.elo = 1000.0  # Dynamic ELO rating (with changing K factor)
        self.elo_fixed = 1000.0  # Fixed K factor ELO rating (always 16)
        # Glicko2 rating stored as a dict with mu, phi, sigma
        self.glicko2 = {"mu": 1500.0, "phi": 350.0, "sigma": 0.06}
        self.vote_count = 0


def compute_real_reliability(original_order: List[Media], current_order: List[Media]) -> float:
    """Calculate alignment with objective ranking using pairwise comparisons."""
    correct = 0
    total = 0
    # Build mapping of media to index in the current ranking
    position_map = {m: idx for idx, m in enumerate(current_order)}

    # Compare all possible pairs
    for i in range(len(original_order)):
        for j in range(i + 1, len(original_order)):
            m1 = original_order[i]
            m2 = original_order[j]
            if position_map[m1] < position_map[m2]:
                correct += 1
            total += 1

    return (correct / total) * 100 if total > 0 else 0.0


def simulate_and_plot(n: int, seed: int) -> dict:
    """Run simulation with a specific seed."""
    random.seed(seed)
    # Setup media items with objective scores (highest score = best ranking)
    original = [Media(i, n - i) for i in range(n)]
    medias = original.copy()
    random.shuffle(medias)

    # Lists to record checkpoints
    votes_data = []
    calc_reliability_data = []
    elo_dynamic_reliability = []
    elo_fixed_reliability = []
    glicko2_reliability = []

    # For each system, track crossing points between calculated and real reliability
    crossing_points = {
        "elo_dynamic": [],
        "elo_fixed": [],
        "glicko2": []
    }
    # For detecting sign changes (difference = calc - real)
    prev_diff = {"elo_dynamic": None, "elo_fixed": None, "glicko2": None}

    total_votes = 0

    while True:
        # Select media_a among those with the fewest votes
        min_votes = min(m.vote_count for m in medias)
        candidates = [m for m in medias if m.vote_count == min_votes]
        media_a = random.choice(candidates)

        # Use the theoretical calculated reliability for vote selection
        current_calc = ReliabilityCalculator.calculate_reliability(n, total_votes)

        # For media_b selection: if overall reliability is high enough, choose an opponent with a similar dynamic ELO
        if current_calc >= 85:
            eligible = [m for m in medias if m != media_a and abs(m.elo - media_a.elo) <= 100]
            media_b = random.choice(eligible) if eligible else random.choice([m for m in medias if m != media_a])
        else:
            media_b = random.choice([m for m in medias if m != media_a])

        # Determine winner based solely on objective_score
        if media_a.objective_score > media_b.objective_score:
            winner, loser = media_a, media_b
        else:
            winner, loser = media_b, media_a

        # --- Update ratings for each system ---
        # Dynamic ELO update: use a K-factor of 32 if reliability is low, otherwise 16
        k_dynamic = 32 if current_calc < 85 else 16
        rating_dynamic = Rating(winner.elo, loser.elo, Rating.WIN, Rating.LOST, k_dynamic)
        new_ratings_dynamic = rating_dynamic.get_new_ratings()
        winner.elo = new_ratings_dynamic['a']
        loser.elo = new_ratings_dynamic['b']

        # Fixed ELO update: always use K=16
        rating_fixed = Rating(winner.elo_fixed, loser.elo_fixed, Rating.WIN, Rating.LOST, 16)
        new_ratings_fixed = rating_fixed.get_new_ratings()
        winner.elo_fixed = new_ratings_fixed['a']
        loser.elo_fixed = new_ratings_fixed['b']

        # Glicko2 update: update using the Glicko2 system
        new_glicko = Glicko2Rating(
            winner.glicko2["mu"], winner.glicko2["phi"], winner.glicko2["sigma"],
            loser.glicko2["mu"], loser.glicko2["phi"], loser.glicko2["sigma"],
            1, 0
        ).get_new_ratings()
        winner.glicko2 = new_glicko["a"]
        loser.glicko2 = new_glicko["b"]

        # Update vote counts (common for all systems) and total votes
        media_a.vote_count += 1
        media_b.vote_count += 1
        total_votes += 1

        # Record data every 1 votes
        if total_votes % 1 == 0:
            votes_data.append(total_votes)
            calc_reliability_data.append(current_calc)

            # Dynamic ELO: sort by m.elo descending
            sorted_dynamic = sorted(medias, key=lambda m: -m.elo)
            real_dynamic = compute_real_reliability(original, sorted_dynamic)
            elo_dynamic_reliability.append(real_dynamic)

            # Fixed ELO: sort by m.elo_fixed descending
            sorted_fixed = sorted(medias, key=lambda m: -m.elo_fixed)
            real_fixed = compute_real_reliability(original, sorted_fixed)
            elo_fixed_reliability.append(real_fixed)

            # Glicko2: sort by m.glicko2["mu"] descending
            sorted_glicko2 = sorted(medias, key=lambda m: -m.glicko2["mu"])
            real_glicko2 = compute_real_reliability(original, sorted_glicko2)
            glicko2_reliability.append(real_glicko2)

            # For each system, detect crossing points (where calc - real changes sign)
            for key, real_value in zip(["elo_dynamic", "elo_fixed", "glicko2"],
                                       [real_dynamic, real_fixed, real_glicko2]):
                diff = current_calc - real_value
                if prev_diff[key] is not None:
                    if (prev_diff[key] < 0 <= diff) or (prev_diff[key] > 0 >= diff):
                        # Linear interpolation between last two checkpoints:
                        x0 = votes_data[-2] if len(votes_data) >= 2 else total_votes - 10
                        x1 = total_votes
                        # Get previous real reliability value for the system
                        if key == "elo_dynamic":
                            y0 = elo_dynamic_reliability[-2] if len(elo_dynamic_reliability) >= 2 else real_value
                        elif key == "elo_fixed":
                            y0 = elo_fixed_reliability[-2] if len(elo_fixed_reliability) >= 2 else real_value
                        else:  # glicko2
                            y0 = glicko2_reliability[-2] if len(glicko2_reliability) >= 2 else real_value
                        y1 = real_value
                        # Similarly, previous calculated reliability
                        y0_calc = calc_reliability_data[-2] if len(calc_reliability_data) >= 2 else current_calc
                        y1_calc = current_calc
                        m_calc = (y1_calc - y0_calc) / (x1 - x0) if (x1 - x0) != 0 else 0
                        m_real = (y1 - y0) / (x1 - x0) if (x1 - x0) != 0 else 0
                        if m_calc != m_real:
                            x_cross = x0 - (y0_calc - y0) / (m_calc - m_real)
                            y_cross = y0 + m_real * (x_cross - x0)
                            crossing_points[key].append((x_cross, y_cross))
                prev_diff[key] = diff

            # End simulation when calculated reliability reaches 96%
            if current_calc >= 96:
                break

    # Record final orderings (by objective score) according to each system’s rating
    final_order_dynamic = [m.objective_score for m in sorted(medias, key=lambda m: -m.elo)]
    final_order_fixed = [m.objective_score for m in sorted(medias, key=lambda m: -m.elo_fixed)]
    final_order_glicko2 = [m.objective_score for m in sorted(medias, key=lambda m: -m.glicko2["mu"])]

    # Compile statistics to return
    stats = {
        "votes_data": votes_data,
        "calc_reliability": calc_reliability_data,
        "elo_dynamic_reliability": elo_dynamic_reliability,
        "elo_fixed_reliability": elo_fixed_reliability,
        "glicko2_reliability": glicko2_reliability,
        "crossing_points": crossing_points,
        "total_votes": total_votes,
        "original_scores": [m.objective_score for m in original],
        "final_order_dynamic": final_order_dynamic,
        "final_order_fixed": final_order_fixed,
        "final_order_glicko2": final_order_glicko2,
        "final_dynamic_elos": [m.elo for m in sorted(medias, key=lambda m: -m.elo)],
        "final_fixed_elos": [m.elo_fixed for m in sorted(medias, key=lambda m: -m.elo_fixed)],
        "final_glicko2_mus": [m.glicko2["mu"] for m in sorted(medias, key=lambda m: -m.glicko2["mu"])]
    }
    return stats


def run_multi_seed_simulation(n: int, seeds: List[int]):
    """Run simulations with multiple seeds and aggregate results."""
    all_stats = []
    for seed in seeds:
        stats = simulate_and_plot(n, seed)
        all_stats.append(stats)

    # Aggregate results
    aggregated_stats = {
        "avg_total_votes": mean(s["total_votes"] for s in all_stats),
        "avg_final_calc_reliability": mean(s["calc_reliability"][-1] for s in all_stats),
        "avg_final_dynamic_reliability": mean(s["elo_dynamic_reliability"][-1] for s in all_stats),
        "avg_final_fixed_reliability": mean(s["elo_fixed_reliability"][-1] for s in all_stats),
        "avg_final_glicko2_reliability": mean(s["glicko2_reliability"][-1] for s in all_stats),

        "avg_calc_reliability_checkpoints": None,
        "avg_elo_dynamic_reliability_checkpoints": None,
        "avg_elo_fixed_reliability_checkpoints": None,
        "avg_glicko2_reliability_checkpoints": None,
    }

    # Calculate average reliability curves
    max_length = max(len(s["votes_data"]) for s in all_stats)
    votes_data = next(s["votes_data"] for s in all_stats if len(s["votes_data"]) == max_length)

    # Initialize arrays for averaging
    calc_rel_sum = np.zeros(max_length)
    dynamic_rel_sum = np.zeros(max_length)
    fixed_rel_sum = np.zeros(max_length)
    glicko2_rel_sum = np.zeros(max_length)
    count = np.zeros(max_length)

    # Sum up all values
    for stats in all_stats:
        length = len(stats["votes_data"])
        calc_rel_sum[:length] += stats["calc_reliability"]
        dynamic_rel_sum[:length] += stats["elo_dynamic_reliability"]
        fixed_rel_sum[:length] += stats["elo_fixed_reliability"]
        glicko2_rel_sum[:length] += stats["glicko2_reliability"]
        count[:length] += 1

    # Calculate averages for checkpoints
    calc_rel_avg = calc_rel_sum / count
    dynamic_rel_avg = dynamic_rel_sum / count
    fixed_rel_avg = fixed_rel_sum / count
    glicko2_rel_avg = glicko2_rel_sum / count

    aggregated_stats["avg_calc_reliability_checkpoints"] = calc_rel_avg
    aggregated_stats["avg_elo_dynamic_reliability_checkpoints"] = dynamic_rel_avg
    aggregated_stats["avg_elo_fixed_reliability_checkpoints"] = fixed_rel_avg
    aggregated_stats["avg_glicko2_reliability_checkpoints"] = glicko2_rel_avg


    # Plot averaged curves
    plt.figure(figsize=(12, 6))
    plt.plot(votes_data, dynamic_rel_avg, label="Dynamic ELO Reliability", color="blue")
    plt.plot(votes_data, fixed_rel_avg, label="Fixed ELO Reliability", color="green")
    plt.plot(votes_data, glicko2_rel_avg, label="Glicko2 Reliability", color="orange")
    plt.plot(votes_data, calc_rel_avg, label="Calculated Reliability", color="red", linestyle="--")

    plt.title(f"Average Reliability Comparison (n={n}, seeds={seeds})")
    plt.xlabel("Total Votes")
    plt.ylabel("Reliability (%)")
    plt.ylim(45, 100)
    plt.legend()
    plt.grid(True)

    filename = f"avg_reliability_comparison_n{n}.png"
    plt.savefig(filename)
    plt.close()

    aggregated_stats["plot_file"] = filename
    aggregated_stats["votes_data"] = votes_data # Pass votes_data for checkpoint table printing
    return aggregated_stats, all_stats


@pytest.mark.parametrize("n", [20, 50])
def test_reliability_with_graph(n: int):
    seeds = [42, 23, 45, 56]  # Editable list of seeds
    aggregated_stats, all_stats = run_multi_seed_simulation(n, seeds)

    print(f"\nResults averaged across {len(seeds)} seeds ({seeds}):")
    print(f"Average total votes: {aggregated_stats['avg_total_votes']:.1f}")
    print(f"Average final calculated reliability: {aggregated_stats['avg_final_calc_reliability']:.1f}%")
    print(f"Average final dynamic ELO reliability: {aggregated_stats['avg_final_dynamic_reliability']:.1f}%")
    print(f"Average final fixed ELO reliability: {aggregated_stats['avg_final_fixed_reliability']:.1f}%")
    print(f"Average final Glicko2 reliability: {aggregated_stats['avg_final_glicko2_reliability']:.1f}%")
    print(f"Plot saved to: {aggregated_stats['plot_file']}")

    # Individual seed results
    print("\nResults by seed:")
    for i, stats in enumerate(all_stats):
        print(f"\nSeed {seeds[i]}:")
        print(f"Total votes: {stats['total_votes']}")
        print(f"Final calculated reliability: {stats['calc_reliability'][-1]:.1f}%")
        print(f"Final dynamic ELO reliability: {stats['elo_dynamic_reliability'][-1]:.1f}%")
        print(f"Final fixed ELO reliability: {stats['elo_fixed_reliability'][-1]:.1f}%")
        print(f"Final Glicko2 reliability: {stats['glicko2_reliability'][-1]:.1f}%")

    # Reliability Checkpoints Table
    print("\nReliability Checkpoints Averages:")
    print(f"{'Votes':<10} {'Calc':<10} {'Dynamic ELO':<15} {'Fixed ELO':<15} {'Glicko2':<10}")
    print("-" * 60)
    vote_data_points = aggregated_stats["votes_data"]
    calc_avg_checkpoints = aggregated_stats["avg_calc_reliability_checkpoints"]
    dynamic_avg_checkpoints = aggregated_stats["avg_elo_dynamic_reliability_checkpoints"]
    fixed_avg_checkpoints = aggregated_stats["avg_elo_fixed_reliability_checkpoints"]
    glicko2_avg_checkpoints = aggregated_stats["avg_glicko2_reliability_checkpoints"]

    for i, votes in enumerate(vote_data_points):
        print(f"{votes:<10} {calc_avg_checkpoints[i]:<10.1f} {dynamic_avg_checkpoints[i]:<15.1f} {fixed_avg_checkpoints[i]:<15.1f} {glicko2_avg_checkpoints[i]:<10.1f}")


    # Assert that average calculated reliability is high enough
    assert aggregated_stats["avg_final_calc_reliability"] >= 96, "Average calculated reliability never reached 96%"