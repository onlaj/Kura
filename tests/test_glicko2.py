import random
from typing import List, Tuple
import matplotlib.pyplot as plt
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


def simulate_and_plot(n: int) -> dict:
    """Run simulation using dynamic ELO, fixed ELO and Glicko2; generate plot and return stats."""
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

        # Record data every 10 votes
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

            # End simulation when calculated reliability reaches 99.8%
            if current_calc >= 96:
                break

    # Record final orderings (by objective score) according to each system’s rating
    final_order_dynamic = [m.objective_score for m in sorted(medias, key=lambda m: -m.elo)]
    final_order_fixed = [m.objective_score for m in sorted(medias, key=lambda m: -m.elo_fixed)]
    final_order_glicko2 = [m.objective_score for m in sorted(medias, key=lambda m: -m.glicko2["mu"])]

    # Generate plot with all curves
    plt.figure(figsize=(12, 6))
    plt.plot(votes_data, elo_dynamic_reliability, label="Dynamic ELO Reliability", color="blue")
    plt.plot(votes_data, elo_fixed_reliability, label="Fixed ELO Reliability", color="green")
    plt.plot(votes_data, glicko2_reliability, label="Glicko2 Reliability", color="orange")
    plt.plot(votes_data, calc_reliability_data, label="Calculated Reliability", color="red", linestyle="--")

    plt.title(f"Reliability Comparison (n={n})")
    plt.xlabel("Total Votes")
    plt.ylabel("Reliability (%)")
    plt.ylim(45, 100)  # Scale y-axis from 45% to 100%
    plt.legend()
    plt.grid(True)

    filename = f"reliability_comparison_n{n}.png"
    plt.savefig(filename)
    plt.close()

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


@pytest.mark.parametrize("n", [20, 50])
def test_reliability_with_graph(n: int):
    random.seed(42)
    stats = simulate_and_plot(n)

    # Print header for reliability checkpoints
    print("\nReliability checkpoints (every 10 votes):")
    header = f"{'Votes':>8} | {'Calc (%)':>9} | {'Dynamic ELO (%)':>15} | {'Fixed ELO (%)':>14} | {'Glicko2 (%)':>12}"
    print(header)
    print("-" * len(header))
    for i in range(len(stats["votes_data"])):
        print(f"{stats['votes_data'][i]:8} | {stats['calc_reliability'][i]:9.1f} | "
              f"{stats['elo_dynamic_reliability'][i]:15.1f} | {stats['elo_fixed_reliability'][i]:14.1f} | "
              f"{stats['glicko2_reliability'][i]:12.1f}")

    # Print crossing point information for each system
    for key, points in stats["crossing_points"].items():
        if points:
            print(f"\nCrossing points for {key.replace('_', ' ').title()}:")
            for i, (votes, rel) in enumerate(points, 1):
                print(f"  {i}. Votes: {votes:.1f}, Reliability: {rel:.1f}%")
        else:
            print(f"\nNo crossing points detected for {key.replace('_', ' ').title()}.")

    # Print final ordering information (objective scores) for each system
    print("\nFinal objective scores ordering:")
    print(" Dynamic ELO:", stats["final_order_dynamic"])
    print(" Fixed ELO:  ", stats["final_order_fixed"])
    print(" Glicko2:    ", stats["final_order_glicko2"])

    # Final ratings summary
    print(f"\nTotal votes: {stats['total_votes']}")
    print(f"Final Calculated Reliability: {stats['calc_reliability'][-1]:.1f}%")
    print(f"Final Dynamic ELO Reliability: {stats['elo_dynamic_reliability'][-1]:.1f}%")
    print(f"Final Fixed ELO Reliability:   {stats['elo_fixed_reliability'][-1]:.1f}%")
    print(f"Final Glicko2 Reliability:     {stats['glicko2_reliability'][-1]:.1f}%")
    print(f"Plot saved to: {stats['plot_file']}")

    # Assertions: Ensure the calculated reliability reached 99.8%
    assert stats["calc_reliability"][-1] >= 96, "Calculated reliability never reached 99.8%"
