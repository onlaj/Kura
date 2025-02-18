import random
from typing import List, Dict, Tuple
import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm


# [Previous Media and compute_real_reliability classes remain the same]
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

    for i in range(len(original_order)):
        for j in range(i + 1, len(original_order)):
            m1 = original_order[i]
            m2 = original_order[j]
            if position_map[m1] < position_map[m2]:
                correct += 1
            total += 1

    return (correct / total) * 100 if total > 0 else 0.0


def simulate_until_threshold(n: int, threshold: float, max_votes: int = 100000) -> int:
    """Run simulation until reaching reliability threshold or max votes."""
    original = [Media(i, n - i) for i in range(n)]
    medias = original.copy()
    random.shuffle(medias)

    total_votes = 0

    while total_votes < max_votes:
        # Select media_a from least voted
        min_votes = min(m.vote_count for m in medias)
        candidates = [m for m in medias if m.vote_count == min_votes]
        media_a = random.choice(candidates)

        # Select media_b
        media_b = random.choice([m for m in medias if m != media_a])

        # Determine winner based on objective score
        if media_a.objective_score > media_b.objective_score:
            winner, loser = media_a, media_b
        else:
            winner, loser = media_b, media_a

        # Update ELO ratings
        k_factor = 32
        expected_a = 1 / (1 + 10 ** ((loser.elo - winner.elo) / 400))
        winner.elo += k_factor * (1 - expected_a)
        loser.elo += k_factor * (0 - (1 - expected_a))

        # Update vote counts
        media_a.vote_count += 1
        media_b.vote_count += 1
        total_votes += 1

        # Check reliability every 50 votes
        if total_votes % 50 == 0:
            sorted_medias = sorted(medias, key=lambda x: -x.elo)
            real_reliability = compute_real_reliability(original, sorted_medias)
            if real_reliability >= threshold:
                return total_votes

    return max_votes  # If threshold not reached


def test_reliability_scaling():
    # Test parameters
    n_values = [10, 20, 50, 100, 200, 350, 500, 750, 1000]
    thresholds = [85, 93]
    seeds = [42, 123, 456, 508, 749, 862]  # Multiple seeds for averaging
    results: Dict[float, List[Tuple[int, int]]] = {threshold: [] for threshold in thresholds}

    # Run simulations
    for threshold in thresholds:
        print(f"\nSimulating for {threshold}% threshold:")
        for n in tqdm(n_values):
            votes_needed = []
            for seed in seeds:
                random.seed(seed)
                votes = simulate_until_threshold(n, threshold)
                votes_needed.append(votes)
            avg_votes = int(np.mean(votes_needed))
            results[threshold].append((n, avg_votes))

    # Create plot
    plt.figure(figsize=(12, 8))
    colors = ['blue', 'red']
    markers = ['o', 's']

    for threshold, color, marker in zip(thresholds, colors, markers):
        n_list = [r[0] for r in results[threshold]]
        votes_list = [r[1] for r in results[threshold]]

        # Plot scatter points
        plt.scatter(n_list, votes_list, color=color, marker=marker,
                    label=f'{threshold}% Threshold (measured)', zorder=3)

        # Fit polynomial regression
        z = np.polyfit(n_list, votes_list, 2)
        p = np.poly1d(z)
        x_smooth = np.linspace(min(n_list), max(n_list), 100)
        plt.plot(x_smooth, p(x_smooth), color=color, linestyle='--',
                 label=f'{threshold}% Threshold (trend line)', zorder=2)

    plt.grid(True, zorder=1)
    plt.xlabel('Number of Media Items')
    plt.ylabel('Votes Required')
    plt.title('Votes Required to Reach Reliability Threshold vs. Number of Media Items')
    plt.legend()

    # Format axis to use regular numbers instead of scientific notation
    plt.gca().xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
    plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))


    # Save plot
    filename = 'reliability_scaling.png'
    plt.savefig(filename, bbox_inches='tight', dpi=300)
    plt.close()

    # Print detailed results
    print("\nDetailed Results:")
    print(f"{'Media Items':<12} {'85% Votes':<12} {'93% Votes':<12}")
    print("-" * 36)
    for i in range(len(n_values)):
        n = n_values[i]
        votes_85 = results[85][i][1]
        votes_93 = results[93][i][1]
        print(f"{n:<12} {votes_85:<12} {votes_93:<12}")


if __name__ == "__main__":
    test_reliability_scaling()