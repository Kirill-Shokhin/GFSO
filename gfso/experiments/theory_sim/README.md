# Experiment: Error Propagation in Expansive Systems

**Objective:** Validate Theorem 3.1 (Linear Bound) and Theorem 3.2 (Soft Validation) using a controlled stochastic process.
**Paper Section:** 5. Empirical Validation

## 1. Mathematical Setup

We simulate a discrete dynamical system:
$$x_{t+1} = f(x_t)$$
where the ideal function is **expansive**:
$$f_{ideal}(x) = 1.1 \cdot x \quad (\text{Lipschitz } L=1.1)$$

### The Stochastic Agent (F)
The implementation introduces Gaussian noise at each step:
$$x_{t+1} = 1.1 \cdot x_t + \mathcal{N}(0, 0.5)$$

### The Validator (\eta)
We compare the agent's output $x_{real}$ against the ideal projection $x_{ideal}$.
*   **Threshold:** $T = 0.2$
*   **Retry Limit:** $M = 5$

## 2. Baselines

1.  **Naive Chain:** No validation. Error accumulates as $\sum L^{N-i} \xi_i$. Expected growth: **Exponential**.
2.  **GFSO Strict:** Hard cutoff if error > T.
3.  **GFSO Soft:** Soft rejection probability (Theorem 3.2).

## 3. Metric
We measure the **Mean Absolute Error (MAE)** between the simulated trajectory and the ideal trajectory over $K=1000$ runs for chain length $N 
in [1, 20]$.

## 4. Expected Outcome
*   **Naive:** Curve should look like $y = e^x$.
*   **GFSO:** Curve should look like $y = ax + b$ (Linear) or saturation.
