"""
GFSO Predictive Experiment

Correct measurement methodology:
- L = d(F(x1), F(x2)) / d(x1, x2)  -- morphism expansion on input PAIRS
- gamma: ONE input x, TWO runs y1=F(x), y2=F(x), ONE target x
         gamma = d(V(y1), V(y2)) / d(y1, y2)
         This measures if validator CONTRACTS distance between outputs

Three scenarios:
- A: Strong validator -> L*gamma < 1 -> VERIFIED (bounded errors)
- B: No validator (gamma=1) -> L*gamma = L -> NOT VERIFIED (if L > 1)
- C: Weak validator -> L*gamma ~ 1 -> BORDERLINE
"""

import os
import json
import time
import numpy as np
import matplotlib.pyplot as plt

import anthropic
from sentence_transformers import SentenceTransformer

OUTPUT_DIR = "experiments/artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Embedding model for stable distance
EMBED_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
REQUEST_DELAY = 1.2


class LLM:
    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not key:
            raise ValueError("Set ANTHROPIC_API_KEY or CLAUDE_API_KEY")
        self.client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.calls = 0

    def __call__(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        time.sleep(REQUEST_DELAY)
        self.calls += 1
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()


def semantic_distance(t1: str, t2: str) -> float:
    """1 - cosine_similarity of embeddings."""
    if t1 == t2:
        return 0.0
    e1, e2 = EMBED_MODEL.encode([t1, t2])
    cos_sim = np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2))
    return 1.0 - cos_sim


def morphism(llm: LLM, text: str) -> str:
    """F: paraphrase morphism."""
    prompt = f"""Paraphrase this text in a different style.
Keep the core meaning but change wording and structure.

Text: {text}

Paraphrased:"""
    return llm(prompt, temperature=0.7)


def validator_strong(llm: LLM, source: str, text: str) -> str:
    """V_strong: strict correction to source."""
    prompt = f"""Correct this text to accurately match the source.
Fix any errors or omissions. Be faithful to the source.

Source: {source}

Text to correct: {text}

Corrected:"""
    return llm(prompt, temperature=0.2)


def validator_weak(llm: LLM, source: str, text: str) -> str:
    """V_weak: light correction."""
    prompt = f"""Lightly review this text. Fix obvious errors only.

Reference: {source[:500]}

Text: {text}

Reviewed:"""
    return llm(prompt, temperature=0.5)


def validator_none(llm: LLM, source: str, text: str) -> str:
    """V_none: identity (gamma = 1)."""
    return text


def load_input_pairs():
    """Load pairs of different inputs for L and gamma measurement."""
    try:
        with open("data/halueval_summarization.json", encoding='utf-8') as f:
            data = [json.loads(line) for i, line in enumerate(f) if i < 6]
        # Use documents as inputs, create pairs
        texts = [d["document"][:1000] for d in data]
    except:
        texts = [
            "The Renaissance began in Italy in the 14th century. It marked renewed interest in classical culture. Key figures included Leonardo da Vinci and Michelangelo.",
            "Machine learning enables systems to learn from data. Common approaches include supervised and unsupervised learning. Neural networks have achieved remarkable success.",
            "Climate change refers to long-term shifts in temperatures. Human activities have been the main driver since the 1800s. Effects include rising sea levels and extreme weather.",
            "The human brain contains approximately 86 billion neurons. These cells communicate through electrical and chemical signals. The brain controls all body functions.",
        ]

    # Create pairs: (x1, x2) where x1 ≠ x2
    pairs = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            pairs.append((texts[i], texts[j]))
    return pairs[:5]  # Limit to 5 pairs


