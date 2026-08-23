"""2-state Gaussian Hidden Markov Model for market regime detection.

This is a standalone math module implementing a two-state HMM (bear / bull)
with Gaussian emissions. All forward-backward, Viterbi and scoring math is
done in LOG SPACE using :func:`scipy.special.logsumexp` for numerical stability.

States:
    0 = bear regime
    1 = bull regime
"""

import numpy as np
from scipy.special import logsumexp


def _logsumexp(a, axis=None):
    """Wrapper around scipy.special.logsumexp for convenience."""
    return logsumexp(a, axis=axis)


class GaussianHMM2State:
    """A 2-state Gaussian HMM with MAP estimation via Baum-Welch EM.

    States are ordered ``[bear, bull]`` (0 = bear, 1 = bull). Emissions are
    independent univariate Gaussians per state with parameters ``mu`` and
    ``sigma``.

    Parameters
    ----------
    transition_prior : array-like, shape (2, 2), optional
        Dirichlet pseudo-counts for the transition matrix rows. Default is
        ``[[2, 1], [1, 2]]`` which encodes mild persistence (states tend to
        stay the same).
    mu_prior : array-like, shape (2,), optional
        Prior means for the emissions. Default ``[0.001, -0.001]`` gives a
        slight bull/bear bias (bull mean slightly positive, bear negative).
    sigma_prior : array-like, shape (2,), optional
        Prior standard deviations for the emissions. Default ``[0.02, 0.03]``
        treats the bear regime as more volatile than the bull regime.
    """

    N = 2  # number of hidden states

    def __init__(self, transition_prior=None, mu_prior=None, sigma_prior=None):
        if transition_prior is None:
            transition_prior = np.array([[2.0, 1.0], [1.0, 2.0]])
        else:
            transition_prior = np.asarray(transition_prior, dtype=float)
            if transition_prior.shape != (2, 2):
                raise ValueError("transition_prior must be shape (2, 2)")

        if mu_prior is None:
            mu_prior = np.array([0.001, -0.001])
        else:
            mu_prior = np.asarray(mu_prior, dtype=float)
            if mu_prior.shape != (2,):
                raise ValueError("mu_prior must be shape (2,)")

        if sigma_prior is None:
            sigma_prior = np.array([0.02, 0.03])
        else:
            sigma_prior = np.asarray(sigma_prior, dtype=float)
            if sigma_prior.shape != (2,):
                raise ValueError("sigma_prior must be shape (2,)")

        self.transition_prior = transition_prior
        self.mu_prior = mu_prior
        self.sigma_prior = sigma_prior

        # Emission stds are stored as variance internally for the NIG prior
        self.sigma_prior2 = sigma_prior ** 2

        # Parameters (initialized to priors until fit is called)
        self.transmat = self._normalize_rows(
            transition_prior + np.eye(2)
        )
        self.mu = mu_prior.copy()
        self.sigma = sigma_prior.copy()

        self.log_likelihood_history = []

    @staticmethod
    def _normalize_rows(m):
        """Row-normalize a matrix so each row sums to 1."""
        m = np.asarray(m, dtype=float)
        row_sums = m.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        return m / row_sums

    @staticmethod
    def _log_gaussian_pdf(x, mu, sigma):
        """Log-density of a univariate Gaussian evaluated elementwise.

        ``x`` is array-like (timesteps,), ``mu`` and ``sigma`` are scalars or
        arrays broadcastable to ``x``. ``sigma`` is a standard deviation.
        """
        sigma = np.maximum(sigma, 1e-6)
        var = sigma ** 2
        log_norm = -0.5 * (np.log(2.0 * np.pi) + np.log(var))
        log_kernel = -0.5 * ((x - mu) ** 2) / var
        return log_norm + log_kernel

    def _emission_logprob(self, returns):
        """Log emission probabilities ``B[t, i]`` for returns[t] in state i."""
        returns = np.asarray(returns, dtype=float)
        B = np.empty((returns.shape[0], self.N))
        for i in range(self.N):
            B[:, i] = self._log_gaussian_pdf(returns, self.mu[i], self.sigma[i])
        return B

    # ------------------------------------------------------------------
    # Forward-backward (log space)
    # ------------------------------------------------------------------
    def _forward_backward(self, returns, B):
        """Run forward-backward in log space.

        Returns
        -------
        log_likelihood : float
        gamma : ndarray (T, 2)             state responsibilities
        xi : ndarray (T-1, 2, 2)           transition responsibilities
        """
        T = returns.shape[0]
        log_A = np.log(self.transmat)
        B = np.asarray(B, dtype=float)

        # Uniform starting distribution over states.
        log_pi = np.log(np.ones(self.N) / self.N)

        # ---- Forward pass (scaled in log space) ----
        log_alpha = np.empty((T, self.N))
        log_alpha[0] = log_pi + B[0]
        # normalize at each step to prevent underflow
        log_c = np.empty(T)
        log_c[0] = logsumexp(log_alpha[0])
        log_alpha[0] = log_alpha[0] - log_c[0]

        for t in range(1, T):
            # logsumexp over previous states weighted by transition probs
            m = log_alpha[t - 1][:, None] + log_A  # (i, j)
            fwd = logsumexp(m, axis=0) + B[t]
            log_c[t] = logsumexp(fwd)
            log_alpha[t] = fwd - log_c[t]

        log_likelihood = float(log_c.sum())

        # ---- Backward pass (scaled in log space) ----
        log_beta = np.empty((T, self.N))
        log_beta[T - 1] = 0.0  # log(1)

        for t in range(T - 2, -1, -1):
            m = log_A + (B[t + 1] + log_beta[t + 1])[None, :]  # (i, j)
            bwd = logsumexp(m, axis=1) - log_c[t + 1]
            log_beta[t] = bwd

        # ---- Gamma (state responsibilities) ----
        gamma = log_alpha + log_beta
        gamma = gamma - logsumexp(gamma, axis=1, keepdims=True)
        gamma = np.exp(gamma)

        # ---- Xi (transition responsibilities) ----
        xi = np.empty((T - 1, self.N, self.N))
        for t in range(T - 1):
            m = (
                log_alpha[t][:, None]
                + log_A
                + B[t + 1][None, :]
                + log_beta[t + 1][None, :]
            )
            m = m - log_likelihood  # undo normalization -> full joint
            xi[t] = np.exp(m)

        return log_likelihood, gamma, xi

    # ------------------------------------------------------------------
    # Baum-Welch EM
    # ------------------------------------------------------------------
    def fit(self, returns, max_iter=100, tol=1e-6):
        """Fit the model to ``returns`` with Baum-Welch EM (MAP).

        Parameters
        ----------
        returns : array-like
            Per-period returns (e.g. log returns).
        max_iter : int
            Maximum number of EM iterations.
        tol : float
            Stop when the absolute log-likelihood improvement is below this.

        Returns
        -------
        self
        """
        returns = np.asarray(returns, dtype=float)
        T = returns.shape[0]
        if T < 2:
            raise ValueError("Need at least 2 observations to fit")

        self.log_likelihood_history = []

        for it in range(max_iter):
            B = self._emission_logprob(returns)
            log_likelihood, gamma, xi = self._forward_backward(returns, B)
            self.log_likelihood_history.append(log_likelihood)

            # ---- M-step with priors (MAP) ----
            # Transition matrix with Dirichlet pseudo-counts per row.
            trans_counts = xi.sum(axis=0)  # (2, 2)
            trans_counts = trans_counts + self.transition_prior
            self.transmat = self._normalize_rows(trans_counts)

            # Emission means (Normal prior) and variances (Inverse-Gamma prior)
            w = gamma  # (T, 2) responsibilities
            w_sum = w.sum(axis=0)  # (2,)

            for i in range(self.N):
                w_i = w[:, i]
                s = w_sum[i]
                # MAP mean: weighted average shrunk toward prior mean.
                if s > 0:
                    mu_new = (w_i * returns).sum() / s
                else:
                    mu_new = self.mu_prior[i]
                # shrink toward prior (equivalent to adding prior pseudo-mass)
                k_prior = 1.0  # prior strength for mean
                self.mu[i] = (s * mu_new + k_prior * self.mu_prior[i]) / (s + k_prior)

                # MAP variance: Inverse-Gamma with prior variance as scale.
                if s > 0:
                    var_new = (w_i * (returns - self.mu[i]) ** 2).sum() / s
                else:
                    var_new = self.sigma_prior2[i]
                # prior pseudo-observations nu with mean = prior variance
                nu_prior = 1.0
                var_map = (s * var_new + nu_prior * self.sigma_prior2[i]) / (s + nu_prior)
                self.sigma[i] = np.sqrt(max(var_map, 1e-12))

            # Floor stds to avoid division by zero.
            self.sigma = np.maximum(self.sigma, 1e-6)

            if it >= 1:
                improvement = log_likelihood - self.log_likelihood_history[-2]
                if improvement < tol:
                    break

        return self

    # ------------------------------------------------------------------
    # Viterbi decode
    # ------------------------------------------------------------------
    def predict(self, returns):
        """Return the most likely state sequence via Viterbi.

        Parameters
        ----------
        returns : array-like

        Returns
        -------
        states : ndarray (T,) of int (0=bear, 1=bull)
        """
        returns = np.asarray(returns, dtype=float)
        T = returns.shape[0]
        B = self._emission_logprob(returns)
        log_A = np.log(self.transmat)
        log_pi = np.log(np.ones(self.N) / self.N)

        log_delta = np.empty((T, self.N))
        psi = np.zeros((T, self.N), dtype=int)

        log_delta[0] = log_pi + B[0]
        for t in range(1, T):
            # for each current state j, best previous state i
            m = log_delta[t - 1][:, None] + log_A  # (i, j)
            psi[t] = np.argmax(m, axis=0)
            log_delta[t] = m[psi[t], np.arange(self.N)] + B[t]

        states = np.empty(T, dtype=int)
        states[T - 1] = int(np.argmax(log_delta[T - 1]))
        for t in range(T - 2, -1, -1):
            states[t] = psi[t + 1, states[t + 1]]

        return states

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def score(self, returns):
        """Log-likelihood of ``returns`` under the forward algorithm.

        Returns
        -------
        float
        """
        returns = np.asarray(returns, dtype=float)
        B = self._emission_logprob(returns)
        log_likelihood, _, _ = self._forward_backward(returns, B)
        return float(log_likelihood)


