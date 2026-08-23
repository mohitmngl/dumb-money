import os
import numpy as np
import jax.numpy as jnp
from intraday_backtest.config import BASE_DIR

BATCH_CACHE_DIR = os.path.join(BASE_DIR, "batch_cache")


def ensure_cache_dir():
    os.makedirs(BATCH_CACHE_DIR, exist_ok=True)


def generate_batches(n_batches, n_stocks, seed=42):
    """Generate batch weight matrix: (n_batches, n_stocks).
    Each row has exactly 10 non-zero entries: 5 long (+0.1) and 5 short (-0.1).
    Fully vectorized numpy for speed. Saves to disk as .npy for reuse."""
    ensure_cache_dir()
    cache_path = os.path.join(BATCH_CACHE_DIR, f"batches_{n_batches}_{n_stocks}_{seed}.npy")

    if os.path.exists(cache_path):
        W = np.load(cache_path)
        if W.shape == (n_batches, n_stocks):
            return jnp.array(W, dtype=jnp.float32)

    rng = np.random.default_rng(seed)
    W = np.zeros((n_batches, n_stocks), dtype=np.float32)

    # Generate all batch stock selections at once
    # Use argsort trick: generate random scores, take top 10 per batch
    scores = rng.random((n_batches, n_stocks), dtype=np.float32)
    stock_indices = np.argpartition(scores, 10, axis=1)[:, :10]  # (n_batches, 10)

    # Assign exactly 5 long and 5 short per batch using rank-based selection
    flip = rng.random((n_batches, 10), dtype=np.float32)
    sorted_idx = np.argsort(flip, axis=1)
    long_mask = np.zeros((n_batches, 10), dtype=bool)
    batch_range = np.arange(n_batches)[:, None]
    long_mask[batch_range, sorted_idx[:, :5]] = True
    short_mask = ~long_mask

    batch_idx = np.arange(n_batches)[:, None]

    long_rows = np.broadcast_to(batch_idx, (n_batches, 10))[long_mask]
    long_cols = stock_indices[long_mask]
    short_rows = np.broadcast_to(batch_idx, (n_batches, 10))[short_mask]
    short_cols = stock_indices[short_mask]

    W[long_rows, long_cols] = 0.1
    W[short_rows, short_cols] = -0.1

    np.save(cache_path, W)
    return jnp.array(W, dtype=jnp.float32)


def load_batches(n_batches, n_stocks, seed=42):
    """Load cached batches or generate if not found."""
    ensure_cache_dir()
    cache_path = os.path.join(BATCH_CACHE_DIR, f"batches_{n_batches}_{n_stocks}_{seed}.npy")

    if os.path.exists(cache_path):
        W = np.load(cache_path)
        if W.shape == (n_batches, n_stocks):
            return jnp.array(W, dtype=jnp.float32)

    return generate_batches(n_batches, n_stocks, seed)