def measure_L(llm: LLM, pairs: list) -> tuple:
    """
    Measure Lipschitz constant L of morphism F.
    L = max d(F(x₁), F(x₂)) / d(x₁, x₂)
    """
    print("\nMeasuring L (morphism expansion)...")
    ratios = []

    for i, (x1, x2) in enumerate(pairs):
        d_in = semantic_distance(x1, x2)
        if d_in < 0.01:
            continue

        y1 = morphism(llm, x1)
        y2 = morphism(llm, x2)
        d_out = semantic_distance(y1, y2)

        ratio = d_out / d_in
        ratios.append(ratio)
        print(f"  Pair {i+1}: d_in={d_in:.3f}, d_out={d_out:.3f}, L={ratio:.3f}")

    L_max = max(ratios) if ratios else 1.0
    L_mean = np.mean(ratios) if ratios else 1.0
    L_std = np.std(ratios) if ratios else 0.0

    print(f"  L: max={L_max:.3f}, mean={L_mean:.3f}, std={L_std:.3f}")
    return L_max, L_mean, L_std, ratios


def measure_gamma(llm: LLM, validator_fn, validator_name: str, sources: list) -> tuple:
    """
    Correct gamma measurement:
    - ONE input x
    - TWO runs: y1 = F(x), y2 = F(x) (temperature gives variation)
    - ONE target: x (same for both)
    - gamma = d(V(y1), V(y2)) / d(y1, y2)

    This measures if validator CONTRACTS distance between different outputs.
    """
    print(f"\nMeasuring gamma for {validator_name}...")
    ratios = []

    for i, x in enumerate(sources):
        # Two runs of F on SAME input (temperature=0.7 gives variation)
        y1 = morphism(llm, x)
        y2 = morphism(llm, x)

        d_before = semantic_distance(y1, y2)
        if d_before < 0.01:
            print(f"  Input {i+1}: outputs too similar, skipping")
            continue

        # Both validators use SAME source x as target
        v1 = validator_fn(llm, x, y1)
        v2 = validator_fn(llm, x, y2)
        d_after = semantic_distance(v1, v2)

        ratio = d_after / d_before
        ratios.append(ratio)
        print(f"  Input {i+1}: d_before={d_before:.3f}, d_after={d_after:.3f}, gamma={ratio:.3f}")

    gamma_max = max(ratios) if ratios else 1.0
    gamma_mean = np.mean(ratios) if ratios else 1.0
    gamma_std = np.std(ratios) if ratios else 0.0

    print(f"  gamma: max={gamma_max:.3f}, mean={gamma_mean:.3f}, std={gamma_std:.3f}")
    return gamma_max, gamma_mean, gamma_std, ratios


