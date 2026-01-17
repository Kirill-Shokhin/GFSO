"""
LLM Domain Adapter for GFSO (Paper v7.0, Section 6.3)

Implements GFSO primitives for LLM chains:
- TextState: State representation for text + facts
- LLMMorphism: Kleisli morphism wrapping LLM API calls
- FactCheckValidator: γ-contractive validator for fact preservation
- EmbeddingMetric: W₁ proxy via embedding distance

Example (fact-drift experiment):
    client = Anthropic()
    morphism = LLMMorphism(client, "Paraphrase: {text}", L=1.1)
    validator = FactCheckValidator(client, facts, gamma=0.85)

    engine = GFSOEngine(...)
    result = engine.execute_chain(morphism, validator, initial_state, n=10)
"""

from dataclasses import dataclass, field
from typing import Optional, Callable
import json

from gfso.core.kleisli import State, Distribution, dirac_delta
from gfso.core.morphism import LipschitzMorphism
from gfso.contract.validator import Validator

__all__ = [
    'TextState',
    'LLMMorphism',
    'FactCheckValidator',
    'EmbeddingMetric',
    'text_metric',
    'run_fact_drift_experiment',
]


@dataclass(frozen=True)
class TextState:
    """
    State in LLM chain: text with optional structured facts.

    Used as state space for text transformation chains.

    Attributes:
        text: The text content
        facts: Optional extracted facts for validation
        embedding: Optional embedding vector for W₁ computation
    """
    text: str
    facts: Optional[tuple[str, ...]] = None
    embedding: Optional[tuple[float, ...]] = None

    def __hash__(self):
        return hash((self.text, self.facts))

    def __eq__(self, other):
        if not isinstance(other, TextState):
            return False
        return self.text == other.text and self.facts == other.facts


def text_metric(s1: TextState, s2: TextState) -> float:
    """
    Simple text metric based on character edit distance (normalized).

    For production use, prefer EmbeddingMetric with sentence-transformers.
    """
    if s1.text == s2.text:
        return 0.0

    # Normalized Levenshtein-like metric (simplified)
    len1, len2 = len(s1.text), len(s2.text)
    max_len = max(len1, len2)

    if max_len == 0:
        return 0.0

    # Count character differences (simplified metric)
    common = sum(c1 == c2 for c1, c2 in zip(s1.text, s2.text))
    return 1.0 - common / max_len


class EmbeddingMetric:
    """
    W₁ proxy metric using embedding distance.

    Uses sentence-transformers or OpenAI embeddings for semantic similarity.

    Args:
        model_name: Sentence-transformers model name
        use_cosine: If True, use cosine distance; else L2
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        use_cosine: bool = True,
    ):
        self._model_name = model_name
        self._use_cosine = use_cosine
        self._model = None

    def _ensure_model(self):
        """Lazy load model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers required for EmbeddingMetric. "
                    "Install with: pip install sentence-transformers"
                )

    def __call__(self, s1: TextState, s2: TextState) -> float:
        """Compute embedding distance between states."""
        if s1.text == s2.text:
            return 0.0

        self._ensure_model()

        import numpy as np

        # Get embeddings
        emb1 = self._model.encode(s1.text)
        emb2 = self._model.encode(s2.text)

        if self._use_cosine:
            # Cosine distance = 1 - cosine_similarity
            sim = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
            return 1.0 - sim
        else:
            # L2 distance
            return np.linalg.norm(emb1 - emb2)


class LLMMorphism:
    """
    Kleisli morphism wrapping LLM API calls.

    Maps TextState → Distribution[TextState] via LLM generation.

    For deterministic temperature=0, returns Dirac delta.
    For temperature > 0, could sample multiple times for distribution.

    Args:
        client: Anthropic client instance
        prompt_template: Template with {text} placeholder
        model: Model name (default: claude-haiku-4-5-20251001)
        temperature: Sampling temperature
        lipschitz_estimate: Empirical L value (typically 1.1-1.3 for LLMs)
        max_tokens: Maximum response tokens
    """

    def __init__(
        self,
        client,  # anthropic.Anthropic
        prompt_template: str,
        model: str = "claude-haiku-4-5-20251001",
        temperature: float = 0.7,
        lipschitz_estimate: float = 1.1,
        max_tokens: int = 1024,
    ):
        self._client = client
        self._prompt = prompt_template
        self._model = model
        self._temperature = temperature
        self._L = lipschitz_estimate
        self._max_tokens = max_tokens

    def __call__(self, state: TextState) -> Distribution[TextState]:
        """
        Apply LLM transformation to state.

        Returns Dirac delta (single sample) for simplicity.
        """
        prompt = self._prompt.format(text=state.text)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            new_text = response.content[0].text.strip()
            new_state = TextState(text=new_text, facts=state.facts)

            return {new_state: 1.0}

        except Exception as e:
            # On error, return original state
            return {state: 1.0}

    @property
    def lipschitz_degree(self) -> float:
        return self._L

    def to_lipschitz_morphism(self, name: Optional[str] = None) -> LipschitzMorphism:
        """Convert to LipschitzMorphism wrapper."""
        return LipschitzMorphism(
            morphism=self,
            lipschitz_degree=self._L,
            name=name or "LLMMorphism",
        )


