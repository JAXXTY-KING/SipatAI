import numpy as np

from ml.susceptibility.features import (
    FEATURE_NAMES,
    PERMANENT_WATER_OCCURRENCE,
    build_features,
    history_labels,
)
from ml.susceptibility.train import auc, is_holdout


def _valley():
    """A synthetic 512 x 512 valley: a river along the middle, land rising to a ridge on both sides."""
    columns = np.abs(np.arange(512) - 256).astype(np.float32)
    elevation = np.tile(2.0 + columns * 0.5, (512, 1))
    occurrence = np.zeros((512, 512), dtype=np.float32)
    occurrence[:, 254:258] = 95.0
    return elevation, occurrence


def test_features_follow_the_documented_channels_and_ranges():
    elevation, occurrence = _valley()
    features = build_features(elevation, occurrence)
    assert features.shape == (len(FEATURE_NAMES), 512, 512)
    assert features.min() >= 0.0 and features.max() <= 1.0 + 1e-6
    distance = features[FEATURE_NAMES.index("distance_to_permanent_water")]
    assert distance[:, 256].max() < distance[:, 10].min()  # nearer the river means a smaller distance
    relief = features[FEATURE_NAMES.index("relief_3km")]
    assert relief[:, 256].mean() < relief[:, 100].mean()  # the valley floor has less relief than its slopes


def test_history_labels_separate_temporary_water_from_dry_and_permanent_land():
    elevation = np.full((2, 4), 10.0, dtype=np.float32)
    occurrence = np.array([[0, 20, 90, np.nan], [1, 59, 60, 3]], dtype=np.float32)
    labels = history_labels(occurrence, elevation)
    assert labels.tolist() == [[0, 1, -1, -1], [0, 1, -1, 1]]
    assert PERMANENT_WATER_OCCURRENCE > 60  # permanent water is never labelled as temporary


def test_auc_and_holdout_split_are_well_behaved():
    scores = np.array([0.1, 0.2, 0.8, 0.9])
    assert auc(scores, np.array([0, 0, 1, 1])) == 1.0
    assert auc(scores, np.array([1, 1, 0, 0])) == 0.0
    assert is_holdout("Pampanga") == is_holdout("Pampanga")
    assert 5 < sum(is_holdout(name) for name in (f"province-{i}" for i in range(100))) < 40