def run_experiment():
    print("=" * 65)
    print("GFSO Predictive Experiment")
    print("=" * 65)
    print("""
Correct measurement:
- L = d(F(x1), F(x2)) / d(x1, x2)  -- expansion on input PAIRS
- gamma = d(V(y1), V(y2)) / d(y1, y2)  -- contraction on output PAIRS
""")

    llm = LLM()
    pairs = load_input_pairs()
    print(f"Loaded {len(pairs)} input pairs")

    # =========================================================================
    # Step 1: Measure L
    # =========================================================================
    print("\n" + "=" * 65)
    print("STEP 1: Measure L (morphism expansion)")
    print("=" * 65)

    L_max, L_mean, L_std, L_ratios = measure_L(llm, pairs)

    # Get single sources for gamma measurement (not pairs)
    sources = list(set([x1 for x1, x2 in pairs] + [x2 for x1, x2 in pairs]))[:4]

    # =========================================================================
    # Step 2: Measure gamma for different validators
    # =========================================================================
    print("\n" + "=" * 65)
    print("STEP 2: Measure gamma for validators")
    print("=" * 65)
    print("Methodology: ONE input -> TWO F runs -> ONE target for both validators")

    validators = [
        ("No validator (gamma=1)", validator_none),
        ("Weak validator", validator_weak),
        ("Strong validator", validator_strong),
    ]

    results = {}
    for name, v_fn in validators:
        gamma_max, gamma_mean, gamma_std, gamma_ratios = measure_gamma(
            llm, v_fn, name, sources
        )
        results[name] = {
            "gamma_max": gamma_max,
            "gamma_mean": gamma_mean,
            "gamma_std": gamma_std,
            "L_gamma_max": L_max * gamma_max,
            "L_gamma_mean": L_mean * gamma_mean,
        }

    # =========================================================================
    # Step 3: Verification status
    # =========================================================================
    print("\n" + "=" * 65)
    print("STEP 3: Verification Status")
    print("=" * 65)

    print(f"\nMeasured L: max={L_max:.3f}, mean={L_mean:.3f}")
    print("\nScenario Analysis:")
    print("-" * 70)
    print(f"{'Validator':<25} {'gamma_mean':<10} {'L*gamma':<10} {'Status':<15}")
    print("-" * 70)

    for name, r in results.items():
        Lg = r["L_gamma_mean"]
        if Lg < 0.9:
            status = "VERIFIED"
        elif Lg < 1.1:
            status = "BORDERLINE"
        else:
            status = "NOT VERIFIED"
        print(f"{name:<25} {r['gamma_mean']:<10.3f} {Lg:<10.3f} {status:<15}")
    print("-" * 70)

    # =========================================================================
    # Step 4: Plot
    # =========================================================================
    print("\n" + "=" * 65)
    print("STEP 4: Generate Plot")
    print("=" * 65)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: L*gamma bar chart
    ax1 = axes[0]
    names = list(results.keys())
    Lg_values = [results[n]["L_gamma_mean"] for n in names]
    colors = ['#e74c3c' if v > 1 else '#f39c12' if v > 0.9 else '#27ae60' for v in Lg_values]

    bars = ax1.bar(names, Lg_values, color=colors, edgecolor='black', linewidth=1.5)
    ax1.axhline(y=1.0, color='red', ls='--', lw=2, label='Stability threshold')
    ax1.set_ylabel('L * gamma', fontsize=12)
    ax1.set_title(f'Verification Status (L={L_mean:.2f})', fontsize=13)
    ax1.set_ylim(0, max(Lg_values) * 1.2)
    ax1.legend()

    for bar, v in zip(bars, Lg_values):
        status = "OK" if v < 1 else "FAIL"
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                status, ha='center', fontsize=10, fontweight='bold')

    # Right: gamma comparison
    ax2 = axes[1]
    gamma_values = [results[n]["gamma_mean"] for n in names]
    ax2.bar(names, gamma_values, color='#3498db', edgecolor='black', linewidth=1.5)
    ax2.axhline(y=1/L_mean, color='green', ls='--', lw=2, label=f'Required gamma < 1/L = {1/L_mean:.2f}')
    ax2.set_ylabel('gamma (contraction)', fontsize=12)
    ax2.set_title('Validator Contraction Factor', fontsize=13)
    ax2.legend()

    plt.tight_layout()

    plot_path = os.path.join(OUTPUT_DIR, "gfso_predictive.png")
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Plot saved: {plot_path}")

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)

    print(f"""
Measured parameters:
  L (morphism)  = {L_mean:.3f} ± {L_std:.3f}

Validator analysis:
  - No validator:     gamma = 1.0,   L*gamma = {L_mean:.2f} {'< 1 OK' if L_mean < 1 else '>= 1 UNSTABLE'}
  - Weak validator:   gamma = {results['Weak validator']['gamma_mean']:.2f},  L*gamma = {results['Weak validator']['L_gamma_mean']:.2f}
  - Strong validator: gamma = {results['Strong validator']['gamma_mean']:.2f},  L*gamma = {results['Strong validator']['L_gamma_mean']:.2f}

GFSO criterion: L*gamma < 1 -> VERIFIED (bounded errors guaranteed)

Total LLM calls: {llm.calls}
""")

    # Save results
    save_data = {
        "L_max": float(L_max),
        "L_mean": float(L_mean),
        "L_std": float(L_std),
        "validators": {k: {kk: float(vv) for kk, vv in v.items()} for k, v in results.items()},
    }
    json_path = os.path.join(OUTPUT_DIR, "gfso_predictive.json")
    with open(json_path, 'w') as f:
        json.dump(save_data, f, indent=2)
    print(f"Results saved: {json_path}")


if __name__ == "__main__":
    run_experiment()