def detect_regime(close_prices, lookback=60):
    """Convenience wrapper to detect a bull/bear regime from prices.

    Parameters
    ----------
    close_prices : array-like
        Closing prices in chronological order.
    lookback : int
        Number of trailing returns used to FIT the HMM. The model is then
        used to decode the full return series.

    Returns
    -------
    dict with keys:
        'regimes' : ndarray (T,) of int (0=bear, 1=bull)
        'current_regime' : 'bull' or 'bear'
        'regime_duration' : int (length of the current run at the end)
        'bull_probability' : float (gamma at final timestep, state 1)
        'log_likelihood' : float (score of the full series)
    """
    close_prices = np.asarray(close_prices, dtype=float)
    if close_prices.shape[0] < 2:
        raise ValueError("Need at least 2 close prices")

    # Log returns.
    returns = np.diff(np.log(close_prices))
    if returns.shape[0] == 0:
        raise ValueError("Not enough prices to compute returns")

    n = returns.shape[0]
    fit_window = returns[-lookback:] if n > lookback else returns

    model = GaussianHMM2State()
    model.fit(fit_window)

    regimes = model.predict(returns)
    ll = model.score(returns)

    current_state = int(regimes[-1])
    current_regime = "bull" if current_state == 1 else "bear"

    # Regime duration: how long the final run has persisted.
    duration = 1
    for t in range(regimes.shape[0] - 2, -1, -1):
        if regimes[t] == current_state:
            duration += 1
        else:
            break

    # Bull probability from a forward-backward pass on the full series.
    B = model._emission_logprob(returns)
    _, gamma, _ = model._forward_backward(returns, B)
    bull_probability = float(gamma[-1, 1])

    return {
        "regimes": regimes,
        "current_regime": current_regime,
        "regime_duration": int(duration),
        "bull_probability": bull_probability,
        "log_likelihood": ll,
    }
