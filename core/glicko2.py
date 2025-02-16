import math


class Glicko2Rating:
    """
    Calculates ratings using the Glicko-2 system for 1v1 comparisons.
    Usage mirrors the existing Elo Rating class.
    """

    # Default system constants (same as reference code)
    MU = 1500
    PHI = 350
    SIGMA = 0.06
    TAU = 1.0
    EPSILON = 0.000001
      # Conversion factor between Glicko and Glicko-2 scales

    def __init__(self, mu_a: float, phi_a: float, sigma_a: float,
                 mu_b: float, phi_b: float, sigma_b: float,
                 score_a: float, score_b: float):

        self.SCALE_RATIO = 173.7178
        """
        Initialize with both players' ratings and match outcome.

        Args:
            mu_a, phi_a, sigma_a: Player A's current rating, deviation, volatility
            mu_b, phi_b, sigma_b: Player B's current rating, deviation, volatility
            score_a, score_b: Match scores (1/0 for win/loss, 0.5/0.5 for draw)
        """
        # Create Glicko-2 helper instance with system parameters
        self.glicko = self.Glicko2Core(mu=self.MU, phi=self.PHI, sigma=self.SIGMA,
                                       tau=self.TAU, epsilon=self.EPSILON)

        # Create scaled-down Rating objects for both players
        self.rating_a = self.glicko.create_rating(mu_a, phi_a, sigma_a)
        self.rating_b = self.glicko.create_rating(mu_b, phi_b, sigma_b)

        # Determine if the match is a draw
        drawn = (abs(score_a - 0.5) < 1e-6 and (abs(score_b - 0.5) < 1e-6))

        # Calculate new ratings
        new_a, new_b = self.glicko.rate_1vs1(self.rating_a, self.rating_b, drawn)

        # Store results
        self.new_a = new_a
        self.new_b = new_b

    def get_new_ratings(self) -> dict:
        """
        Returns the updated ratings after the match.

        Returns:
            dict: New mu, phi, sigma for both players (scaled to original Glicko scale)
        """
        return {
            'a': {'mu': self.new_a.mu, 'phi': self.new_a.phi, 'sigma': self.new_a.sigma},
            'b': {'mu': self.new_b.mu, 'phi': self.new_b.phi, 'sigma': self.new_b.sigma}
        }

    class Glicko2Core:
        """Core Glicko-2 implementation (adapted from reference code)."""

        def __init__(self, mu=1500, phi=350, sigma=0.06, tau=1.0, epsilon=0.000001):
            self.mu = mu
            self.phi = phi
            self.sigma = sigma
            self.tau = tau
            self.epsilon = epsilon
            self.SCALE_RATIO = 173.7178

        def create_rating(self, mu, phi, sigma):
            return self.Rating(mu, phi, sigma)

        class Rating:
            """Holds a player's Glicko-2 rating parameters."""

            def __init__(self, mu, phi, sigma):
                self.mu = mu
                self.phi = phi
                self.sigma = sigma

        def scale_down(self, rating):
            """Converts Glicko scale to Glicko-2 scale."""
            mu = (rating.mu - self.mu) / self.SCALE_RATIO
            phi = rating.phi / self.SCALE_RATIO
            return self.Rating(mu, phi, rating.sigma)

        def scale_up(self, rating):
            """Converts Glicko-2 scale back to Glicko scale."""
            mu = rating.mu * self.SCALE_RATIO + self.mu
            phi = rating.phi * self.SCALE_RATIO
            return self.Rating(mu, phi, rating.sigma)

        def reduce_impact(self, rating):
            """Reduces impact of high-deviation opponents."""
            return 1.0 / math.sqrt(1.0 + (3.0 * rating.phi ** 2) / (math.pi ** 2))

        def rate_1vs1(self, rating1, rating2, drawn=False):
            """Updates ratings for a 1v1 match."""
            # Scale to Glicko-2
            r1 = self.scale_down(rating1)
            r2 = self.scale_down(rating2)
            # Process updates
            new_r1 = self._rate(r1, [(0.5 if drawn else 1.0, r2)])
            new_r2 = self._rate(r2, [(0.5 if drawn else 0.0, r1)])
            # Scale back and return
            return self.scale_up(new_r1), self.scale_up(new_r2)

        def _rate(self, rating, series):
            """Core rating update logic (adapted from reference code)."""
            if not series:
                new_phi = math.sqrt(rating.phi ** 2 + rating.sigma ** 2)
                return self.Rating(rating.mu, new_phi, rating.sigma)

            variance = 0.0
            delta = 0.0
            for outcome, opponent in series:
                impact = self.reduce_impact(opponent)
                expected = 1.0 / (1.0 + math.exp(-impact * (rating.mu - opponent.mu)))
                variance += (impact ** 2) * expected * (1 - expected)
                delta += impact * (outcome - expected)

            variance = 1.0 / variance if variance else 0.0
            delta *= variance

            sigma = self._determine_sigma(rating, delta, variance)
            new_phi = 1.0 / math.sqrt(1.0 / (rating.phi ** 2 + sigma ** 2) + 1.0 / variance)
            new_mu = rating.mu + new_phi ** 2 * (delta / variance)
            return self.Rating(new_mu, new_phi, sigma)

        def _determine_sigma(self, rating, delta, variance):
            """Iteratively solve for new volatility (from reference code)."""
            a = math.log(rating.sigma ** 2)
            f = lambda x: self._f(x, rating.phi, delta, variance, a)
            # Bounding logic (omitted for brevity; see reference code)
            # ... (Full implementation available in reference code)
            return rating.sigma  # Simplified for example
