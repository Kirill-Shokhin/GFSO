import numpy as np
import matplotlib.pyplot as plt
import os
from scipy.ndimage import gaussian_filter1d

# --- GLOBAL CONFIGURATION ---
OUTPUT_DIR = "gfso/experiments/theory_sim/artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)
SEED = 42

class UnifiedManifoldSimulator:
    def __init__(self, seed=SEED):
        np.random.seed(seed)
        
    def get_dynamics(self, x, safe_margin, k_stable=1.0, k_chaos=1.2):
        """
        Manifold Hypothesis:
        - Inside Safe Margin (Norm < M): Stable (K=1.0)
        - Outside Safe Margin (Norm > M): Chaos (K=1.2)
        """
        norm = np.linalg.norm(x)
        if norm < safe_margin:
            return k_stable
        else:
            return k_chaos

    def step_agent(self, x, dynamics_k, noise_std):
        """
        Agent Step: x_{t+1} = K(x_t) * x_t + Noise
        """
        expanded = x * dynamics_k
        noise = np.random.normal(0, noise_std, size=x.shape)
        return expanded + noise

    def validate_step(self, x_current, proposal, val_dims, threshold, val_noise_std):
        """
        Validation Logic with Measurement Noise.
        """
        view = proposal[:val_dims]
        meas_noise = np.random.normal(0, val_noise_std, size=view.shape)
        perceived_view = view + meas_noise
        limit = threshold * np.sqrt(val_dims)
        return np.linalg.norm(perceived_view) <= limit

    def run_simulation(self, n_steps, n_trials, dim, val_dim, 
                       safe_margin, noise_std, val_noise_std, 
                       threshold, max_retries, mode='naive'):
        """
        Runs the simulation.
        """
        errors = np.zeros((n_trials, n_steps))
        
        for i in range(n_trials):
            # Start with small noise (not absolute zero)
            x = np.random.normal(0, 0.1, size=dim)
            
            for t in range(n_steps):
                errors[i, t] = np.linalg.norm(x)
                
                k = self.get_dynamics(x, safe_margin)
                proposal = self.step_agent(x, k, noise_std)
                
                if mode == 'naive':
                    x = proposal
                else:
                    # GFSO Logic: Retry Loop
                    accepted = False
                    curr_attempt = proposal
                    
                    for _ in range(max_retries):
                        if self.validate_step(x, curr_attempt, val_dim, threshold, val_noise_std):
                            x = curr_attempt
                            accepted = True
                            break
                        else:
                            curr_attempt = self.step_agent(x, k, noise_std)
                    
                    if not accepted:
                        # Fallback: DAMPENING (Organic Compromise)
                        # Instead of Stall, we blend the bad proposal with the current state.
                        # This allows drift to accumulate slowly (realistic friction).
                        x = 0.9 * x + 0.1 * curr_attempt

        return errors

# --- PLOTTING UTILS ---
def plot_journal_style(filename, steps, data_map, safe_margin, annotation_text=None):
    plt.rcParams['figure.facecolor'] = 'white'
    plt.figure(figsize=(10, 6))
    
    SIGMA = 1.5
    
    for label, props in data_map.items():
        data = props['data']
        color = props['color']
        
        median = gaussian_filter1d(np.median(data, axis=0), sigma=SIGMA)
        plt.plot(steps, median, color=color, linewidth=2.5, linestyle=props.get('style', '-'), label=label)
        
        # Fill
        if props.get('fill', False):
            p10 = gaussian_filter1d(np.percentile(data, 10, axis=0), sigma=SIGMA)
            p90 = gaussian_filter1d(np.percentile(data, 90, axis=0), sigma=SIGMA)
            plt.fill_between(steps, p10, p90, color=color, alpha=0.1)

    c_safe = '#2980B9'
    plt.axhline(y=safe_margin, color=c_safe, linestyle='--', linewidth=1.5, alpha=0.7)
    plt.text(1, safe_margin*1.2, 'Stability Boundary (K=1.0)', color=c_safe, fontsize=11, fontweight='bold')

    plt.yscale('log')
    plt.xlabel('Composition Depth (Steps)', fontsize=13)
    plt.ylabel('Global Error ($W_1$ / $L_2$)', fontsize=13)
    plt.legend(loc='upper left', fontsize=10, frameon=True, facecolor='white')
    
    plt.grid(True, which="major", ls="-", alpha=0.15, color='black') 
    plt.gca().tick_params(which='minor', left=True)
    for spine in plt.gca().spines.values():
        if spine.spine_type in ['top', 'right']:
            spine.set_visible(False)
            
    if annotation_text:
        last_step = steps[-1]
        vals = [np.median(d['data'], axis=0)[-1] for d in data_map.values()]
        min_val = min(vals)
        plt.annotate(annotation_text, 
                 xy=(last_step, min_val), 
                 xytext=(last_step-20, min_val*10),
                 arrowprops=dict(arrowstyle="->", color='black', connectionstyle="arc3,rad=.2"),
                 fontsize=11, fontweight='bold', color='#B7950B')

    out_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Saved {out_path}")


