"""Dataset loaders for GFSO experiments."""

from .base import Task, DatasetLoader
from .math_dataset import MATHLoader
from .bbh_dataset import BBHLoader
from .hle_dataset import HLELoader

# Registry of available loaders
DATASETS = {
    "math": MATHLoader,
    "bbh": BBHLoader,
    "hle": HLELoader,
}


def get_loader(name: str, **kwargs) -> DatasetLoader:
    """Get dataset loader by name.

    Args:
        name: Dataset name (math, bbh)
        **kwargs: Loader-specific arguments

    Returns:
        DatasetLoader instance
    """
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset: {name}. Available: {list(DATASETS.keys())}")
    return DATASETS[name](**kwargs)


__all__ = ["Task", "DatasetLoader", "MATHLoader", "BBHLoader", "get_loader", "DATASETS"]
