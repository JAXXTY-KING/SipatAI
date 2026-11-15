INPUT_CHANNEL_ORDER = ("VV", "VH", "NDVI", "NDWI", "RED", "NIR")
INPUT_CHANNEL_COUNT = len(INPUT_CHANNEL_ORDER)
# Optical channels are unusable under cloud; those pixels are set to a value outside the real range
# (NDVI/NDWI in [-1, 1], reflectance in [0, 1]) so the network can learn to rely on radar alone.
OPTICAL_CHANNEL_INDEXES = (2, 3, 4, 5)
OPTICAL_MISSING_VALUE = -2.0
INPUT_SIZE = (512, 512)
CLASS_NAMES = ("not_flooded", "flooded")
CLASS_COUNT = len(CLASS_NAMES)
