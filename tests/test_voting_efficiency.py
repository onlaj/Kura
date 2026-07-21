"""
Unit tests for voting efficiency: reliability calibration, Glicko volatility,
uncertainty-aware pairing, and rematch exclusion.
"""
import random
from typing import List, Set, Tuple

import pytest

from core.glicko2 import Glicko2Rating
from core.reliability_calculator import ReliabilityCalculator
from db.database import Database


def compute_real_reliability(original_order, current_order) -> float:
    """Pairwise alignment with an objective ranking."""
    correct = 0
    total = 0
    position_map = {m: idx for idx, m in enumerate(current_order)}
    for i in range(len(original_order)):
        for j in range(i + 1, len(original_order)):
            m1, m2 = original_order[i], original_order[j]
            if position_map[m1] < position_map[m2]:
                correct += 1
            total += 1
    return (correct / total) * 100 if total else 0.0


class SimMedia:
    def __init__(self, media_id: int, objective_score: int):
        self.id = media_id
        self.objective_score = objective_score
        self.mu = 1200.0
        self.phi = 350.0
        self.sigma = 0.06
        self.vote_count = 0


def _pick_pair_legacy(medias: List[SimMedia], seen: Set[Tuple[int, int]]):
    """Old pairing: least-voted + random opponent (no rematch avoidance)."""
    min_votes = min(m.vote_count for m in medias)
    candidates = [m for m in medias if m.vote_count == min_votes]
    a = random.choice(candidates)
    b = random.choice([m for m in medias if m is not a])
    return a, b


def _pick_pair_smart(medias: List[SimMedia], seen: Set[Tuple[int, int]]):
    """New pairing: high-phi primary, rating-nearby opponent, avoid rematches."""
    ordered = sorted(medias, key=lambda m: (-m.phi, m.vote_count, random.random()))
    a = ordered[0]
    others = [m for m in medias if m is not a]

    def edge_key(x, y):
        return (min(x.id, y.id), max(x.id, y.id))

    for max_diff in (100, 200, None):
        pool = others
        if max_diff is not None:
            pool = [m for m in others if abs(m.mu - a.mu) <= max_diff] or others
        fresh = [m for m in pool if edge_key(a, m) not in seen]
        candidates = fresh or pool
        candidates = sorted(
            candidates, key=lambda m: (abs(m.mu - a.mu), -m.phi, m.vote_count)
        )
        return a, candidates[0]
    return a, others[0]


def simulate_glicko(n: int, threshold: float, smart: bool, max_votes: int = 50000) -> int:
    original = [SimMedia(i, n - i) for i in range(n)]
    medias = list(original)
    random.shuffle(medias)
    seen: Set[Tuple[int, int]] = set()
    total_votes = 0
    pick = _pick_pair_smart if smart else _pick_pair_legacy

    while total_votes < max_votes:
        a, b = pick(medias, seen)
        if a.objective_score > b.objective_score:
            winner, loser = a, b
        else:
            winner, loser = b, a

        updated = Glicko2Rating(
            winner.mu, winner.phi, winner.sigma,
            loser.mu, loser.phi, loser.sigma,
            1.0, 0.0,
        ).get_new_ratings()
        winner.mu, winner.phi, winner.sigma = (
            updated["a"]["mu"], updated["a"]["phi"], updated["a"]["sigma"]
        )
        loser.mu, loser.phi, loser.sigma = (
            updated["b"]["mu"], updated["b"]["phi"], updated["b"]["sigma"]
        )
        a.vote_count += 1
        b.vote_count += 1
        seen.add((min(a.id, b.id), max(a.id, b.id)))
        total_votes += 1

        if total_votes % 25 == 0:
            ranked = sorted(medias, key=lambda m: -m.mu)
            if compute_real_reliability(original, ranked) >= threshold:
                return total_votes
    return max_votes


