import random
from typing import List, Dict, Tuple
import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm
from core.elo import Rating
from core.glicko2 import Glicko2Rating


class Media:
    """Represents a media item with an objective score and multiple ratings."""

    def __init__(self, media_id: int, objective_score: int):
        self.id = media_id
        self.objective_score = objective_score
        self.elo = 1000.0
        self.glicko2 = {"mu": 1200.0, "phi": 350.0, "sigma": 0.06}
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


def simulate_until_threshold(n: int, threshold: float, max_votes: int = 100000) -> dict:
    """Run simulation until reaching reliability threshold or max votes."""
    original = [Media(i, n - i) for i in range(n)]
    medias = original.copy()
    random.shuffle(medias)

    total_votes = 0
    elo_reached = None
    glicko_reached = None

    while total_votes < max_votes and (elo_reached is None or glicko_reached is None):
        # Select media_a from least voted
        min_votes = min(m.vote_count for m in medias)
        candidates = [m for m in medias if m.vote_count == min_votes]
        media_a = random.choice(candidates)
        media_b = random.choice([m for m in medias if m != media_a])

        # Determine winner based on objective score
        if media_a.objective_score > media_b.objective_score:
            winner, loser = media_a, media_b
        else:
            winner, loser = media_b, media_a

        # Update ELO ratings
        rating = Rating(winner.elo, loser.elo, Rating.WIN, Rating.LOST, 32)
        new_ratings = rating.get_new_ratings()
        winner.elo = new_ratings['a']
        loser.elo = new_ratings['b']

        # Update Glicko2 ratings
        new_glicko = Glicko2Rating(
            winner.glicko2["mu"], winner.glicko2["phi"], winner.glicko2["sigma"],
            loser.glicko2["mu"], loser.glicko2["phi"], loser.glicko2["sigma"],
            1, 0
        ).get_new_ratings()
        winner.glicko2 = new_glicko["a"]
        loser.glicko2 = new_glicko["b"]

        # Update vote counts
        media_a.vote_count += 1
        media_b.vote_count += 1
        total_votes += 1

        # Check reliability every 50 votes
        if total_votes % 50 == 0:
            # Check ELO reliability
            if elo_reached is None:
                sorted_elo = sorted(medias, key=lambda x: -x.elo)
                elo_reliability = compute_real_reliability(original, sorted_elo)
                if elo_reliability >= threshold:
                    elo_reached = total_votes

            # Check Glicko2 reliability
            if glicko_reached is None:
                sorted_glicko = sorted(medias, key=lambda x: -x.glicko2["mu"])
                glicko_reliability = compute_real_reliability(original, sorted_glicko)
                if glicko_reliability >= threshold:
                    glicko_reached = total_votes

    return {
        "elo_votes": elo_reached if elo_reached is not None else max_votes,
        "glicko_votes": glicko_reached if glicko_reached is not None else max_votes
    }


def test_reliability_scaling():
    # Test parameters
    n_values = [10, 20, 50, 100, 200, 500, 1000]
    thresholds = [85, 93]
    seeds = [42, 123, 456]  # Multiple seeds for averaging

    # Initialize results dictionary
    results = {
        (threshold, system): [] for threshold in thresholds
        for system in ['elo', 'glicko2']
    }

    # Run simulations
    for threshold in thresholds:
        print(f"\nSimulating for {threshold}% threshold:")
        for n in tqdm(n_values):
            elo_votes = []
            glicko_votes = []
            for seed in seeds:
                random.seed(seed)
                sim_results = simulate_until_threshold(n, threshold)
                elo_votes.append(sim_results["elo_votes"])
                glicko_votes.append(sim_results["glicko_votes"])

            results[(threshold, 'elo')].append((n, int(np.mean(elo_votes))))
            results[(threshold, 'glicko2')].append((n, int(np.mean(glicko_votes))))

    # Create plot
    plt.figure(figsize=(12, 8))
    colors = {
        (85, 'elo'): 'blue',
        (85, 'glicko2'): 'green',
        (93, 'elo'): 'red',
        (93, 'glicko2'): 'purple'
    }
    markers = {
        (85, 'elo'): 'o',
        (85, 'glicko2'): 's',
        (93, 'elo'): '^',
        (93, 'glicko2'): 'D'
    }

    for (threshold, system), color in colors.items():
        n_list = [r[0] for r in results[(threshold, system)]]
        votes_list = [r[1] for r in results[(threshold, system)]]

        # Plot scatter points
        label = f'{threshold}% {system.upper()} (measured)'
        plt.scatter(n_list, votes_list, color=color,
                    marker=markers[(threshold, system)],
                    label=label, zorder=3)

        # Fit polynomial regression
        z = np.polyfit(n_list, votes_list, 2)
        p = np.poly1d(z)
        x_smooth = np.linspace(min(n_list), max(n_list), 100)
        plt.plot(x_smooth, p(x_smooth), color=color, linestyle='--',
                 label=f'{threshold}% {system.upper()} (trend line)', zorder=2)

    plt.grid(True, zorder=1)
    plt.xlabel('Number of Media Items')
    plt.ylabel('Votes Required')
    plt.title('Votes Required to Reach Reliability Threshold vs. Number of Media Items')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

    # Format axis to use regular numbers instead of scientific notation
    plt.gca().xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
    plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))


    # Save plot
    filename = '../docs/reliability_scaling_comparison.png'
    plt.savefig(filename, bbox_inches='tight', dpi=300)
    plt.close()

    # Print detailed results
    print("\nDetailed Results:")
    print(f"{'Media Items':<12} {'ELO 85%':<12} {'Glicko2 85%':<12} {'ELO 93%':<12} {'Glicko2 93%':<12}")
    print("-" * 65)
    for i in range(len(n_values)):
        n = n_values[i]
        elo_85 = results[(85, 'elo')][i][1]
        glicko_85 = results[(85, 'glicko2')][i][1]
        elo_93 = results[(93, 'elo')][i][1]
        glicko_93 = results[(93, 'glicko2')][i][1]
        print(f"{n:<12} {elo_85:<12} {glicko_85:<12} {elo_93:<12} {glicko_93:<12}")


if __name__ == "__main__":
    test_reliability_scaling()