class FactCheckValidator(Validator):
    """
    Validator for fact preservation in LLM chains.

    Paper v7.0, Section 6.3: Fact-checking as γ-contractive map.

    Mechanism:
    1. LLM judge compares output facts against ground truth
    2. If accuracy < threshold: trigger retry
    3. Contraction γ ≈ threshold (empirically 0.8-0.9)

    Args:
        client: Anthropic client instance
        ground_truth_facts: List of facts that must be preserved
        threshold: Minimum accuracy to pass (default 0.8)
        max_retries: Maximum retry attempts (default 3)
        model: Model for fact-checking (default: claude-haiku-4-5-20251001)
    """

    def __init__(
        self,
        client,  # anthropic.Anthropic
        ground_truth_facts: list[str],
        threshold: float = 0.8,
        max_retries: int = 3,
        model: str = "claude-haiku-4-5-20251001",
    ):
        self._client = client
        self._facts = ground_truth_facts
        self._threshold = threshold
        self._max_retries = max_retries
        self._model = model
        self._gamma = threshold  # γ ≈ threshold

    def __call__(self, dist: Distribution[TextState]) -> Distribution[TextState]:
        """Apply fact-check validation with retry."""
        result = {}

        for state, prob in dist.items():
            validated = self._validate_with_retry(state)
            result[validated] = result.get(validated, 0.0) + prob

        return result

    def _validate_with_retry(self, state: TextState) -> TextState:
        """Check facts, retry if below threshold."""
        current = state

        for attempt in range(self._max_retries + 1):
            accuracy = self._check_accuracy(current)

            if accuracy >= self._threshold:
                return current

            if attempt < self._max_retries:
                # Request correction
                current = self._request_correction(current)

        return current  # Return best effort

    def _check_accuracy(self, state: TextState) -> float:
        """LLM judge: what fraction of facts preserved?"""
        prompt = f"""Check if these facts are preserved in the text below.

Facts to verify:
{json.dumps(self._facts, indent=2)}

Text to check:
{state.text}

Respond with JSON only:
{{"preserved": ["fact1", "fact2", ...], "missing": ["fact3", ...], "accuracy": 0.0-1.0}}"""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()

            # Parse JSON response
            # Handle potential markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            result = json.loads(text)
            return float(result.get("accuracy", 0.0))

        except Exception:
            return 0.0  # Assume failure on error

    def _request_correction(self, state: TextState) -> TextState:
        """Ask LLM to correct factual errors."""
        prompt = f"""The following text is missing or misrepresenting some facts.
Please rewrite to preserve ALL these facts while keeping the style:

Required facts:
{json.dumps(self._facts, indent=2)}

Text to fix:
{state.text}

Rewritten text:"""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            new_text = response.content[0].text.strip()
            return TextState(text=new_text, facts=state.facts)

        except Exception:
            return state

    def contraction_degree(self) -> float:
        return self._gamma


class IdentityLLMValidator(Validator):
    """No-op validator for LLM chains (γ = 1)."""

    def __call__(self, dist: Distribution[TextState]) -> Distribution[TextState]:
        return dict(dist)

    def contraction_degree(self) -> float:
        return 1.0


def run_fact_drift_experiment(
    client,
    facts: list[str],
    chain_length: int = 10,
    with_validator: bool = True,
    temperature: float = 0.7,
    threshold: float = 0.8,
    lipschitz_estimate: float = 1.1,
) -> dict:
    """
    Reproduce fact-drift experiment from Paper v7.0, Section 6.3.

    Args:
        client: Anthropic client
        facts: List of facts to preserve
        chain_length: Number of paraphrase steps
        with_validator: Whether to apply FactCheckValidator
        temperature: LLM sampling temperature
        threshold: Fact-check accuracy threshold
        lipschitz_estimate: Estimated L for paraphraser

    Returns:
        dict with experiment results
    """
    from gfso.engine.executor import GFSOEngine
    from gfso.core.graph import TaskDAG

    # Initial state
    initial_text = " ".join(facts)
    initial = TextState(text=initial_text, facts=tuple(facts))

    # Morphism (paraphraser)
    morphism = LLMMorphism(
        client,
        prompt_template="Paraphrase the following while preserving all meaning:\n{text}",
        temperature=temperature,
        lipschitz_estimate=lipschitz_estimate,
    ).to_lipschitz_morphism("paraphraser")

    # Validator
    if with_validator:
        validator = FactCheckValidator(client, facts, threshold=threshold)
    else:
        validator = IdentityLLMValidator()

    # Stability check
    L = lipschitz_estimate
    gamma = validator.contraction_degree()
    product = L * gamma
    is_stable = product <= 1.0

    print(f"Stability analysis: L={L:.2f}, γ={gamma:.2f}, L·γ={product:.2f}")
    print(f"Regime: {'STABLE' if is_stable else 'UNSTABLE'}")

    # Execute chain (simplified - direct execution)
    current = initial
    trajectory = [current]
    accuracies = []

    for step in range(chain_length):
        # Apply morphism
        dist = morphism(current)
        current = list(dist.keys())[0]  # Take single sample

        # Apply validator
        validated_dist = validator({current: 1.0})
        current = list(validated_dist.keys())[0]

        trajectory.append(current)

        # Measure accuracy
        acc = _measure_fact_accuracy(client, current.text, facts)
        accuracies.append(acc)

    return {
        "final_text": current.text,
        "final_accuracy": accuracies[-1] if accuracies else 1.0,
        "accuracy_trajectory": accuracies,
        "stability": {
            "L": L,
            "gamma": gamma,
            "product": product,
            "is_stable": is_stable,
        },
        "chain_length": chain_length,
        "with_validator": with_validator,
    }


def _measure_fact_accuracy(client, text: str, facts: list[str]) -> float:
    """Measure fact preservation accuracy."""
    prompt = f"""Check what fraction of these facts are accurately preserved in the text.

Facts:
{json.dumps(facts, indent=2)}

Text:
{text}

Return only a number between 0.0 and 1.0:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=32,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        return float(text)

    except Exception:
        return 0.0
