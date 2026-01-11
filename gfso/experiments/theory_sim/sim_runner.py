import numpy as np
import matplotlib.pyplot as plt
import os
import pandas as pd
from scipy import stats
from scipy.ndimage import gaussian_filter1d

# --- CONFIGURATION (MANIFOLD STABILITY) ---
SEED = 42
N_STEPS = 50
N_TRIALS = 1000
NOISE_STD = 0.5       # Sigma_A
VALIDATOR_NOISE = 0.2 # Sigma_V
THRESHOLD = 0.3       # T (Tighter control)
MAX_RETRIES = 10      # M

# --- PHYSICS OF THE SYSTEM ---
# The system is stable (L=1.0) as long as error is small.
# If error exceeds SAFE_MARGIN, the system enters "Hallucination/Crisis Mode" (L > 1).
SAFE_MARGIN = 2.0     
K_STABLE = 1.0
K_CHAOS = 1.2         # Exponential divergence factor

OUTPUT_DIR = "gfso/experiments/theory_sim/artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

class ManifoldSimulator:
    def __init__(self, seed=SEED):
        np.random.seed(seed)
        
    def get_dynamics(self, current_val, ideal_val):
        """
        State-Dependent Dynamics.
        If the agent deviates too far from 'truth' (ideal_val), it becomes chaotic.
        """
        error = np.abs(current_val - ideal_val)
        if error < SAFE_MARGIN:
            return K_STABLE
        else:
            return K_CHAOS

    def validate_step(self, ideal_next_val, noise_std, val_noise_std, threshold, max_retries):
        """
        Tries to produce a value close to ideal_next_val.
        """
        for i in range(max_retries):
            proposal = ideal_next_val + np.random.normal(0, noise_std)
            meas_noise = np.random.normal(0, val_noise_std)
            dist = np.abs((proposal - ideal_next_val) + meas_noise)
            
            if dist <= threshold:
                return proposal, i + 1
        
        return proposal, max_retries

    def run_chain(self, n_steps, n_trials, mode='naive'):
        """
        Runs the simulation. 
        """
        errors = np.zeros((n_trials, n_steps))
        
        for i in range(n_trials):
            x = 0.0 # Current state (deviation from truth) 
            
            for t in range(n_steps):
                errors[i, t] = np.abs(x)
                
                # 1. Determine local expansiveness based on current error
                k_curr = self.get_dynamics(x, 0.0)
                
                # 2. Compute "Next Expected State" by the agent
                expected_next_x = k_curr * x
                
                # 3. Step
                if mode == 'naive':
                    x = expected_next_x + np.random.normal(0, NOISE_STD)
                else:
                    x, _ = self.validate_step(expected_next_x, NOISE_STD, VALIDATOR_NOISE, THRESHOLD, MAX_RETRIES)

        return errors

def plot_marketing_visual(steps, err_naive, err_gfso, safe_margin):
    """
    Generates a 'Journal-Ready' visualization.
    - White background, no title.
    - High contrast for PDF printing.
    """
    plt.rcParams['figure.facecolor'] = 'white'
    plt.figure(figsize=(10, 6))
    
    # Calculate Statistics with Smoothing
    SIGMA = 1.5
    naive_median = gaussian_filter1d(np.median(err_naive, axis=0), sigma=SIGMA)
    naive_p10 = gaussian_filter1d(np.percentile(err_naive, 10, axis=0), sigma=SIGMA)
    naive_p90 = gaussian_filter1d(np.percentile(err_naive, 90, axis=0), sigma=SIGMA)
    
    gfso_median = gaussian_filter1d(np.median(err_gfso, axis=0), sigma=SIGMA)
    gfso_p10 = gaussian_filter1d(np.percentile(err_gfso, 10, axis=0), sigma=SIGMA)
    gfso_p90 = gaussian_filter1d(np.percentile(err_gfso, 90, axis=0), sigma=SIGMA)
    
    # Colors
    c_naive = '#D35400' # Burnt Orange (better for print)
    c_gfso = '#1E8449'  # Dark Green
    c_safe = '#2E86C1'  # Steel Blue
    
    # Plot Naive
    plt.plot(steps, naive_median, color=c_naive, linewidth=2.5, label='Standard Chain (Median)')
    plt.fill_between(steps, naive_p10, naive_p90, color=c_naive, alpha=0.1, label='Naive 10-90% Range')
    
    # Plot GFSO
    plt.plot(steps, gfso_median, color=c_gfso, linewidth=2.5, label='GFSO Protected (Median)')
    plt.fill_between(steps, gfso_p10, gfso_p90, color=c_gfso, alpha=0.15, label='GFSO 10-90% Range')
    
    # Plot Safe Margin
    plt.axhline(y=safe_margin, color=c_safe, linestyle='--', linewidth=1.5, alpha=0.7)
    plt.text(1, safe_margin*1.2, 'Stability Boundary (K=1.0)', color=c_safe, fontsize=11, fontweight='bold')
    
    # Annotations
    final_ratio = naive_median[-1] / (gfso_median[-1] + 1e-9)
    plt.annotate(f'{final_ratio:.0f}x Stability Gain', 
                 xy=(steps[-1], gfso_median[-1]), 
                 xytext=(steps[-1]-18, gfso_median[-1]*20),
                 arrowprops=dict(arrowstyle="->", color='black', connectionstyle="arc3,rad=.2"),
                 fontsize=12, fontweight='bold')

    # Formatting
    plt.yscale('log')
    plt.xlabel('Composition Depth (Steps)', fontsize=13)
    plt.ylabel('Semantic Drift ($W_1$ Error)', fontsize=13)
    plt.legend(loc='upper left', fontsize=10, frameon=True, facecolor='white')
    
    # Clean Grid: Only major lines, very subtle
    plt.grid(True, which="major", ls="-", alpha=0.15, color='black') 
    plt.gca().tick_params(which='minor', left=True) # Ticks only for minor, no lines
    
    plt.xlim(0, steps[-1])
    
    # Remove top and right spines
    for spine in plt.gca().spines.values():
        if spine.spine_type in ['top', 'right']:
            spine.set_visible(False)
    
    # Save
    out_path = os.path.join(OUTPUT_DIR, "gfso_impact_v2.png")
    plt.savefig(out_path, dpi=300, bbox_inches='tight', transparent=False)
    print(f"Journal-style Plot saved to {out_path}")

