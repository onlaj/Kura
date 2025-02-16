# core/elo.py
import math

import math

import math


class ReliabilityCalculator:
    """
    Provides improved reliability metrics for ELO-based ranking systems.

    The improved model uses a combination of:
    - Quick initial gains (logarithmic component)
    - Steady improvement (linear component)
    - Asymptotic approach to perfect reliability

    The formula is designed to match observed behavior of ELO and Glicko2 systems.
    """

    @staticmethod
    def calculate_reliability(n: int, v: int) -> float:
        """
        Calculate current reliability percentage of the ranking system.

        Args:
            n: Number of media items in the system (n > 0)
            v: Total number of votes cast (v >= 0)

        Returns:
            float: Reliability percentage between 0-100
        """
        if n <= 0 or v < 0:
            return 0.0

        # Start from 50% (random ordering)
        base_reliability = 50.0

        # Quick initial gains component
        votes_per_item = v / n
        initial_gain = 25.0 * (1 - math.exp(-votes_per_item / 2))

        # Steady improvement component
        steady_gain = 20.0 * (1 - math.exp(-votes_per_item / 10))

        # Asymptotic final approach
        final_gain = 5.0 * (1 - math.exp(-votes_per_item / 50))

        reliability = base_reliability + initial_gain + steady_gain + final_gain

        # Cap at 100%
        return min(100.0, reliability)

    @staticmethod
    def calculate_required_votes(n: int, target_reliability: float) -> int:
        """
        Calculate votes needed to reach a desired reliability level.

        Args:
            n: Number of media items in the system (n > 0)
            target_reliability: Desired reliability percentage (0 < R < 100)

        Returns:
            int: Minimum votes required (rounded up to nearest integer)
        """
        if n <= 0 or target_reliability <= 50 or target_reliability >= 100:
            return 0

        # Using binary search to find required votes
        low, high = 0, n * 1000
        while low < high:
            mid = (low + high) // 2
            reliability = ReliabilityCalculator.calculate_reliability(n, mid)

            if abs(reliability - target_reliability) < 0.1:
                return mid
            elif reliability < target_reliability:
                low = mid + 1
            else:
                high = mid - 1

        return low


class Rating:
    """
    Calculates ratings based on the ELO system used in chess.
    """

    KFACTOR = 16

    WIN = 1
    DRAW = 0.5
    LOST = 0

    def __init__(self, rating_a: float, rating_b: float, score_a: float, score_b: float, k_factor: int):
        """
        Initialize and calculate new ratings based on input scores.

        Args:
            rating_a: Current rating of player A
            rating_b: Current rating of player B
            score_a: Score of player A (1 for win, 0.5 for draw, 0 for loss)
            score_b: Score of player B (1 for win, 0.5 for draw, 0 for loss)
        """
        self.k_factor = k_factor
        self._rating_a = rating_a
        self._rating_b = rating_b
        self._score_a = score_a
        self._score_b = score_b

        expected_scores = self._get_expected_scores(self._rating_a, self._rating_b)
        self._expected_a = expected_scores['a']
        self._expected_b = expected_scores['b']

        new_ratings = self._get_new_ratings(
            self._rating_a, self._rating_b,
            self._expected_a, self._expected_b,
            self._score_a, self._score_b
        )
        self._new_rating_a = new_ratings['a']
        self._new_rating_b = new_ratings['b']

    def set_new_settings(self, rating_a: float, rating_b: float, score_a: float, score_b: float) -> 'Rating':
        """
        Update the rating calculator with new values.

        Args:
            rating_a: Current rating of player A
            rating_b: Current rating of player B
            score_a: Score of player A
            score_b: Score of player B

        Returns:
            self for method chaining
        """
        self.__init__(rating_a, rating_b, score_a, score_b)
        return self

    def get_new_ratings(self) -> dict:
        """
        Get the newly calculated ratings.

        Returns:
            Dictionary containing new ratings for both players
        """
        return {
            'a': self._new_rating_a,
            'b': self._new_rating_b
        }

    def _get_expected_scores(self, rating_a: float, rating_b: float) -> dict:
        """
        Calculate expected scores for both players.

        Args:
            rating_a: Rating of player A
            rating_b: Rating of player B

        Returns:
            Dictionary containing expected scores for both players
        """
        expected_score_a = 1 / (1 + (10 ** ((rating_b - rating_a) / 400)))
        expected_score_b = 1 / (1 + (10 ** ((rating_a - rating_b) / 400)))

        return {
            'a': expected_score_a,
            'b': expected_score_b
        }

    def _get_new_ratings(self, rating_a: float, rating_b: float,
                         expected_a: float, expected_b: float,
                         score_a: float, score_b: float) -> dict:
        """
        Calculate new ratings based on expected and actual scores.

        Args:
            rating_a: Current rating of player A
            rating_b: Current rating of player B
            expected_a: Expected score of player A
            expected_b: Expected score of player B
            score_a: Actual score of player A
            score_b: Actual score of player B

        Returns:
            Dictionary containing new ratings for both players
        """
        new_rating_a = rating_a + (self.k_factor * (score_a - expected_a))
        new_rating_b = rating_b + (self.k_factor * (score_b - expected_b))

        return {'a': new_rating_a, 'b': new_rating_b}