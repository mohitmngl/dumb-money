"""
Bayesian probability updating and Kelly Criterion position sizing for stock trading.

This module provides:
- Beta-Binomial conjugate Bayesian updating
- Wilson score confidence intervals
- Kelly Criterion optimal bet sizing
- Combined Bayesian stock scoring
"""

import numpy as np
from scipy import stats


class BetaPosterior:
    """Conjugate Beta-Binomial Bayesian updater for win rate estimation.

    Uses a Beta prior which, after observing wins and losses,
    yields a Beta posterior distribution for the true win probability.

    The Beta distribution is the conjugate prior for the Binomial likelihood,
    meaning the posterior is also a Beta distribution with updated parameters.
    """

    def __init__(self, alpha_prior=1, beta_prior=1):
        """Initialize with prior hyperparameters.

        Args:
            alpha_prior: Prior pseudo-count of successes (default 1 for uniform prior).
            beta_prior: Prior pseudo-count of failures (default 1 for uniform prior).

        Note:
            Alpha=1, Beta=1 gives a uniform prior over [0, 1].
            Higher values represent stronger prior beliefs.
        """
        self.alpha = alpha_prior
        self.beta = beta_prior

    def update(self, wins, losses):
        """Update posterior with observed wins and losses.

        Args:
            wins: Number of successful outcomes observed.
            losses: Number of failed outcomes observed.

        Returns:
            self: Allows method chaining.
        """
        self.alpha += wins
        self.beta += losses
        return self

    @property
    def mean(self):
        """Posterior mean probability (expected value of Beta distribution).

        Returns:
            float: The mean of the posterior Beta(alpha, beta) distribution,
                   computed as alpha / (alpha + beta).
        """
        return self.alpha / (self.alpha + self.beta)

    def credible_interval(self, level=0.95):
        """Compute the highest density credible interval.

        Uses scipy.stats.beta to compute the equal-tailed credible interval.

        Args:
            level: Credibility level (default 0.95 for 95% interval).

        Returns:
            tuple: (lower, upper) bounds of the credible interval.
        """
        tail = (1 - level) / 2
        lower = stats.beta.ppf(tail, self.alpha, self.beta)
        upper = stats.beta.ppf(1 - tail, self.alpha, self.beta)
        return (lower, upper)

    def sample(self, n=1000):
        """Draw samples from the posterior distribution.

        Args:
            n: Number of samples to draw (default 1000).

        Returns:
            numpy.ndarray: Array of n samples from Beta(alpha, beta).
        """
        return stats.beta.rvs(self.alpha, self.beta, size=n)


class WilsonScoreInterval:
    """Wilson score interval for binomial proportions.

    Provides a more accurate confidence interval for proportions than the
    normal approximation, especially for small sample sizes or extreme
    proportions near 0 or 1.
    """

    @staticmethod
    def compute(n_pos, n_total, z=1.96):
        """Compute the Wilson score lower bound for a binomial proportion.

        The Wilson score interval adjusts for sample size and provides
        better coverage than the Wald interval, particularly when
        np or n(1-p) is small.

        Args:
            n_pos: Number of positive outcomes.
            n_total: Total number of trials.
            z: Z-score for desired confidence level (default 1.96 for 95%).

        Returns:
            float: Lower bound of the Wilson score interval. Returns 0.5
                   when n_total is 0 (uninformative prior).

        Formula:
            (phat + z^2/(2n) - z*sqrt((phat*(1-phat) + z^2/(4n))/n)) / (1 + z^2/n)
        """
        if n_total == 0:
            return 0.5

        phat = n_pos / n_total
        n = n_total
        z_sq = z ** 2

        center = phat + z_sq / (2 * n)
        spread = np.sqrt((phat * (1 - phat) + z_sq / (4 * n)) / n)

        lower = (center - z * spread) / (1 + z_sq / n)
        return lower