# --- RUNNERS ---

def run_experiment_1_scalar():
    print("\n--- Running Experiment 1: Scalar Dynamics (1D) ---")
    sim = UnifiedManifoldSimulator()
    
    # Params
    N_STEPS = 50
    N_TRIALS = 1000
    DIM = 1
    VAL_DIM = 1
    
    SAFE_MARGIN = 2.0
    NOISE = 0.5
    VAL_NOISE = 0.2
    
    # RELAXED Threshold for Organic Behavior
    THRESHOLD = 1.0  
    RETRIES = 10
    
    err_naive = sim.run_simulation(N_STEPS, N_TRIALS, DIM, VAL_DIM, SAFE_MARGIN, NOISE, VAL_NOISE, THRESHOLD, RETRIES, 'naive')
    err_gfso = sim.run_simulation(N_STEPS, N_TRIALS, DIM, VAL_DIM, SAFE_MARGIN, NOISE, VAL_NOISE, THRESHOLD, RETRIES, 'gfso')
    
    print(f"Naive Final: {np.mean(err_naive[:,-1]):.2f}")
    print(f"GFSO Final:  {np.mean(err_gfso[:,-1]):.2f}")
    
    data = {
        'Standard Chain': {'data': err_naive, 'color': '#D35400', 'fill': True},
        'GFSO Protected': {'data': err_gfso,  'color': '#1E8449', 'fill': True}
    }
    gain = np.mean(err_naive[:,-1]) / (np.mean(err_gfso[:,-1]) + 1e-9)
    plot_journal_style("fig1_scalar_dynamics.png", np.arange(N_STEPS), data, SAFE_MARGIN, f"{gain:.0f}x Stability Gain")

def run_experiment_2_vector():
    print("\n--- Running Experiment 2: Vector Robustness (100D) ---")
    sim = UnifiedManifoldSimulator()
    
    # Params
    N_STEPS = 50
    N_TRIALS = 1000
    DIM = 100
    VAL_DIM = 10 
    
    SAFE_MARGIN = 15.0 
    NOISE = 0.5
    VAL_NOISE = 0.2
    
    # RELAXED Threshold for Organic Behavior
    THRESHOLD = 1.0 
    RETRIES = 10
    
    err_naive = sim.run_simulation(N_STEPS, N_TRIALS, DIM, VAL_DIM, SAFE_MARGIN, NOISE, VAL_NOISE, THRESHOLD, RETRIES, 'naive')
    err_full = sim.run_simulation(N_STEPS, N_TRIALS, DIM, DIM, SAFE_MARGIN, NOISE, VAL_NOISE, THRESHOLD, RETRIES, 'gfso')
    err_partial = sim.run_simulation(N_STEPS, N_TRIALS, DIM, VAL_DIM, SAFE_MARGIN, NOISE, VAL_NOISE, THRESHOLD, RETRIES, 'gfso')
    
    print(f"Naive Final:   {np.mean(err_naive[:,-1]):.2f}")
    print(f"Full Final:    {np.mean(err_full[:,-1]):.2f}")
    print(f"Partial Final: {np.mean(err_partial[:,-1]):.2f}")
    
    # Plot
    data = {
        'Baseline (Unconstrained)': {'data': err_naive, 'color': '#D35400', 'fill': True},
        'Partial (Noisy 10%)':      {'data': err_partial, 'color': '#F1C40F', 'style': '--', 'fill': True},
        'Full Validation':          {'data': err_full, 'color': '#1E8449', 'fill': True}
    }
    gain = np.mean(err_naive[:,-1]) / np.mean(err_partial[:,-1])
    plot_journal_style("fig2_vector_robustness.png", np.arange(N_STEPS), data, SAFE_MARGIN, f"{gain:.0f}x Robustness Gain")

if __name__ == "__main__":
    run_experiment_1_scalar()
    run_experiment_2_vector()