def run_experiment():
    sim = ManifoldSimulator()
    print(f"Running Manifold Stability Experiment (N={N_TRIALS}, Steps={N_STEPS})...")
    print(f"Physics: Stable inside +/-{SAFE_MARGIN}, Chaos (K={K_CHAOS}) outside.")
    
    # Run Naive
    err_naive = sim.run_chain(N_STEPS, N_TRIALS, mode='naive')
    
    # Run GFSO
    err_gfso = sim.run_chain(N_STEPS, N_TRIALS, mode='gfso')
    
    # Analyze Mean (for text report consistency with previous run)
    mean_naive = np.mean(err_naive, axis=0)
    mean_gfso = np.mean(err_gfso, axis=0)
    
    # Count "Survival Rate" (Trials that stayed within SAFE_MARGIN * 5)
    limit = SAFE_MARGIN * 5.0 
    fail_naive = np.sum(err_naive[:, -1] > limit)
    fail_gfso = np.sum(err_gfso[:, -1] > limit)
    
    print(f"\nResults at Step {N_STEPS}:")
    print(f"Naive Mean Error: {mean_naive[-1]:.2f}")
    print(f"GFSO Mean Error:  {mean_gfso[-1]:.2f}")
    
    # Plot Standard (Raw)
    steps = np.arange(N_STEPS)
    plt.figure(figsize=(12, 6))
    plt.plot(steps, mean_naive, 'r-', linewidth=3, label='Naive (Mean)')
    plt.plot(steps, mean_gfso, 'g-', linewidth=3, label='GFSO (Mean)')
    plt.axhline(y=SAFE_MARGIN, color='b', linestyle='--', label='Stability Boundary')
    plt.title(f'Manifold Stability Analysis (Raw Means)')
    plt.legend()
    out_path = os.path.join(OUTPUT_DIR, "manifold_stability.png")
    plt.savefig(out_path)
    print(f"Standard Plot saved to {out_path}")
    
    # --- MARKETING VISUALIZATION (High Impact) ---
    plot_marketing_visual(steps, err_naive, err_gfso, SAFE_MARGIN)
    
    # Generate Report
    report = f"""
    GFSO MANIFOLD STABILITY REPORT
    ==============================
    Model: State-Dependent Dynamics (The "Edge of Chaos" Hypothesis)
    Results (N={N_TRIALS}, Steps={N_STEPS}):
    ----------------------------------------
    Naive Mean Error: {mean_naive[-1]:.2f}
    GFSO Mean Error:  {mean_gfso[-1]:.2f}
    Improvement:      {mean_naive[-1] / mean_gfso[-1]:.2f}x
    
    Failure Rate (Drift > {limit}):
    - Naive: {fail_naive/N_TRIALS*100:.1f}% collapsed.
    - GFSO:  {fail_gfso/N_TRIALS*100:.1f}% collapsed.
    """
    
    with open(os.path.join(OUTPUT_DIR, "validation_report.txt"), "w") as f:
        f.write(report)

if __name__ == "__main__":
    run_experiment()
