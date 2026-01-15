"""
GFSO Experimental Validation: L * gamma <= 1
Exp 1: Phase transition (Prop 5.2b: Ideal Scaling)
Exp 2: Partial observation (Prop 5.2: Truncation + Fallback)
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter1d
from dataclasses import dataclass
from typing import Optional, Callable
import os

OUTPUT_DIR = "experiments/artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)


@dataclass
class Config:
    n_steps: int = 50
    n_trials: int = 1000
    dim: int = 100
    noise_std: float = 0.5
    L: float = 1.2
    seed: int = 42


def simulate(cfg: Config, validator: Optional[Callable] = None) -> np.ndarray:
    """E_{n+1} = L * E_n + noise, with optional validator."""
    np.random.seed(cfg.seed)
    errors = np.zeros((cfg.n_trials, cfg.n_steps))
    for trial in range(cfg.n_trials):
        x = np.zeros(cfg.dim)
        for t in range(cfg.n_steps):
            proposal = cfg.L * x + np.random.normal(0, cfg.noise_std, cfg.dim)
            x = validator(x, proposal) if validator else proposal
            errors[trial, t] = np.linalg.norm(x)
    return errors


# Validators

def ideal_scaling(gamma: float):
    """
    Pure scaling: V(p) = gamma * p.
    Implements Proposition 5.2b (Deterministic Contraction).
    Used to validate the Stability Criterion L * gamma <= 1.
    """
    def v(x, p): return gamma * p
    return v


def rejection_with_fallback(obs_dims: Optional[int], cfg: Config, threshold: float = 1.0,
                            noise: float = 0.2, retries: int = 10, bias_correction: bool = False):
    """
    Realistic validator implementing Proposition 5.2 (Truncation) with Partial Observation.

    Mechanism:
    1. Observe random subset of dimensions.
    2. Check threshold (Truncation) — PRIMARY contraction mechanism.
    3. If fail: Retry (Resampling).
    4. If all retries fail: Interpolate towards previous state (Fallback safety net).

    Note: Fallback (0.8*x + 0.2*p) does NOT provide contraction (L_eff = 1.04 > 1 for L=1.2).
    It bounds step size to prevent unbounded growth. Stability comes from successful rejections.
    """
    def v(x, p):
        dim = len(p)
        od = obs_dims or dim
        
        # Bias Correction (Conceptual placeholder for asymmetric distributions)
        if bias_correction:
            p = p - np.mean(p) # Simple centering

        for _ in range(retries):
            idx = np.random.choice(dim, od, replace=False)
            # Measurement with observation noise
            measured_norm = np.linalg.norm(p[idx] + np.random.normal(0, noise, od))
            # Scale threshold by sqrt(d_obs/d_total)
            if measured_norm <= threshold * np.sqrt(od):
                return p
            
            # Resample: generating a new proposal from the implementation F
            p = cfg.L * x + np.random.normal(0, cfg.noise_std, dim)
            
        # Fallback: Interpolate towards previous state if rejection fails
        # Bounds step size: ||x_new - x|| = 0.2||p - x||, limiting divergence rate
        return 0.8 * x + 0.2 * p
    return v


def run_and_plot(title: str, cases: list, cfg: Config, filename: str):
    """Run experiment cases and plot results."""
    print(f"\n{'='*60}\n{title}\n{'='*60}")

    results = []
    for name, validator, color, style in cases:
        print(f"Running: {name}...")
        data = simulate(cfg, validator)
        results.append((name, data, color, style))
        print(f"  Mean error @ n=50: {np.mean(data[:,-1]):.2f}")

    # Plot
    plt.figure(figsize=(10, 6))
    for name, data, color, style in results:
        mean = gaussian_filter1d(np.mean(data, axis=0), 1.5)
        std = gaussian_filter1d(np.std(data, axis=0), 1.5)
        label = name.replace("Lg=", r"$L \cdot \gamma=$")
        plt.plot(mean, color=color, ls=style, lw=2.5, label=label)
        plt.fill_between(range(cfg.n_steps), mean - std, mean + std, color=color, alpha=0.1)

    plt.yscale('log')
    plt.xlabel('Composition Depth (n)', fontsize=13)
    plt.ylabel('Error $E_n$ ($W_1$ distance)', fontsize=13)
    plt.legend(loc='upper left', fontsize=10)
    plt.grid(True, alpha=0.15)
    for s in ['top', 'right']: plt.gca().spines[s].set_visible(False)

    path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved: {path}")


if __name__ == "__main__":
    cfg = Config()
    L = cfg.L

    # Experiment 1: Phase Transition (Prop 5.2b)
    run_and_plot("Phase Transition at L*gamma = 1", [
        ("Naive (No Validator)", None, '#D35400', '-'),
        (f"Supercritical (Lg={L*0.9:.2f})", ideal_scaling(0.9), '#E67E22', '--'),
        (f"Critical (Lg={1.0:.2f})", ideal_scaling(1/L), '#F1C40F', '-.'),
        (f"Subcritical (Lg={L*0.75:.2f})", ideal_scaling(0.75), '#1E8449', '-'),
    ], cfg, "fig1_theory_validation.png")

    # Experiment 2: Partial Observation (Prop 5.2)
    run_and_plot("Partial Observation Robustness", [
        ("Baseline (Unconstrained)", None, '#D35400', '-'),
        ("Partial (10/100 dims)", rejection_with_fallback(10, cfg), '#F1C40F', '--'),
        ("Full (100/100 dims)", rejection_with_fallback(None, cfg), '#1E8449', '-'),
    ], cfg, "fig2_realistic_scenario.png")

    print(f"\n{'='*60}\nCOMPLETE\n{'='*60}")