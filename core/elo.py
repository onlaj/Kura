# core/elo.py

class Rating:
    """
    Calculates ratings based on the ELO system used in chess.
    """

    KFACTOR = 16

    WIN = 1
    DRAW = 0.5
    LOST = 0

    def __init__(self, rating_a: float, rating_b: float, score_a: float, score_b: float):
        """
        Initialize and calculate new ratings based on input scores.

        Args:
            rating_a: Current rating of player A
            rating_b: Current rating of player B
            score_a: Score of player A (1 for win, 0.5 for draw, 0 for loss)
            score_b: Score of player B (1 for win, 0.5 for draw, 0 for loss)
        """
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
        new_rating_a = rating_a + (self.KFACTOR * (score_a - expected_a))
        new_rating_b = rating_b + (self.KFACTOR * (score_b - expected_b))

        return {
            'a': new_rating_a,
            'b': new_rating_b
        }