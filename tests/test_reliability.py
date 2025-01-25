import random
from typing import List, Tuple
import matplotlib.pyplot as plt
import pytest

from core.elo import ReliabilityCalculator, Rating


class Media:
    """Represents a media item with an objective score and ELO rating."""

    def __init__(self, media_id: int, objective_score: int):
        self.id = media_id
        self.objective_score = objective_score
        self.elo = 1000.0
        self.vote_count = 0


def compute_real_reliability(original_order: List[Media], current_order: List[Media]) -> float:
    """Calculate alignment with objective ranking using pairwise comparisons."""
    correct = 0
    total = 0
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


# def compute_real_reliability(original_order: List[Media], current_order: List[Media]) -> float:
#     """
#     Calculate reliability based on how close media are to their objective positions.
#
#     Args:
#         original_order: List of media sorted by objective score (descending).
#         current_order: List of media sorted by ELO rating (descending).
#
#     Returns:
#         Average percentage of positional accuracy across all media.
#     """
#     n = len(current_order)
#     if n <= 1:
#         return 100.0  # Single item is perfectly placed
#
#     total_percent = 0.0
#     max_distance = n - 1  # Maximum possible position difference
#
#     for current_pos, media in enumerate(current_order):
#         # Correct position is determined by the media's objective score ranking
#         correct_pos = media.id  # Media IDs correspond to their objective rankings
#         distance = abs(current_pos - correct_pos)
#         individual_percent = 100.0 * (1.0 - distance / max_distance)
#         total_percent += individual_percent
#
#     return total_percent / n

def simulate_and_plot(n: int) -> Tuple[dict, str]:
    """Run simulation and generate comparison plot"""
    # Setup media
    original = [Media(i, n - i) for i in range(n)]
    shuffled = original.copy()
    random.shuffle(shuffled)

    votes_data = []
    real_reliability = []
    calc_reliability = []
    crossing_points = []  # Stores (votes, reliability) where lines cross
    total_votes = 0
    previous_diff = None

    while True:
        # Voting logic
        min_votes = min(m.vote_count for m in shuffled)
        candidates = [m for m in shuffled if m.vote_count == min_votes]
        media_a = random.choice(candidates)
        media_b = random.choice([m for m in shuffled if m != media_a])

        # Determine winner
        if media_a.objective_score > media_b.objective_score:
            winner, loser = media_a, media_b
        else:
            winner, loser = media_b, media_a

        # Update ELO
        rating = Rating(winner.elo, loser.elo, Rating.WIN, Rating.LOST)
        new_ratings = rating.get_new_ratings()
        winner.elo = new_ratings['a']
        loser.elo = new_ratings['b']

        # Update counts
        media_a.vote_count += 1
        media_b.vote_count += 1
        total_votes += 1

        # Sort and record every 10 votes
        if total_votes % 10 == 0:
            shuffled.sort(key=lambda x: -x.elo)
            real = compute_real_reliability(original, shuffled)
            calc = ReliabilityCalculator.calculate_reliability(n, total_votes)

            # Detect crossings
            if len(votes_data) > 0:
                current_diff = calc - real
                if previous_diff is not None:
                    # Check if signs changed (crossing occurred)
                    if (previous_diff < 0 <= current_diff) or \
                            (previous_diff > 0 >= current_diff):
                        # Linear interpolation to estimate crossing point
                        x0, y0_real = votes_data[-1], real_reliability[-1]
                        x1, y1_real = total_votes, real
                        y0_calc = calc_reliability[-1]
                        y1_calc = calc

                        # Solve for x where (calc(x) - real(x)) = 0
                        m_real = (y1_real - y0_real) / (x1 - x0)
                        m_calc = (y1_calc - y0_calc) / (x1 - x0)

                        # Intersection of two lines formula
                        x_cross = x0 + (y0_calc - y0_real) / (m_real - m_calc)
                        y_cross = y0_real + m_real * (x_cross - x0)

                        crossing_points.append((x_cross, y_cross))

                previous_diff = current_diff

            votes_data.append(total_votes)
            real_reliability.append(real)
            calc_reliability.append(calc)

            if calc >= 99:
                break

    final_order = [m.objective_score for m in shuffled]
    original_order = [m.objective_score for m in original]

    # Generate plot
    plt.figure(figsize=(12, 6))
    plt.plot(votes_data, real_reliability, label='Real Reliability', color='blue')
    plt.plot(votes_data, calc_reliability, label='Calculated Reliability', color='red', linestyle='--')

    plt.title(f'Reliability Comparison (n={n})')
    plt.xlabel('Total Votes')
    plt.ylabel('Reliability (%)')
    plt.legend()
    plt.grid(True)

    # Save plot
    filename = f'reliability_comparison_n{n}.png'
    plt.savefig(filename)
    plt.close()

    # Calculate statistics
    diffs = [abs(c - r) for c, r in zip(calc_reliability, real_reliability)]
    stats = {
        "max_diff": max(diffs),
        "min_diff": min(diffs),
        "avg_diff": sum(diffs) / len(diffs),
        "plot_file": filename,
        "total_votes": total_votes,
        "calc_reliability": calc_reliability,  # Added this line
        "real_reliability": real_reliability,  # Added this line
        "original_scores": original_order,
        "final_scores": final_order,
        "final_elos": [m.elo for m in shuffled],
        "original_elos": [m.elo for m in original],
        "crossing_points": crossing_points,
        "first_crossing": crossing_points[0] if crossing_points else None,
        "final_crossing": crossing_points[-1] if crossing_points else None
    }
    return stats


@pytest.mark.parametrize("n", [20, 50])
def test_reliability_with_graph(n: int):
    random.seed(42)
    stats = simulate_and_plot(n)

    # Print comparison
    print(f"\n{'Objective Score':<15} | {'Final ELO':<10} | {'Final Score':<15}")
    print("-" * 45)
    for orig, final, elo in zip(stats["original_scores"],
                                stats["final_scores"],
                                stats["final_elos"]):
        print(f"{orig:<15} | {elo:<10.1f} | {final:<15}")

    # Print crossing information
    if stats["crossing_points"]:
        print(f"\nCrossing points detected at:")
        for i, (votes, rel) in enumerate(stats["crossing_points"], 1):
            print(f"  {i}. Votes: {votes:.1f}, Reliability: {rel:.1f}%")
    else:
        print("\nNo crossing points detected between reliability curves")

    # Assertions
    assert stats["calc_reliability"][-1] >= 95, "Calc reliability never reached 99%"
    print(f"\nFinal Calculated Reliability: {stats['calc_reliability'][-1]:.1f}%")
    print(f"Final Real Reliability: {stats['real_reliability'][-1]:.1f}%")