# GFSO Simulation Experiments

This directory contains the numerical validation for the **General Framework for Structural Optimization (GFSO)** paper.
These scripts verify the **Manifold Stability Hypothesis**: that structural validators act as contraction mappings, preventing the exponential error explosion typical of expansive stochastic agents (LLMs).

## Experiments

The simulations are unified in `sim_runner.py`, which executes two scenarios:

### 1. Scalar Stability (1D)
**Objective:** Visualize the stabilization effect in a scalar dynamic system.
*   **Physics:** $x_{t+1} = K(x_t) \cdot x_t + \text{Noise}$.
    *   $K=1.0$ (Stable) if $|x| < 2.0$.
    *   $K=1.2$ (Chaotic) if $|x| > 2.0$.
*   **Validator:** Checks $|x| < T$.
*   **Logic:** **Stall on Fail**. If validation fails $M$ times, the agent retains its previous state ($x_{t+1} = x_t$).
*   **Artifact:** `fig1_scalar_dynamics.png` (Shows >1000x gain due to ideal stalling).

### 2. Vector Robustness (100D)
**Objective:** Test robustness under the **Curse of Dimensionality** and **Partial Observability**.
*   **Space:** $\mathbb{R}^{100}$ (100 Dimensions).
*   **Validator:** **Noisy & Partial**. Only observes 10 dimensions (10%) with measurement noise ($\sigma=0.2$).
*   **Challenge:** Can a blind, drunk validator prevent chaos in 100 dimensions?
*   **Artifact:** `fig2_vector_robustness.png` (Shows ~600x gain despite blind spots).

## Usage

Run the unified simulation:

```bash
python sim_runner.py
```

## Artifacts
Outputs are saved to `artifacts/`:
*   `fig1_scalar_dynamics.png`: Figure 1 for the paper.
*   `fig2_vector_robustness.png`: Figure 2 for the paper.