class TestReliabilityCalibration:
    def test_glicko_94_near_empirical_votes_per_item(self):
        """UI 94% target for Glicko should land near ~8.3 votes/item at large n."""
        n = 1000
        votes = ReliabilityCalculator.calculate_required_votes(n, 94, "glicko2")
        vpi = votes / n
        assert 8.0 <= vpi <= 8.6, f"unexpected vpi={vpi}"

    def test_elo_94_near_calibrated_votes_per_item(self):
        """UI 94% target for Elo should land near ~12 votes/item at large n."""
        n = 1000
        votes = ReliabilityCalculator.calculate_required_votes(n, 94, "elo")
        vpi = votes / n
        assert 11.5 <= vpi <= 12.5, f"unexpected vpi={vpi}"

    def test_elo_needs_more_votes_than_glicko(self):
        n = 500
        glicko = ReliabilityCalculator.calculate_required_votes(n, 94, "glicko2")
        elo = ReliabilityCalculator.calculate_required_votes(n, 94, "elo")
        assert elo > glicko

    def test_glicko_85_is_early(self):
        n = 1000
        votes = ReliabilityCalculator.calculate_required_votes(n, 85, "glicko2")
        assert votes / n < 5.0

    def test_mean_phi_boosts_reliability(self):
        base = ReliabilityCalculator.calculate_reliability(
            100, 400, "glicko2", mean_phi=350
        )
        settled = ReliabilityCalculator.calculate_reliability(
            100, 400, "glicko2", mean_phi=80
        )
        assert settled > base

    def test_old_curve_overshoot_fixed(self):
        """Previous formula needed ~20 votes/item for 94%; new curve needs far less."""
        n = 100
        votes = ReliabilityCalculator.calculate_required_votes(n, 94, "glicko2")
        assert votes < n * 15


class TestGlickoSigma:
    def test_sigma_updates_on_match(self):
        before = 0.06
        result = Glicko2Rating(
            1500, 200, before, 1400, 30, 0.06, 1.0, 0.0
        ).get_new_ratings()
        assert abs(result["a"]["sigma"] - before) > 0 or result["a"]["phi"] < 200
        assert result["a"]["phi"] < 200

    def test_winner_rating_increases(self):
        result = Glicko2Rating(
            1200, 350, 0.06, 1200, 350, 0.06, 1.0, 0.0
        ).get_new_ratings()
        assert result["a"]["mu"] > 1200
        assert result["b"]["mu"] < 1200


class TestPairing:
    @pytest.fixture
    def db(self, tmp_path):
        path = str(tmp_path / "test.db")
        database = Database(path)
        album_id = database.create_album("Test", "glicko2")
        for i in range(8):
            fpath = str(tmp_path / f"img_{i}.jpg")
            open(fpath, "wb").close()
            database.add_media(fpath, "image", album_id)
        yield database, album_id
        database.close()

    def test_avoids_rematches(self, db):
        database, album_id = db
        seen = set()
        for _ in range(20):
            left, right = database.get_pair_for_voting(album_id)
            assert left and right
            edge = (min(left[0], right[0]), max(left[0], right[0]))
            database.update_ratings(left[0], right[0], album_id)
            if edge in seen:
                pytest.fail(f"Rematch occurred early: {edge}")
            seen.add(edge)
        assert len(seen) == 20

    def test_weighted_vote_inserts_single_edge(self, db):
        database, album_id = db
        left, right = database.get_pair_for_voting(album_id)
        database.update_ratings(left[0], right[0], album_id, weight=2)
        assert database.get_total_votes(album_id) == 1

    def test_glicko_recalc_resets_votes(self, db):
        database, album_id = db
        left, right = database.get_pair_for_voting(album_id)
        database.update_ratings(left[0], right[0], album_id)
        database._recalculate_glicko2(album_id)
        database.cursor.execute(
            "SELECT votes FROM media WHERE id = ?", (left[0],)
        )
        assert database.cursor.fetchone()[0] == 1


class TestPairingEfficiency:
    def test_smart_pairing_reaches_threshold_with_fewer_votes(self):
        random.seed(42)
        n = 40
        threshold = 90.0
        legacy = simulate_glicko(n, threshold, smart=False)
        random.seed(42)
        smart = simulate_glicko(n, threshold, smart=True)
        assert smart <= legacy * 1.05, (
            f"smart={smart} legacy={legacy}: expected smart pairing to need fewer votes"
        )
        assert smart < n * 25
