import math
from typing import Optional


class ReliabilityCalculator:
    """
    Reliability metrics calibrated to empirical Elo / Glicko-2 convergence.

    The vote-density curve is fitted so that Glicko albums reach ~94% near
    ~8.3 votes per item (matching docs/reliability_thresholds.md), while Elo
    albums need a denser vote history (~12 votes/item at large n).

    For Glicko albums, mean residual rating deviation (phi) can advance the
    estimate further once uncertainty has actually collapsed.
    """

    # Glicko RD (phi) at init and a "well-settled" target used for blending
    PHI_INIT = 350.0
    PHI_SETTLED = 80.0

    @staticmethod
    def calculate_reliability(
        n: int,
        v: int,
        rating_system: str = "glicko2",
        mean_phi: Optional[float] = None,
    ) -> float:
        """
        Calculate current reliability percentage of the ranking system.

        Args:
            n: Number of media items (n > 0)
            v: Total number of votes cast (v >= 0)
            rating_system: 'glicko2' (default) or 'elo'
            mean_phi: Optional average Glicko RD for the album; used only for
                      Glicko albums to blend uncertainty into the estimate

        Returns:
            float: Reliability percentage between 0-100
        """
        if n <= 0 or v < 0:
            return 0.0

        votes_per_item = v / n
        # Elo converges more slowly in the empirical tables — stretch the
        # effective density so the same UI targets require more votes.
        if rating_system == "elo":
            votes_per_item *= 0.70

        # Calibrated three-phase model (Glicko ~94% near 8.3 votes/item):
        #  - quick early gains
        #  - mid-stage sorting
        #  - asymptotic refinement
        base_reliability = 50.0
        initial_gain = 26.0 * (1 - math.exp(-votes_per_item / 1.2))
        steady_gain = 17.0 * (1 - math.exp(-votes_per_item / 4.0))
        final_gain = 7.0 * (1 - math.exp(-votes_per_item / 14.0))

        reliability = base_reliability + initial_gain + steady_gain + final_gain

        if rating_system != "elo" and mean_phi is not None:
            reliability = ReliabilityCalculator._blend_phi(reliability, mean_phi)

        return min(100.0, reliability)

    @staticmethod
    def _blend_phi(vote_reliability: float, mean_phi: float) -> float:
        """Pull reliability up as average Glicko RD falls toward settled values."""
        span = ReliabilityCalculator.PHI_INIT - ReliabilityCalculator.PHI_SETTLED
        if span <= 0:
            return vote_reliability
        phi_confidence = max(
            0.0,
            min(1.0, (ReliabilityCalculator.PHI_INIT - mean_phi) / span),
        )
        # Up to ~12% of the remaining gap to 100% can come from low RD
        remaining = 100.0 - vote_reliability
        return vote_reliability + remaining * 0.12 * phi_confidence

    @staticmethod
    def calculate_required_votes(
        n: int,
        target_reliability: float,
        rating_system: str = "glicko2",
        mean_phi: Optional[float] = None,
    ) -> int:
        """
        Calculate votes needed to reach a desired reliability level.

        Args:
            n: Number of media items (n > 0)
            target_reliability: Desired reliability percentage (0 < R < 100)
            rating_system: 'glicko2' or 'elo'
            mean_phi: Optional average Glicko RD (assumed constant while searching)

        Returns:
            int: Minimum votes required
        """
        if n <= 0 or target_reliability <= 50 or target_reliability >= 100:
            return 0

        low, high = 0, n * 1000
        while low < high:
            mid = (low + high) // 2
            reliability = ReliabilityCalculator.calculate_reliability(
                n, mid, rating_system=rating_system, mean_phi=mean_phi
            )

            if abs(reliability - target_reliability) < 0.1:
                return mid
            elif reliability < target_reliability:
                low = mid + 1
            else:
                high = mid - 1

        return low
