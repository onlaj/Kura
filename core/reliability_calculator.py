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
