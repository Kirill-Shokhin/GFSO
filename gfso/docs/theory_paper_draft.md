# The General Framework for Structural Optimization: Compositional Error Bounds in Enriched Kleisli Categories

**Target Venue:** CAV 2026
**Status:** Draft v4.5 (Universal Theory)

**Author:** Kirill Shokhin ([kashokhin@gmail.com](mailto:kashokhin@gmail.com))
**Repository:** [github.com/Kirill-Shokhin/GFSO](https://github.com/Kirill-Shokhin/GFSO)

---

## Abstract
Hierarchical composition of stochastic components suffers from exponential error cascade: small local deviations amplify into global failures. We propose **GFSO**, synthesizing control theory, behavioral metrics, and category theory. Working in the **Kleisli category of the Kantorovich monad**, we derive compositional error bounds for systems with Lipschitz dynamics. Control mechanisms (audits, guardrails) are formalized as **$\epsilon$-Natural Transformations**—contractions enforcing stability. Our **Stability Criterion** ($L \cdot \gamma \le 1$) is analogous to the small-gain theorem but applies to sequential stochastic chains with Wasserstein metric. Experiments confirm the predicted phase transition: subcritical validators reduce error by orders of magnitude.

---

## 1. Introduction: Control Challenges in Hierarchical Systems

### 1.1. The Telephone Game in Hierarchical Systems
Hierarchical composition is ubiquitous: a corporate directive flows from CEO through middle management to front-line employees; a supply order propagates from retailer through distributors to manufacturers; a reasoning task decomposes from high-level intent through intermediate steps to executable actions in AI agents. In each case, **information passes through a chain of imperfect processors**, and a fundamental question arises: *Does the output preserve the semantic intent of the input?*

Analysis reveals that without structural safeguards, fidelity loss is mathematically inevitable. This is the "Telephone Game" phenomenon, formalized in control theory as **expansive dynamics** ($L > 1$): each processing step introduces noise that amplifies downstream. In organizational hierarchies, this manifests as **bureaucratic drift**—a small policy misinterpretation compounds into catastrophic implementation failure. In supply chains, it appears as the **bullwhip effect**—minor demand fluctuations create exponential inventory swings upstream. In generative AI, it emerges as **semantic collapse**—cumulative hallucinations destroy reasoning chain coherence.

The common thread is *topological*: when morphisms in a compositional structure are expansive ($d(f(x), f(y)) > d(x,y)$), error propagation is **exponential** ($\mathcal{O}(L^n)$ in chain length $n$). Traditional approaches treat each domain separately, but the mathematics reveals a unified pathology.

### 1.2. The Discretization Gap
Existing verification methods—whether probabilistic model checking for software, audit protocols for bureaucracies, or quality assurance in manufacturing—share a common paradigm: **discrete logical verification**. They map continuous state spaces to binary decisions (Pass/Fail, True/False, Compliant/Non-Compliant).

This creates a "Discretization Gap": logical predicates are too brittle to capture *proximity* in high-dimensional spaces. A supply chain state that is "close" to optimal may still fail a binary threshold check, triggering unnecessary interventions. An AI reasoning step that is "nearly correct" gets rejected identically to a catastrophically wrong one, discarding valuable partial progress.

Reliability in hierarchical stochastic systems is not a binary property, but a **continuous metric property**. The question is not "Is the state correct?" but "How far has the distribution drifted from specification?"

### 1.3. The GFSO Paradigm
Instead of asking "Is the state correct?", we ask "Is the transformation stable?". We model components as morphisms in a **Wasserstein-Enriched Kleisli Category**. In this view, reliability is not a property of individual component parameters, but of the **topology of the composition**.

Our central thesis is that **Control Mechanisms are Contraction Mappings**: whether a corporate audit, a supply chain quality check, or an AI guardrail, the formal role is identical—an $\epsilon$-Natural Transformation that minimizes the Wasserstein distance between *Implementation* (stochastic reality) and *Specification* (ideal logic). By treating control mechanisms as metric operators rather than logical predicates, we provide a framework for analyzing the reliability of compositions.

### 1.4. Why Now?
Each domain has developed heuristics for controlling error propagation: audits in bureaucracies, demand smoothing in supply chains, guardrails in AI systems. These mechanisms share a common intuition ("more control helps") but lack a quantitative criterion for sufficiency.

GFSO addresses this gap by providing a **unified stability criterion** ($L \cdot \gamma \le 1$) that answers a precise engineering question: given component drift $L$ and validator strength $\gamma$, will the system remain stable? The framework enables diagnosis of instability before cascading failures occur and quantifies the trade-off between control cost and system reliability.

### 1.5. Contributions
This paper provides a **categorical synthesis** connecting control theory, behavioral metrics, and probabilistic semantics:
1.  **Wasserstein-Kleisli Semantics:** We instantiate the abstract framework of Markov categories [Fritz, 2020] with concrete Wasserstein bounds, working in the Kleisli category of the Kantorovich monad. This bridges categorical probability with the behavioral metrics tradition [van Breugel & Worrell, 2005; Baldan et al., 2014].
2.  **Stability Criterion Analogous to Small-Gain:** The condition $L \cdot \gamma \le 1$ mirrors the classical small-gain theorem [Jiang et al., 1996] in spirit: both state that "product of gains < 1" ensures stability. However, small-gain applies to feedback loops with $L^p$ norms; GFSO applies to sequential chains with Wasserstein metric. The connection is conceptual, not formal—we do not derive one from the other. Our contribution is the interpretation of validators as $\epsilon$-natural transformations in Kleisli categories.
3.  **Domain Instantiation:** We provide concrete instantiations for domains where classical control assumptions fail: corporate hierarchies, supply chains with the bullwhip effect, and AI agent chains with semantic drift.
4.  **Empirical Validation:** Synthetic experiments confirm the predicted phase transition at $L \cdot \gamma = 1$, demonstrating that the categorical framework yields practical predictions.

---

## 2. Related Work

GFSO synthesizes four research traditions: behavioral metrics from concurrency theory, categorical probability, contraction-based stability from control theory, and compositional verification. We position our contribution as a **categorical synthesis** that unifies these perspectives.

### 2.1. Behavioral Metrics and Optimal Transport
The study of quantitative behavioral equivalence originated with **probabilistic bisimulation metrics** [Desharnais et al., 2002], which measure how "close" two states are behaviorally. Van Breugel & Worrell [2005] established that such metrics arise naturally from the **Kantorovich lifting** of the underlying state metric—connecting behavioral equivalence to optimal transport.

This connection was systematized coalgebraically by **Baldan et al. [2014]**, who showed how to derive Wasserstein-style behavioral metrics via **functor lifting**. Recent work [Bacci et al., 2018] provides an algebraic axiomatization of Markov processes with quantitative equational logic. A breakthrough result [Calo et al., 2024] proves that bisimulation metrics *are* optimal transport distances and can be computed efficiently via Sinkhorn iteration [Cuturi, 2013].

**GFSO's position:** We adopt the Wasserstein metric as our semantic distance, following this established tradition. Our contribution is not the metric itself, but its application to **validator design** via the stability criterion.

### 2.2. Categorical Probability
**Markov Categories** [Fritz, 2020] axiomatize probability synthetically, enabling diagrammatic reasoning about stochastic processes. String diagram techniques for Bayesian inference [Cho & Jacobs, 2019] provide intuitive compositional calculi. The **Kantorovich/Wasserstein monad** on metric spaces [Perrone, 2021] and its interaction with deterministic submonads [Moss & Perrone, 2022] form the categorical foundation for our Kleisli construction.

**GFSO's position:** We work in the Kleisli category of the Kantorovich monad, instantiating the abstract Markov category framework with concrete Wasserstein bounds.

### 2.3. Contraction Theory and Small-Gain Stability
The study of stability via **contraction mappings** was systematized by **Lohmiller & Slotine [1998]**, who established that systems with uniformly contracting dynamics exhibit exponential convergence. The **small-gain theorem** [Jiang et al., 1996; Sontag, 2008] provides the classical stability criterion for cascaded systems: if $L_1 \cdot L_2 < 1$ for two interconnected systems with gains $L_1, L_2$, the cascade is stable. This has been extended to networks [Dashkovskiy et al., 2010] and recently connected to learning-based control [Tsukamoto et al., 2021].

**GFSO's position:** Our criterion $L \cdot \gamma \le 1$ is **analogous** to the small-gain condition: both express "product of gains < 1 → stability". The settings differ—small-gain addresses feedback loops with $L^p$ norms; GFSO addresses sequential chains with Wasserstein metric. We do not claim formal equivalence. Our contribution is: (1) working in enriched Kleisli categories with $W_1$ bounds, (2) interpreting validators as $\epsilon$-natural transformations, and (3) extending to stochastic, high-dimensional settings where classical control assumptions fail.

### 2.4. Compositional Probabilistic Verification
**Probabilistic Model Checking** (PRISM [Kwiatkowska et al., 2011]) verifies properties of finite-state MDPs. Compositional extensions via **assume-guarantee reasoning** [Kwiatkowska et al., 2010] enable modular verification but remain discrete. Recent work on **string diagrams for MDPs** [Watanabe et al., 2023] brings categorical compositionality to probabilistic model checking.

For neural networks, **Lipschitz certification** [Fazlyab et al., 2019] computes tight bounds on network sensitivity, while tools like **Marabou** [Katz et al., 2019] verify properties via SMT solving. In AI agents, runtime verification (**AgentGuard** [Koohestani, 2025]) and empirical optimization (**DSPy** [Khattab et al., 2024]) address error propagation heuristically.

**GFSO's position:** We provide a metric-space framework that complements discrete verification. Where PRISM asks "does the system satisfy $\phi$?", GFSO asks "how far can the system drift from specification?"

### 2.5. Contract-Based Design
**Design by Contract** [Meyer, 1992] specifies component behavior via pre/postconditions. **Assume-Guarantee contracts** [Benveniste et al., 2018] extend this to concurrent systems. We formalize contracts as **$\epsilon$-Natural Transformations**—families of validators ensuring approximate commutativity of the implementation-specification diagram.

### 2.6. Positioning Summary

| Aspect | Prior Work | Limitation | GFSO Extension |
| :--- | :--- | :--- | :--- |
| **Stability criterion** | Small-gain: $L_1 \cdot L_2 < 1$ [Jiang et al.] | Feedback loops, $L^p$ norms | Sequential chains, $W_1$ metric |
| **Behavioral metrics** | Kantorovich lifting [Baldan et al.] | Characterization only | Validator design criterion |
| **Categorical probability** | Markov categories [Fritz] | Abstract, no error bounds | Concrete Wasserstein bounds |
| **Compositional verification** | Assume-guarantee [Kwiatkowska et al.] | Discrete, logical | Continuous, metric |

**GFSO's Contribution:** The condition $L \cdot \gamma \le 1$ is **analogous** to the small-gain theorem but applies to a different setting (sequential stochastic chains vs feedback loops). Our contributions are:
1. **Framework Synthesis:** We connect three traditions—control-theoretic stability intuitions, categorical semantics (Kleisli categories), and behavioral metrics (Wasserstein distance)—providing explicit error bounds for hierarchical stochastic systems
2. **Validator Formalization:** We introduce $\epsilon$-natural transformations as a new abstraction for validators—formalizing control mechanisms (audits, guardrails, quality checks) as morphism families with quantitative contraction guarantees. This abstraction is novel
3. **Domain Generalization:** We apply the framework to stochastic, high-dimensional settings where classical control assumptions (determinism, low dimension, linearity) fail—providing concrete instantiations for AI agent chains, supply chains, and organizational hierarchies

---

## 3. Preliminaries: The Category $\mathbf{PolMet}$

### 3.1. The Base Category $\mathbf{PolMet}$
Let $\mathbf{PolMet}$ be the category where:
*   **Objects:** Polish metric spaces $(X, d_X)$.
*   **Morphisms:** Lipschitz continuous maps $f: X \to Y$ (with any Lipschitz constant $L \ge 0$).
This category acts as our deterministic base. We equip it with the **Kantorovich Monad** $\mathcal{D}$, a metric refinement of the classical Giry monad [Giry, 1982] studied by Perrone [2021], defined by:
*   **Functor:** $\mathcal{D}(X) = \mathcal{P}_1(X)$, the space of Borel probability measures with finite first moment, metrized by $W_1$.
*   **Unit:** $\eta_X: X \to \mathcal{D}(X)$ maps $x \mapsto \delta_x$ (Dirac measure).
*   **Multiplication:** $\mu_X: \mathcal{D}(\mathcal{D}(X)) \to \mathcal{D}(X)$ is marginalization (integrating out the outer measure).

The term "enriched" refers to the Lawvere perspective: $W_1$ provides hom-object structure over $([0,\infty], \ge, +)$, making Lipschitz bounds compositional (see §8.3).

### 3.2. The Stochastic Category $\mathcal{Kl}(\mathcal{D})$
Our working category is the **Kleisli Category** of the monad $\mathcal{D}$, denoted $\mathcal{Kl}(\mathcal{D})$. This structure is inspired by the synthetic approach to probability via **Markov Categories** [Fritz, 2020].
*   **Objects:** Same as in $\mathbf{PolMet}$.
*   **Morphisms:** A morphism $f: X \to Y$ in $\mathcal{Kl}(\mathcal{D})$ corresponds to a continuous map $f: X \to \mathcal{D}(Y)$ in $\mathbf{PolMet}$ (a Markov kernel).
*   **Composition:** For $f: X \to Y$ and $g: Y \to Z$ in $\mathcal{Kl}(\mathcal{D})$, the Kleisli composition $g \circ_K f: X \to Z$ is defined via the bind operation:
    $$ (g \circ_K f)(x)(B) = \int_Y g(y)(B) \, f(x)(dy) $$
    where $B$ is a Borel set in $Z$.

---

## 4. The GFSO Framework

### 4.1. Ontology
We model the system using functors from an index category $\mathcal{I}$ (the dependency DAG) to $\mathcal{Kl}(\mathcal{D})$.

**Assumption 4.0 (Object Agreement):** We assume the functors $F$ and $G$ agree on objects, mapping each task node $i \in \mathcal{I}$ to the same state space $X_i \in \mathbf{PolMet}$. They differ only on morphisms, capturing the divergence between *Plan* and *Execution*.

| Concept | Symbol | Type | Description |
| :--- | :--- | :--- | :--- |
| **Index** | $\mathcal{I}$ | Category | Finite category representing task dependencies. |
| **Plan** | $G$ | $\mathcal{I} \to \mathcal{Kl}(\mathcal{D})$ | Functor defining the specification/expected behavior. |
| **Execution** | $F$ | $\mathcal{I} \to \mathcal{Kl}(\mathcal{D})$ | Functor defining the actual implementation. |
| **Validator** | $\eta$ | NatTrans | Natural transformation approximating $F$ to $G$. |

### 4.2. $\epsilon$-Natural Transformations
**Definition 4.1 (Kleisli Commutativity):**
A family of morphisms $\eta_X: X \to X$ in $\mathcal{Kl}(\mathcal{D})$ (represented by kernels $X \to \mathcal{D}(X)$) constitutes an **$\epsilon$-Natural Transformation** $\eta: F \Rightarrow G$. Note that under **Assumption 4.0**, $F(X) = G(X) = X$, so $\eta_X$ is a well-typed endomorphism. The condition holds if for every morphism $f: X \to Y$ in $\mathcal{I}$ and for all $x \in X$:
$$ W_1( (\eta_Y \circ_K F(f))(x), (G(f) \circ_K \eta_X)(x) ) \le \epsilon $$
Here, $\circ_K$ denotes Kleisli composition. The inequality requires the naturality square to commute up to $\epsilon$ in the $W_1$ metric.

**Definition 4.2a (Lipschitz Validator):**
A validator is a map $\mathcal{V}: \mathcal{D}(X) \to \mathcal{D}(X)$ that is **$\gamma$-Lipschitz**: for any pair of distributions $\mu, \nu \in \mathcal{D}(X)$,
$$ W_1(\mathcal{V}(\mu), \mathcal{V}(\nu)) \le \gamma \cdot W_1(\mu, \nu) $$
This property ensures small input differences produce small output differences.

**Definition 4.2b (Contractive Validator):**
Given a target distribution $\mu_G \in \mathcal{D}(X)$, a validator $\mathcal{V}$ is **$\gamma$-Contractive to $\mu_G$** if:
$$ W_1(\mathcal{V}(\mu), \mu_G) \le \gamma \cdot W_1(\mu, \mu_G) \quad \forall \mu \in \mathcal{D}(X) $$
with $\gamma < 1$. This property ensures the validator moves distributions closer to the target. (In context, $\mu_G = G_{chain}(x)$ where $G$ is the specification functor.)

**Assumption 4.3 (Specification Invariance):**
The validator $\mathcal{V}$ fixes the specification: $\mathcal{V}(G_{chain}(x)) = G_{chain}(x)$ for all $x$.
*Justification:* The specification $G$ represents the ideal plan. A well-designed validator should not alter distributions that already match the target—it only corrects deviations.

**Remark:** These properties are logically independent. However, if $\mathcal{V}$ is $\gamma$-Lipschitz (4.2a) and satisfies Specification Invariance (Assumption 4.3), then $\mathcal{V}$ is automatically $\gamma$-Contractive to $G_{chain}(x)$ (4.2b). The Stability Criterion (Corollary 5.3) requires 4.2b.

**Remark (Practical Interpretation):** The contraction factor $\gamma$ represents the fraction of error that *passes through* validation. A validator with $\gamma = 0.7$ removes 30% of the deviation from specification; the remaining 70% propagates downstream. Perfect validation ($\gamma = 0$) is neither required nor realistic—the criterion $L \cdot \gamma \le 1$ shows that even imperfect validators suffice when their contraction compensates for component expansiveness.

**Remark (Role of Definition 4.1 vs 4.2):** These definitions serve distinct purposes:
- **Definition 4.1 (ε-Naturality):** Categorical motivation—why validators are natural transformations between $F$ and $G$. Ensures *semantic coherence* across composition stages. Not directly used in proofs.
- **Definition 4.2a + Assumption 4.3:** The operational requirements for Stability Criterion (Corollary 5.3). The proofs use 4.2a (Lipschitz) combined with 4.3 (Specification Invariance), which together imply 4.2b (Contractivity).

**Lemma 4.4 (Canonical Construction):**
In the GFSO framework, the validator map $\mathcal{V}: \mathcal{D}(X) \to \mathcal{D}(X)$ is defined as the **Kleisli extension** of the stochastic kernel $\eta_X: X \to X$:
$$ \mathcal{V}(\mu)(B) := \hat{\eta_X}(\mu)(B) = \int \eta_X(x)(B) \, \mu(dx) $$
If the kernel $\eta_X$ satisfies the metric Lipschitz property on points ($W_1(\eta_X(x), \eta_X(y)) \le \gamma d(x,y)$), then $\mathcal{V}$ is $\gamma$-Lipschitz on distributions (Definition 4.2a) by Lemma A.0. Combined with Specification Invariance (Assumption 4.3), this yields $\gamma$-Contractivity to the target (Definition 4.2b).

---

## 5. Main Theorems

**Assumption 5.0 (Strict Specification):**
The specification $G: \mathcal{I} \to \mathcal{Kl}(\mathcal{D})$ is a **strict functor**: $G(g \circ f) = G(g) \circ_K G(f)$ for all composable morphisms. This reflects that the plan is internally consistent—the specification for a composite task equals the composition of specifications. We treat strict functoriality as a *normative ideal*: a coherent plan assumes compositionality. In practice (bureaucracies, supply chains), high-level plans may not perfectly decompose; such deviation appears as specification laxity $\delta_G$, which effectively increments the modularity tax $\delta_F$ in the global bounds.

**Definition 5.0 (Linear Reliability):**
A sequential system is **Linearly Reliable** if the global error $E_n = W_1(F_{chain}(x), G_{chain}(x))$ grows at most linearly with chain length $n$, i.e., $E_n = O(n)$. This contrasts with the default exponential divergence $O(L^n)$.

**Definition 5.1 (Chain Composition):**
For a sequence of **composable** morphisms $f_1, \dots, f_n$ in $\mathcal{I}$ (with $F(f_i): X_{i-1} \to X_i$ in $\mathcal{Kl}(\mathcal{D})$), we define the implementation and specification chains as:
*   $F_{chain} = F(f_n) \circ_K \dots \circ_K F(f_1)$
*   $G_{chain} = G(f_n) \circ_K \dots \circ_K G(f_1)$

Under **Assumption 5.0**, $G_{chain} = G(f_n \circ \dots \circ f_1) = G(h_n)$ where $h_n$ is the composite morphism.

**Lemma 5.1.1 (Chain-Functor Discrepancy):**
For an approximate functor $F$ satisfying Assumption 5.2b with $L$-Lipschitz components, the discrepancy between $F_{chain}$ and $F(h_n)$ is bounded:
$$ W_1(F_{chain}(x), F(h_n)(x)) \le \delta_F \cdot \frac{L^{n-1} - 1}{L - 1} \quad (L > 1) $$
*Proof:* Each composition step introduces error $\le \delta_F$, which is then amplified by factor $L$ at each subsequent step. Summing the geometric series: $\delta_F(1 + L + \dots + L^{n-2}) = \delta_F \frac{L^{n-1}-1}{L-1}$. $\square$

**Corollary (Explicit Bound for $F_{chain}$):** Combining Theorem 5.1 and Lemma 5.1.1 via triangle inequality:
$$ W_1(F_{chain}(x), G_{chain}(x)) \le L^{n-1}\epsilon_0 + (\epsilon_0 + 2\delta_F) \frac{L^{n-1} - 1}{L - 1} = O(L^n) $$
The chain-functor discrepancy adds a factor of 2 to $\delta_F$ but does not change the asymptotic behavior.

**Assumption 5.1 (Component Compliance):**
We assume the implementation complies with the plan locally. For each morphism $f \in \mathcal{I}$:
$$ W_1(F(f)(x), G(f)(x)) \le \epsilon_0 \quad \forall x $$
This assumption bounds the local implementation error.

**Assumption 5.2a (Approximate Functoriality):**
We model the Implementation $F: \mathcal{I} \to \mathcal{Kl}(\mathcal{D})$ as satisfying **Approximate Functoriality**. This implies that while strict functoriality ($F(g \circ f) = F(g) \circ_K F(f)$) may not hold, the deviation is bounded metrically.

**Assumption 5.2b (Bounded Deviation):**
We assume the deviation from strict functoriality is metrically bounded by $\delta_F$:
$$ \sup_x W_1( (F(g) \circ_K F(f))(x), F(g \circ f)(x) ) \le \delta_F $$
$\delta_F$ quantifies the **Modularity Tax**: the additional error introduced by decomposition.

**Theorem 5.1 (The Exponential Divergence Bound):**
Let $f_1, \dots, f_n$ be a chain of $L$-Lipschitz components ($L > 1$). Under **Assumption 5.1 (Component Compliance)** with local error $\epsilon_0$ and **Assumption 5.2b (Bounded Deviation)** with tax $\delta_F$, the global error follows the recurrence:
$$ E_n \le L^{n-1}\epsilon_0 + (\epsilon_0 + \delta_F) \frac{L^{n-1} - 1}{L - 1} $$
Asymptotically, this confirms the exponential divergence $W_1( F_{chain}(x), G_{chain}(x) ) = O(L^n)$.
*Proof:* See Appendix A.2.

**Proposition 5.2 (Variance Contraction via Truncation):**
Let $\mathcal{V}_T$ be a rejection-sampling validator with threshold $T$. For any error distribution $P$ that is **symmetric about zero** and has bounded support, $\mathcal{V}_T$ acts as a **contraction map** on the Wasserstein distance to the ideal $\delta_0$:
$$ W_1(\mathcal{V}_T(P), \delta_0) < W_1(P, \delta_0) $$
(Symmetry is required to preserve the zero mean property after truncation). For the uniform case $U[-E, E]$ with $T < E$, the contraction factor is $\gamma(T) = T/E$. If $T \ge E$, the validator is identity ($\gamma = 1$) and provides no contraction.
*Proof:* See Appendix B.

**Remark (Generalization to Gaussian):** For Gaussian noise $\mathcal{N}(0, \sigma^2)$, truncation at threshold $T$ similarly yields $\gamma < 1$, though the closed-form expression involves error functions. Specifically, $\gamma = \mathbb{E}[|X| \mid |X| \le T] / \mathbb{E}[|X|]$ where $X \sim \mathcal{N}(0, \sigma^2)$. The uniform case provides an explicit formula; the contraction mechanism generalizes to any symmetric unimodal distribution.

**Remark (Symmetry Limitation):** Proposition 5.2 applies when the error distribution is symmetric about zero—typically the *fresh noise* injected at each step, not the accumulated state. In chains where accumulated state $x_n$ drifts from zero, the distribution becomes biased. Two solutions: (1) apply truncation to the *incremental* error before adding to state, or (2) use Proposition 5.2b (scaling), which provides $\gamma$-contraction for arbitrary distributions without symmetry requirements.

**Remark (Asymmetric Distributions):** Proposition 5.2 requires symmetry to ensure the truncated distribution retains zero mean. For asymmetric error distributions (e.g., biased estimators), truncation alone does not suffice—it may shift the mean further from zero. In such cases, the validator must include a **bias correction** step: $\mathcal{V}(\mu) = \text{Truncate}_T(\mu - \mathbb{E}[\mu])$. This is an idealized model; practical systems should estimate and correct bias before applying threshold validation.

**Proposition 5.2b (Pure Scaling Validator):**
Let $\mathcal{V}_\gamma$ be the pushforward under scaling $x \mapsto \gamma x$, i.e., $\mathcal{V}_\gamma(\mu) = (\gamma \cdot)_* \mu$ for constant $\gamma \in [0,1]$. Then $\mathcal{V}_\gamma$ is $\gamma$-contractive:
$$ W_1(\mathcal{V}_\gamma(\mu), \delta_0) = \gamma \cdot W_1(\mu, \delta_0) $$
*Proof:* By homogeneity of the $W_1$ metric: $W_1((\gamma \cdot)_* \mu, \delta_0) = \inf_\pi \int \|\gamma x - 0\| d\pi = \gamma \inf_\pi \int \|x\| d\pi = \gamma \cdot W_1(\mu, \delta_0)$.

**Remark (Distribution-Dependent Contraction):** Proposition 5.2's contraction factor $\gamma = T/E$ depends on the input distribution's support $E$. This is not a universal validator property—different inputs yield different $\gamma$. For the Stability Criterion (Corollary 5.3), we require $\gamma$ to be bounded uniformly over the family of distributions encountered during system operation. In practice, this means the threshold $T$ must be chosen relative to the expected worst-case error support.

**Remark (Two Validator Classes):** Propositions 5.2 and 5.2b establish two distinct mechanisms satisfying Definition 4.2b: stochastic rejection sampling (realistic, models retry-based validators) and deterministic scaling (minimal, provides precise $\gamma$ control). Both achieve the Stability Criterion (Corollary 5.3).

**Corollary 5.3 (The GFSO Stability Criterion):**
A sufficient condition for a sequential system to be **Linearly Reliable** (per Definition 5.0) is that the product of the component's expansiveness and the control mechanism's contraction is non-expansive:
$$ L \cdot \gamma \le 1 $$
Under this condition, the error bound from Theorem 5.1 collapses from $O(L^n)$ to $O(n(\epsilon_0 + \delta_F))$.
*Proof:* See Appendix C.

**Example 5.4 (Regime Comparison):**
Consider chains with $L=1.2$ and per-step noise injection $\epsilon_0$. We compare three regimes at chain length $n$:

| Regime | $L \cdot \gamma$ | Error Bound | Behavior |
|--------|------------------|-------------|----------|
| No validation | — | $O(L^n) = O(1.2^n)$ | Exponential |
| Supercritical | $1.08$ | $O((L\gamma)^n)$ | Exponential (slower) |
| Subcritical | $0.90$ | $\frac{\gamma \epsilon_0}{1 - L\gamma}$ | Bounded |

*Numerical example:* For $n=50$, unvalidated error grows as $1.2^{50} \approx 9 \times 10^3$. With subcritical validation ($L \cdot \gamma = 0.90$), the steady-state bound is $\frac{0.75 \epsilon_0}{0.10} = 7.5\epsilon_0$ — a reduction by three orders of magnitude. Section 6 confirms this prediction experimentally.

---

### 6. Empirical Validation

**Categorical Instantiation:**
To validate the theory, we instantiate the framework as follows:
*   **Index $\mathcal{I}$:** A linear chain category $1 \to 2 \to \dots \to N$.
*   **State Space:** The Polish space $(\mathbb{R}^{100}, \|\cdot\|_2)$.
*   **Plan $G$:** Maps morphisms to constant kernels $x \mapsto \delta_0$ (the ideal state is always zero).
*   **Implementation $F$:** Maps morphisms to Gaussian kernels $\mathcal{N}(Lx, \sigma^2 I)$ with Lipschitz constant $L=1.2$.
*   **Validator:** Implements the contraction map via pure scaling (Experiment 1, Proposition 5.2b) or rejection sampling with partial observation (Experiment 2, inspired by Proposition 5.2).

We simulated $N=1000$ chains of length 50 in $\mathbb{R}^{100}$ with uniform dynamics $L=1.2$ and noise $\sigma=0.5$.

**Measurement:** The error metric is $\|x_n\|_2$ (Euclidean norm of state). Since $G_{chain}(x_0) = \delta_0$, by Kantorovich-Rubinstein duality: $W_1(F_{chain}(x_0), \delta_0) = \mathbb{E}_{X \sim F_{chain}(x_0)}[\|X\|]$. Thus, averaging $\|x_n\|$ across trials estimates $W_1$.

### 6.1. Phase Transition at $L \cdot \gamma = 1$

The first experiment directly validates the Stability Criterion (Corollary 5.3) by varying the contraction factor $\gamma$:

| Regime | $L \cdot \gamma$ | Mean Error (n=50) | Behavior |
|--------|------------------|-------------------|----------|
| Naive (no validator) | — | 68,485 | Exponential |
| Supercritical | 1.08 | 517 | Exponential (slower) |
| Critical | 1.00 | 29 | Linear |
| Subcritical | 0.90 | **8.6** | **Bounded** |

The phase transition is sharp: at $L \cdot \gamma = 0.90$ (just 10% below critical), error stabilizes; at $L \cdot \gamma = 1.08$ (8% above), error grows exponentially.

![Figure 1: Phase Transition](../experiments/artifacts/fig1_theory_validation.png)

### 6.2. Robustness under Partial Observation

The second experiment tests robustness when the validator observes only a subset of dimensions (modeling realistic scenarios where full state observation is infeasible).

*   **Setup:** Same dynamics ($L=1.2$, $\mathbb{R}^{100}$). Validator observes a random 10% of dimensions per step with measurement noise ($\sigma=0.2$). The validator implements a **rejection-with-interpolation** strategy: if no valid sample is found within $k=10$ retries, the system interpolates toward the previous state ($0.8x + 0.2p$). This conservative fallback bounds the step size: $\|x_{new} - x\| = 0.2\|p - x\|$, preventing unbounded error growth even when rejection fails.
*   **Result:**

| Validator | Observed Dims | Mean Error (n=50) |
|-----------|---------------|-------------------|
| None (Naive) | — | 68,485 |
| Full | 100/100 | 62 |
| Partial | 10/100 | **95** |

Partial observation (10%) achieves comparable containment to full observation. This empirical observation—which we term the **Complexity Asymmetry heuristic**—suggests that sparse random probes suffice when error is isotropically distributed across dimensions.

![Figure 2: Partial Observation](../experiments/artifacts/fig2_realistic_scenario.png)

---

## 7. Domain Instantiations

We formalize the stability criterion $L \cdot \gamma \le 1$ for three domains, establishing anchors for domain-specific analysis.

### 7.1. Corporate Governance and Organizational Hierarchies

**GFSO Model:** An organization is a functor $F: \mathcal{Policy} \to \mathcal{Execution}$ mapping strategic directives (Specification) to operational outcomes (Implementation). Each hierarchical layer (executive → management → front-line) is a morphism introducing stochastic noise.

**Expansiveness Factor $L$:** Bureaucratic drift arises from misinterpretation, information loss during handoffs, and local optimization conflicting with global objectives. As an illustrative estimate, we model $L \approx 1.15$-$1.3$ per layer (empirical calibration is domain-specific).

**Control Mechanism $\gamma$:** Standard Operating Procedures (SOPs), audits, and KPI monitoring act as $\epsilon$-Natural Transformations. A quarterly audit with threshold $T$ on performance metrics implements variance truncation (Proposition 5.2), providing $\gamma < 1$ contraction.

**Stability Criterion:** For a 5-layer hierarchy with $L=1.2$ per layer, effective global control requires $\gamma \le 0.83$ (i.e., audits must reject deviations >17% from specification). Without such control, final implementation error scales as $L^5 \approx 2.5x$ the input uncertainty.

### 7.2. Supply Chain Optimization

**GFSO Model:** A supply chain is a compositional structure $\mathcal{I}$ where nodes are suppliers/manufacturers and edges are logistics/procurement contracts. The "Bullwhip Effect" [Lee et al., 1997] describes exponential demand signal amplification upstream.

**Expansiveness Factor $L$:** Each supply tier amplifies demand variance due to batch ordering, lead time delays, and forecast updating. Measured bullwhip ratios in retail supply chains range $L \approx 1.5$-$2.0$ per tier.

**Control Mechanism $\gamma$:** Information sharing protocols (e.g., EDI, vendor-managed inventory) and demand smoothing policies act as topological validators. Sharing point-of-sale data directly with manufacturers implements a "shortcut" natural transformation, reducing laxity $\delta_F$ by eliminating intermediate noise layers.

**Stability Criterion:** For a 4-tier chain with $L=1.8$ per tier, uncontrolled error is $\mathcal{O}(1.8^4) \approx 10.5x$. Implementing information transparency to achieve $\gamma = 0.55$ yields $1.8 \cdot 0.55 = 0.99 < 1$, restoring stability. This explains observed variance reductions in collaborative forecasting systems.

### 7.3. Generative AI Agent Systems

**GFSO Model:** A compound AI system is a sequence of LLM calls (morphisms) implementing a reasoning plan (Index $\mathcal{I}$). Each call is a stochastic kernel $f: \text{Prompt} \to \mathcal{D}(\text{Response})$ with output distributions in high-dimensional embedding spaces.

**Expansiveness Factor $L$:** Hallucination and semantic drift cause $L > 1$. Illustrative estimates: $L \approx 1.1$-$1.3$ per reasoning step.

**Remark (Local Lipschitz Assumption):** The *global* Lipschitz constant for LLMs may be arbitrarily large—a single token can flip semantic meaning. The estimates above represent the **effective local Lipschitz constant** within the coherent semantic basin of the reasoning trajectory. This locality assumption is implicit in all practical LLM applications; without it, no compositional reasoning would be possible.

**Control Mechanism $\gamma$:** Runtime assertions (e.g., type checks, regex validation, unit tests) and LLM-based verification act as $\epsilon$-Natural Transformations. Rejection sampling with semantic similarity thresholds implements variance truncation.

**Stability Criterion:** For a 10-step reasoning chain with $L=1.2$, unvalidated error is $\mathcal{O}(1.2^{10}) \approx 6.2x$. Guardrails achieving $\gamma = 0.83$ yield $1.2 \cdot 0.83 = 0.996 < 1$, preventing exponential collapse. This formalizes the empirical success of frameworks like DSPy and LangChain.

---

## 8. Discussion: Implementation and Categorical Choices

### 8.1. Why the Wasserstein Monad?
A common question is the choice between the **Giry monad** and the **Wasserstein monad**. While the Giry monad captures measure-theoretic properties, it is "topologically blind"—it doesn't naturally handle the metric proximity required for error propagation. The Wasserstein monad $\mathcal{D}$ on **PolMet** explicitly internalizes the metric $W_1$, allowing us to treat reliability as a Lipschitz property, which is crucial for our Stability Criterion ($L \cdot \gamma \le 1$).

### 8.2. Computational Complexity of $W_1$
For discrete measures with $N$ support points, exact $W_1$ computation is $O(N^3 \log N)$ via optimal transport solvers. For continuous distributions (as in our theoretical framework), $W_1$ is typically intractable to compute exactly.

**Clarification:** GFSO uses $W_1$ as a **theoretical Lyapunov function**—the proofs establish bounds on $W_1$ without requiring its explicit computation. In practice:
- **Validators** use cheap surrogates (KPIs, unit tests, semantic similarity) that correlate with $W_1$ reduction
- **Estimation** (Section 8.4) uses sampling-based approximations
- The **Complexity Asymmetry heuristic** (Section 6.2) suggests that low-dimensional probes often provide sufficient contraction in practice

### 8.3. Connection to Lawvere's Metric Spaces
Our approach is inspired by Lawvere's insight [12] that metric spaces are categories enriched over $([0, \infty], \ge, +)$. While we do not construct a full enrichment here, the Wasserstein distance serves as a natural hom-object measuring "semantic distance" between distributions. The Lipschitz constant $L$ then becomes the composition bound: $d(f \circ g) \le L_f \cdot d(g)$. This perspective suggests that "Stability" ($L \cdot \gamma \le 1$) is not merely a sufficient condition, but reflects the categorical structure of contraction in metric-enriched categories.

### 8.4. GFSO as Diagnostic Framework
A common misconception is that formal methods *eliminate* errors. GFSO makes no such claim. Instead, it provides a **diagnostic framework** that makes errors *measurable and predictable*.

By quantifying $L$ (component drift) and $\gamma$ (control effectiveness) at each hierarchical layer, practitioners can:
1. **Identify bottlenecks:** Layers where $L \cdot \gamma > 1$ are flagged as unstable before cascading failures occur.
2. **Predict degradation:** Given current $L$, $\gamma$, and chain length $n$, the framework bounds worst-case error accumulation.
3. **Optimize interventions:** Resources can be allocated to reduce $L$ (better training, clearer specifications) or reduce $\gamma$ (stronger validation) where the product $L \cdot \gamma$ is largest.

The value lies not in guaranteeing correctness—which is impossible for stochastic systems—but in providing **early warning** and **quantitative trade-off analysis**. Engineers have always known that "more testing helps"; GFSO provides the mathematics to answer "how much testing is enough?"

**Practical Estimation of $L$ and $\gamma$:**
- **Estimating $L$:** Measure output variance under input perturbation. For a component $f$, sample inputs $x, x'$ with $d(x,x') = \epsilon$, compute $L \approx \mathbb{E}[W_1(f(x), f(x'))] / \epsilon$. For LLMs, this corresponds to prompt perturbation studies.
- **Estimating $\gamma$:** Measure error reduction after validation. Given samples $\{e_i\}$ of pre-validation error and $\{e'_i\}$ post-validation, estimate $\gamma \approx \mathbb{E}[e'_i] / \mathbb{E}[e_i]$. For rejection sampling, $\gamma$ depends on threshold $T$ and error distribution (Proposition 5.2).
- **Surrogate metrics:** When $W_1$ is intractable, use domain-specific proxies: KPIs for business processes, semantic similarity for LLMs, defect rates for supply chains.

### 8.5. Limitations and Future Work

**Assumption 4.0 (Same State Spaces).** Our framework assumes $F$ and $G$ agree on objects, meaning implementation and specification operate on identical state spaces. This holds when both are stochastic programs over the same domain. However, practical implementations may operate on discretized or approximated spaces (floating point vs reals, quantized actions, finite precision). Extending GFSO to handle $F(X) \ne G(X)$ requires introducing a projection morphism $\rho: F(X) \to G(X)$ with bounded distortion, adding a term $W_1(\rho(F(f)(x)), G(f)(x))$ to the error bound. This generalization is straightforward but omitted for clarity.

**Lipschitz Linearization.** The Stability Criterion $L \cdot \gamma \le 1$ assumes globally $L$-Lipschitz components. In practice (especially LLMs), local error behavior may be nonlinear—$L$ varies with input. The criterion is thus a *sufficient condition in the linearized neighborhood of the nominal trajectory*. For systems with state-dependent $L(x)$, the bound holds when $\sup_x L(x) \cdot \gamma \le 1$; tighter analysis requires trajectory-specific Lyapunov arguments beyond the scope of this paper.

**High Expansion Regime.** The Stability Criterion $L \cdot \gamma \le 1$ establishes a theoretical lower bound for reliability. However, in systems where $L$ is extremely large (e.g., highly divergent creative tasks), achieving sufficient $\gamma$ via rejection sampling may become computationally prohibitive due to low acceptance rates. Future work will explore the **Categorical Synthesis of Optimal Validators**, using the adjunction between Specification and Implementation to automatically derive contraction mappings that minimize $W_1$ while maximizing sample efficiency.

**Experimental Comparison.** Our experiments validate GFSO's theoretical predictions (phase transition, partial observation robustness) on synthetic benchmarks. Direct comparison with existing approaches (PRISM for probabilistic model checking, AgentGuard for runtime verification) requires implementing equivalent tasks across frameworks—a significant engineering effort orthogonal to this paper's theoretical contribution. Such empirical benchmarking is planned for future work.

---

## References

### Behavioral Metrics and Optimal Transport
1.  **Desharnais, J., Gupta, V., Jagadeesan, R. & Panangaden, P.** (2002). "The metric analogue of weak bisimulation for probabilistic processes". *LICS 2002*, 413-422.
2.  **van Breugel, F. & Worrell, J.** (2005). "A behavioural pseudometric for probabilistic transition systems". *Theoretical Computer Science*, 331(1), 115-142.
3.  **Baldan, P., Bonchi, F., Kerstan, H. & König, B.** (2014). "Behavioral Metrics via Functor Lifting". *FSTTCS 2014*, LIPIcs 29, 403-415.
4.  **Bacci, G., Mardare, R., Panangaden, P. & Plotkin, G.** (2018). "An Algebraic Theory of Markov Processes". *LICS 2018*, 679-688.
5.  **Cuturi, M.** (2013). "Sinkhorn Distances: Lightspeed Computation of Optimal Transport". *NeurIPS 2013*, 2292-2300.
6.  **Calo, S., Jonsson, A., Neu, G., Schwartz, L. & Segovia-Aguas, J.** (2024). "Bisimulation Metrics are Optimal Transport Distances, and Can be Computed Efficiently". *NeurIPS 2024*.
7.  **Villani, C.** (2009). *Optimal Transport: Old and New*. Springer.

### Categorical Probability
8.  **Giry, M.** (1982). "A categorical approach to probability theory". In *Categorical Aspects of Topology and Analysis*, LNCS 915, Springer, 68-85.
9.  **Fritz, T.** (2020). "A synthetic approach to Markov kernels, conditional independence and theorems on sufficient statistics". *Advances in Mathematics*, 370.
10. **Cho, K. & Jacobs, B.** (2019). "Disintegration and Bayesian Inversion via String Diagrams". *Mathematical Structures in Computer Science*, 29(7), 938-971.
11. **Moss, S. & Perrone, P.** (2022). "Probability Monads with Submonads of Deterministic States". *LICS 2022*, 1-13.
12. **Perrone, P.** (2021). "Lifting couplings in Wasserstein spaces". *arXiv:2110.06591*.
13. **Lawvere, F.W.** (1973). "Metric spaces, generalized logic, and closed categories". *Rendiconti del Seminario Matematico e Fisico di Milano*, 43, 135-166.

### Contraction Theory and Control
14. **Lohmiller, W. & Slotine, J.-J.E.** (1998). "On Contraction Analysis for Nonlinear Systems". *Automatica*, 34(6), 683-696.
15. **Jiang, Z.-P., Mareels, I.M.Y. & Wang, Y.** (1996). "A Lyapunov Formulation of the Nonlinear Small-Gain Theorem for Interconnected ISS Systems". *Automatica*, 32(8), 1211-1215.
16. **Sontag, E.D.** (2008). "Input to State Stability: Basic Concepts and Results". In *Nonlinear and Optimal Control Theory*, Springer, 163-220.
17. **Dashkovskiy, S., Rüffer, B. & Wirth, F.** (2010). "Small Gain Theorems for Large Scale Systems and Construction of ISS Lyapunov Functions". *SIAM J. Control Optim.*, 48(6), 4089-4118.
18. **Tsukamoto, H., Chung, S.-J. & Slotine, J.-J.E.** (2021). "Contraction Theory for Nonlinear Stability Analysis and Learning-based Control: A Tutorial Overview". *Annual Reviews in Control*, 52, 135-169.

### Compositional Verification
19. **Kwiatkowska, M., Norman, G. & Parker, D.** (2011). "PRISM 4.0: Verification of Probabilistic Real-time Systems". *CAV 2011*, LNCS 6806, 585-591.
20. **Kwiatkowska, M., Norman, G., Parker, D. & Qu, H.** (2010). "Assume-Guarantee Verification for Probabilistic Systems". *TACAS 2010*, LNCS 6015, 23-37.
21. **Watanabe, K., Eberhart, C., Asada, K. & Hasuo, I.** (2023). "Compositional Probabilistic Model Checking with String Diagrams of MDPs". *CAV 2023*, LNCS 13966, 45-67.
22. **Kozen, D.** (1981). "Semantics of probabilistic programs". *Journal of Computer and System Sciences*, 22(3), 328-350.

### Neural Network Verification and AI Safety
23. **Fazlyab, M., Robey, A., Hassani, H., Morari, M. & Pappas, G.J.** (2019). "Efficient and Accurate Estimation of Lipschitz Constants for Deep Neural Networks". *NeurIPS 2019*, 11427-11438.
24. **Katz, G. et al.** (2019). "The Marabou Framework for Verification and Analysis of Deep Neural Networks". *CAV 2019*, LNCS 11561, 443-452.
25. **Khattab, O. et al.** (2024). "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines". *ICLR 2024*.
26. **Koohestani, R.** (2025). "AgentGuard: Runtime Verification of AI Agents". *arXiv:2509.23864*, AgenticSE @ ASE 2025.

### Contract-Based Design
27. **Meyer, B.** (1992). "Applying 'Design by Contract'". *IEEE Computer*, 25(10), 40-51.
28. **Benveniste, A. et al.** (2018). "Contracts for System Design". *Foundations and Trends in Electronic Design Automation*, 12(2-3), 124-400.

### Domain Applications
29. **Lee, H.L., Padmanabhan, V. & Whang, S.** (1997). "The Bullwhip Effect in Supply Chains". *Sloan Management Review*, 38(3), 93-102.

---

## Appendix: Detailed Proofs

### A.0. Lemma (Wasserstein Lifting)
If a kernel $k: X \to \mathcal{D}(Y)$ satisfies the metric Lipschitz condition $W_1(k(x), k(x')) \le L \cdot d_X(x, x')$, then its extension to distributions $\hat{k}: \mathcal{D}(X) \to \mathcal{D}(Y)$ is $L$-Lipschitz in $W_1$:
$$W_1(\hat{k}(\mu), \hat{k}(\nu)) \le L \cdot W_1(\mu, \nu)$$
*Proof:* Follows from Kantorovich-Rubinstein duality. See Perrone [2021], Theorem 5.1 (Lifting Property).

### A.1. Lemma: Composition Bound (Gluing)
To bound the composition $W_1(k \circ_K f, k \circ_K g)$, where $f,g: X \to Y$ and $k: Y \to Z$, let $\pi^*$ be the optimal coupling on $Y \times Y$ realizing $W_1(f(a), g(a))$. We construct a coupling $\Pi$ on $Z \times Z$ as the pushforward of $\pi^*$ through the product kernel $k \otimes k$:
$$ \Pi(dz_1, dz_2) = \int_{Y \times Y} (k(y_1) \otimes k(y_2))(dz_1, dz_2) \, \pi^*(dy_1, dy_2) $$
**Marginal Verification:** $\mathrm{proj}_1(\Pi) = (k \circ_K f)(a)$.
**Cost Bound:** $\int_{Z \times Z} d_Z \, d\Pi \le L \int_{Y \times Y} d_Y(y_1, y_2) \, d\pi^* = L \cdot W_1(f(a), g(a))$ (using Lemma A.0).

### A.1.5 Lemma (Pointwise to Distributed Proximity)
If $W_1(k(x), k'(x)) \le \epsilon$ for all $x \in X$, then for any distribution $\mu \in \mathcal{D}(X)$:
$$ W_1( \hat{k}(\mu), \hat{k'}(\mu) ) \le \epsilon $$
where $\hat{k}(\mu)(B) = \int k(x)(B) \, d\mu(x)$ is the Kleisli extension.
*Proof:* By Kantorovich-Rubinstein duality, for any 1-Lipschitz function $\phi$:
$$ |\mathbb{E}_{\hat{k}(\mu)}[\phi] - \mathbb{E}_{\hat{k'}(\mu)}[\phi]| = |\mathbb{E}_{x \sim \mu}[\mathbb{E}_{y \sim k(x)}[\phi(y)] - \mathbb{E}_{y \sim k'(x)}[\phi(y)]]| $$
$$ \le \mathbb{E}_{x \sim \mu}[ |\mathbb{E}_{k(x)}[\phi] - \mathbb{E}_{k'(x)}[\phi]| ] $$
$$ \le \mathbb{E}_{x \sim \mu}[ W_1(k(x), k'(x)) ] \le \mathbb{E}_{x \sim \mu}[\epsilon] = \epsilon $$
Taking the supremum over $\phi$ yields the result. $\square$

### A.2. Proof of Theorem 5.1 (The Exponential Divergence Bound)
We proceed by induction on chain length $n$.
Let $h_n = f_n \circ \dots \circ f_1$. We define $E_n = W_1(F(h_n)(x), G(h_n)(x))$.

*Note:* We bound $E_n$ for $F(h_n)$ directly. The bound for $F_{chain}$ follows by Lemma 5.1.1 and triangle inequality.

**Base Case ($n=1$):**
$E_1 = W_1(F(f_1)(x), G(f_1)(x)) \le \epsilon_0$ by Assumption 5.1.

**Inductive Step:**
Consider a path of length $n+1$: $h_{n+1} = f_{n+1} \circ h_n$.
We want to bound $E_{n+1} = W_1(F(h_{n+1})(x), G(h_{n+1})(x))$.

Using the triangle inequality:
$$ E_{n+1} \le W_1( F(h_{n+1})(x), (F(f_{n+1}) \circ_K F(h_n))(x) ) + W_1( (F(f_{n+1}) \circ_K F(h_n))(x), G(h_{n+1})(x) ) $$
The first term is bounded by $\delta_F$ (Assumption 5.2b).
For the second term, since the specification $G$ is a strict functor (by construction of the plan), we have $G(h_{n+1}) = G(f_{n+1}) \circ_K G(h_n)$. Thus we compare $F(f_{n+1}) \circ_K F(h_n)$ with $G(f_{n+1}) \circ_K G(h_n)$.

Decomposing via the mixed term $(F(f_{n+1}) \circ_K G(h_n))(x)$:
$$ \le W_1( F(f_{n+1}) \circ_K F(h_n), F(f_{n+1}) \circ_K G(h_n) ) + W_1( F(f_{n+1}) \circ_K G(h_n), G(f_{n+1}) \circ_K G(h_n) ) + \delta_F $$
1.  **Amplification Term:** By Lemma A.0 (Lifting) and Lemma A.1 (Composition), since $F(f_{n+1})$ is $L$-Lipschitz:
    $$ W_1( F(f_{n+1}) \circ_K F(h_n), F(f_{n+1}) \circ_K G(h_n) ) \le L \cdot W_1(F(h_n), G(h_n)) = L \cdot E_n $$
2.  **Injection Term:** By Assumption 5.1 (Component Compliance):
    $$ W_1( F(f_{n+1}) \circ_K G(h_n), G(f_{n+1}) \circ_K G(h_n) ) \le \epsilon_0 $$
    *(This follows from Lemma A.1.5 because $F(f_{n+1})$ and $G(f_{n+1})$ are $\epsilon_0$-close pointwise).*

Thus:
$$ E_{n+1} \le L \cdot E_n + \epsilon_0 + \delta_F $$
This linear recurrence $E_{n+1} = L \cdot E_n + C$ solves to $E_n \sim O(L^n)$ for $L > 1$.

### B. Proof of Proposition 5.2 ($W_1$ Contraction via Truncation)
**Proof:** For a distribution $P$ with zero mean and support containing values beyond $[-T, T]$, we show $W_1(\mathcal{V}_T(P), \delta_0) < W_1(P, \delta_0)$.

By Kantorovich-Rubinstein duality, for $P$ with zero mean:
$$ W_1(P, \delta_0) = \mathbb{E}_{e \sim P}[|e|] $$

After rejection sampling with threshold $T$, the truncated distribution $P_T$ has:
$$ P_T(de) = \frac{1}{Z} \cdot P(de) \cdot \mathbb{1}_{|e| \le T} \quad \text{where } Z = P(|e| \le T) $$

**1. General Case:**
We decompose the expectation of the original distribution:
$$ \mathbb{E}_P[|e|] = \int_{|e| \le T} |e| dP + \int_{|e| > T} |e| dP $$
The first term equals $Z \cdot \mathbb{E}_{P_T}[|e|]$. Let $P_{tail}$ denote the conditional distribution on $\{|e| > T\}$ with mass $1-Z$. Then:
$$ \mathbb{E}_P[|e|] = Z \cdot \mathbb{E}_{P_T}[|e|] + (1-Z) \cdot \mathbb{E}_{P_{tail}}[|e|] $$

*Case A (Strict Contraction):* If $P(|e| > T) > 0$, then $P_{tail}$ is well-defined. Since all mass in $P_{tail}$ satisfies $|e| > T$ and the support of $P_T$ is $[-T, T]$:
$$ \mathbb{E}_{P_{tail}}[|e|] > T \ge \mathbb{E}_{P_T}[|e|] $$
Therefore:
$$ \mathbb{E}_P[|e|] > Z \cdot \mathbb{E}_{P_T}[|e|] + (1-Z) \cdot \mathbb{E}_{P_T}[|e|] = \mathbb{E}_{P_T}[|e|] $$
Thus, $W_1(P_T, \delta_0) < W_1(P, \delta_0)$ and $\gamma < 1$.

*Case B (No Contraction):* If $P(|e| > T) = 0$, then $P = P_T$, and $\gamma = 1$. This implies the validator is passive when the error is within bounds.

**2. Uniform Case $U[-E, E]$:**
Let $e \sim U[-E, E]$. The mean absolute error is:
$$ W_1(P, \delta_0) = \frac{1}{2E} \int_{-E}^{E} |x| dx = \frac{1}{2E} \cdot 2 \int_{0}^{E} x dx = \frac{1}{E} \left[ \frac{x^2}{2} \right]_{0}^{E} = \frac{E}{2} $$
The truncated distribution is $U[-T, T]$. Similarly:
$$ W_1(P_T, \delta_0) = \frac{T}{2} $$
The contraction factor is:
$$ \gamma = \frac{W_1(P_T, \delta_0)}{W_1(P, \delta_0)} = \frac{T/2}{E/2} = \frac{T}{E} $$
$\square$

### C. Derivation of Stability Criterion
We modify the recurrence from (A.2) by applying the validator $\mathcal{V}$ after each step.
Let $E'_{n}$ be the error after validation at step $n$.

*Constructive condition for Assumption 4.3:* For a rejection-sampling validator $\mathcal{V}_T$ with threshold $T$, Specification Invariance holds iff $\text{supp}(G_{chain}(x)) \subseteq [-T, T]$. In words: the specification's error distribution must lie entirely within the acceptance region. This is a design constraint—the threshold $T$ must be chosen large enough to accommodate the ideal output, but small enough to reject deviations.

*Notation:* For brevity, let $F := F_{chain}(x)$ and $G := G_{chain}(x)$ denote the output distributions at step $n+1$.

Under Assumption 4.3 (Specification Invariance), $\mathcal{V}(G) = G$. Combined with Definition 4.2a ($\gamma$-Lipschitz validator):
$$ E'_{n+1} = W_1(\mathcal{V}(F), G) \stackrel{4.3}{=} W_1(\mathcal{V}(F), \mathcal{V}(G)) \stackrel{4.2a}{\le} \gamma \cdot W_1(F, G) = \gamma \cdot E_{n+1}^{raw} $$
(Note: This derivation requires both 4.2a and 4.3. Definition 4.2b alone is insufficient—we need the Lipschitz property to bound the distance between $\mathcal{V}(F)$ and $\mathcal{V}(G)$.)

By this contraction property:
$$ E'_{n+1} \le \gamma \cdot E_{n+1}^{raw} $$
Substituting the expansion from (A.2):
$$ E'_{n+1} \le \gamma \cdot ( L \cdot E'_n + \epsilon_0 + \delta_F ) $$
$$ E'_{n+1} = (L \cdot \gamma) E'_n + \gamma(\epsilon_0 + \delta_F) $$
This is a linear recurrence of the form $x_{n+1} = A x_n + B$.
For the system to be **Linearly Reliable** (Definition 5.0), the error must not diverge. This requires the slope $A \le 1$:
$$ L \cdot \gamma \le 1 $$

**Remark (Steady-State Analysis):** The three regimes exhibit qualitatively different long-term behavior:
- **Subcritical ($L \cdot \gamma < 1$):** Error converges to a finite steady-state $E'_\infty = \frac{\gamma(\epsilon_0 + \delta_F)}{1 - L\gamma}$. This represents equilibrium between error injection (new noise each step) and error contraction (validator reducing accumulated drift).
- **Critical ($L \cdot \gamma = 1$):** Error grows linearly as $E'_n = E'_0 + n \cdot \gamma(\epsilon_0 + \delta_F)$. The system is marginally stable.
- **Supercritical ($L \cdot \gamma > 1$):** Error grows exponentially as $E'_n \sim (L\gamma)^n$. The system is unstable.

Q.E.D.