class KellyCriterion:
    """Kelly Criterion for optimal position sizing.

    The Kelly Criterion determines the optimal fraction of capital to
    wager to maximize long-term geometric growth rate. It balances
    expected return against variance to find the growth-optimal bet size.
    """

    @staticmethod
    def fraction(win_prob, win_loss_ratio):
        """Compute the optimal Kelly fraction for position sizing.

        The Kelly fraction f* = (b*p - q) / b, where:
        - b = win_loss_ratio (average win / average loss)
        - p = win probability
        - q = 1 - p (loss probability)

        A positive fraction indicates a mathematical edge; negative
        means no edge and no bet should be placed.

        Args:
            win_prob: Probability of winning (p).
            win_loss_ratio: Ratio of average win to average loss (b).

        Returns:
            float: Optimal fraction of capital to risk, clamped to [0, 0.25].
                   Returns 0 if the expected value is negative (no edge).
                   Maximum of 25% to limit ruin risk from estimation error.
        """
        if win_loss_ratio <= 0:
            return 0.0

        p = win_prob
        q = 1 - p
        b = win_loss_ratio

        f_star = (b * p - q) / b

        if f_star <= 0:
            return 0.0

        return min(f_star, 0.25)

    @staticmethod
    def expected_growth(rate, win_prob, win_loss_ratio):
        """Compute the expected log growth rate (edge) for a given bet size.

        The growth rate is: p * log(1 + rate*b) + q * log(1 - rate),
        where b is the win/loss ratio and rate is the fraction wagered.

        This is the objective function that Kelly maximizes. A positive
        value indicates the bet has positive expected geometric growth.

        Args:
            rate: Fraction of capital to wager (f in Kelly notation).
            win_prob: Probability of winning (p).
            win_loss_ratio: Ratio of average win to average loss (b).

        Returns:
            float: Expected log growth rate. Negative values indicate
                   the bet destroys capital in expectation.
        """
        p = win_prob
        q = 1 - p
        b = win_loss_ratio

        if rate <= 0 or rate >= 1:
            return 0.0

        growth = p * np.log(1 + rate * b) + q * np.log(1 - rate)
        return float(growth)


def bayesian_stock_score(wins_1d, losses_1d, wins_5d, losses_5d,
                         current_price, stop_price):
    """Compute a combined Bayesian score for stock trading decisions.

    Integrates multiple statistical approaches:
    - Beta-Binomial posterior for 1-day and 5-day win rates
    - Wilson score lower bound for conservative 1-day estimate
    - Kelly Criterion for optimal position sizing using 5-day stats

    The combined score provides a single metric balancing historical
    win rates, statistical uncertainty, and position sizing theory.

    Args:
        wins_1d: Number of 1-day positive returns observed.
        losses_1d: Number of 1-day negative returns observed.
        wins_5d: Number of 5-day positive returns observed.
        losses_5d: Number of 5-day negative returns observed.
        current_price: Current stock price.
        stop_price: Stop-loss price for risk calculation.

    Returns:
        dict: Dictionary containing:
            - posterior_1d_mean: Bayesian 1-day win rate estimate
            - posterior_5d_mean: Bayesian 5-day win rate estimate
            - wilson_1d_lower: Conservative Wilson lower bound for 1-day
            - kelly_fraction: Optimal position size fraction
            - kelly_growth: Expected log growth rate
            - combined_score: Weighted composite score (0-1 scale)
    """
    posterior_1d = BetaPosterior()
    posterior_1d.update(wins_1d, losses_1d)
    posterior_1d_mean = posterior_1d.mean

    posterior_5d = BetaPosterior()
    posterior_5d.update(wins_5d, losses_5d)
    posterior_5d_mean = posterior_5d.mean

    total_1d = wins_1d + losses_1d
    wilson_1d_lower = WilsonScoreInterval.compute(wins_1d, total_1d)

    if current_price > 0 and stop_price > 0 and current_price > stop_price:
        avg_loss = current_price - stop_price
        avg_win = avg_loss
        win_loss_ratio = avg_win / avg_loss
    else:
        win_loss_ratio = 1.0

    kelly_fraction = KellyCriterion.fraction(posterior_5d_mean, win_loss_ratio)
    kelly_growth = KellyCriterion.expected_growth(
        kelly_fraction, posterior_5d_mean, win_loss_ratio
    )

    combined_score = (
        0.3 * posterior_1d_mean +
        0.3 * posterior_5d_mean +
        0.2 * wilson_1d_lower +
        0.2 * kelly_fraction
    )

    return {
        'posterior_1d_mean': posterior_1d_mean,
        'posterior_5d_mean': posterior_5d_mean,
        'wilson_1d_lower': wilson_1d_lower,
        'kelly_fraction': kelly_fraction,
        'kelly_growth': kelly_growth,
        'combined_score': combined_score
    }
