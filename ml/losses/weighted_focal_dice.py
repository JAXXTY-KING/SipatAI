from mindspore import Tensor, nn, ops
import mindspore as ms

from ml.configs.model_config import CLASS_COUNT


class WeightedFocalDiceLoss(nn.Cell):
    """Combine class-weighted focal loss and soft Dice loss for segmentation."""

    def __init__(
        self,
        class_weights: tuple[float, ...],
        focal_gamma: float,
        dice_weight: float,
        smooth: float = 1e-6,
    ) -> None:
        super().__init__()
        if len(class_weights) != CLASS_COUNT:
            raise ValueError(f"Expected {CLASS_COUNT} class weights in configured class order.")
        if focal_gamma < 0 or dice_weight < 0 or smooth <= 0:
            raise ValueError("Loss parameters must be non-negative and smoothing must be positive.")

        self.class_weights = ops.reshape(
            Tensor(class_weights, ms.float32),
            (1, CLASS_COUNT, 1, 1),
        )
        self.focal_gamma = focal_gamma
        self.dice_weight = dice_weight
        self.smooth = smooth
        self.softmax = nn.Softmax(axis=1)
        self.on_value = Tensor(1.0, ms.float32)
        self.off_value = Tensor(0.0, ms.float32)

    def construct(self, logits, target):
        labels = ops.cast(target, ms.int32)
        # Pixels labelled -1 are "no data": they contribute to neither loss term.
        valid = ops.cast(labels >= 0, ms.float32)
        valid_channel = ops.expand_dims(valid, 1)
        safe_labels = labels * ops.cast(valid, ms.int32)
        one_hot_target = ops.one_hot(
            safe_labels,
            CLASS_COUNT,
            self.on_value,
            self.off_value,
            axis=1,
        ) * valid_channel
        probabilities = self.softmax(logits)
        clipped_probabilities = ops.clip_by_value(probabilities, 1e-7, 1.0)

        valid_pixels = ops.maximum(ops.sum(valid), 1.0)
        focal_loss = -ops.sum(
            one_hot_target
            * self.class_weights
            * ops.pow(1.0 - probabilities, self.focal_gamma)
            * ops.log(clipped_probabilities)
        ) / (valid_pixels * CLASS_COUNT)

        masked_probabilities = probabilities * valid_channel
        axes = (0, 2, 3)
        intersection = ops.sum(masked_probabilities * one_hot_target, dim=axes)
        cardinality = ops.sum(masked_probabilities + one_hot_target, dim=axes)
        dice_score = (2.0 * intersection + self.smooth) / (cardinality + self.smooth)
        dice_loss = 1.0 - ops.mean(dice_score)
        return focal_loss + self.dice_weight * dice_loss
