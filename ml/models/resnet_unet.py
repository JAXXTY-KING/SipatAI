from mindspore import nn, ops

from ml.configs.model_config import CLASS_COUNT, INPUT_CHANNEL_COUNT


class ConvNormRelu(nn.Cell):
    """Two convolution blocks used by the U-Net decoder."""

    def __init__(self, input_channels: int, output_channels: int) -> None:
        super().__init__()
        self.layers = nn.SequentialCell(
            [
                nn.Conv2d(
                    input_channels,
                    output_channels,
                    kernel_size=3,
                    pad_mode="pad",
                    padding=1,
                    has_bias=False,
                ),
                nn.BatchNorm2d(output_channels),
                nn.ReLU(),
                nn.Conv2d(
                    output_channels,
                    output_channels,
                    kernel_size=3,
                    pad_mode="pad",
                    padding=1,
                    has_bias=False,
                ),
                nn.BatchNorm2d(output_channels),
                nn.ReLU(),
            ]
        )

    def construct(self, value):
        return self.layers(value)


class ResNetBottleneck(nn.Cell):
    expansion = 4

    def __init__(self, input_channels: int, channels: int, stride: int = 1) -> None:
        super().__init__()
        output_channels = channels * self.expansion
        self.conv1 = nn.Conv2d(input_channels, channels, kernel_size=1, has_bias=False)
        self.bn1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(
            channels,
            channels,
            kernel_size=3,
            stride=stride,
            pad_mode="pad",
            padding=1,
            has_bias=False,
        )
        self.bn2 = nn.BatchNorm2d(channels)
        self.conv3 = nn.Conv2d(channels, output_channels, kernel_size=1, has_bias=False)
        self.bn3 = nn.BatchNorm2d(output_channels)
        self.relu = nn.ReLU()
        self.shortcut = None

        if stride != 1 or input_channels != output_channels:
            self.shortcut = nn.SequentialCell(
                [
                    nn.Conv2d(
                        input_channels,
                        output_channels,
                        kernel_size=1,
                        stride=stride,
                        has_bias=False,
                    ),
                    nn.BatchNorm2d(output_channels),
                ]
            )

    def construct(self, value):
        residual = value if self.shortcut is None else self.shortcut(value)
        output = self.relu(self.bn1(self.conv1(value)))
        output = self.relu(self.bn2(self.conv2(output)))
        output = self.bn3(self.conv3(output))
        return self.relu(output + residual)


class ResNet50UNet(nn.Cell):
    """ResNet-50 encoder and U-Net decoder for two-class flood segmentation."""

    def __init__(self) -> None:
        super().__init__()
        self.input_channels = INPUT_CHANNEL_COUNT
        self.encoder_channels = 64
        self.conv1 = nn.Conv2d(
            self.input_channels,
            self.encoder_channels,
            kernel_size=7,
            stride=2,
            pad_mode="pad",
            padding=3,
            has_bias=False,
        )
        self.bn1 = nn.BatchNorm2d(self.encoder_channels)
        self.relu = nn.ReLU()
        self.max_pool = nn.MaxPool2d(kernel_size=3, stride=2, pad_mode="same")

        self.layer1 = self._make_layer(64, block_count=3, stride=1)
        self.layer2 = self._make_layer(128, block_count=4, stride=2)
        self.layer3 = self._make_layer(256, block_count=6, stride=2)
        self.layer4 = self._make_layer(512, block_count=3, stride=2)

        self.up4 = nn.Conv2dTranspose(2048, 512, kernel_size=2, stride=2, has_bias=False)
        self.decode4 = ConvNormRelu(512 + 1024, 512)
        self.up3 = nn.Conv2dTranspose(512, 256, kernel_size=2, stride=2, has_bias=False)
        self.decode3 = ConvNormRelu(256 + 512, 256)
        self.up2 = nn.Conv2dTranspose(256, 128, kernel_size=2, stride=2, has_bias=False)
        self.decode2 = ConvNormRelu(128 + 256, 128)
        self.up1 = nn.Conv2dTranspose(128, 64, kernel_size=2, stride=2, has_bias=False)
        self.decode1 = ConvNormRelu(64 + 64, 64)
        self.up0 = nn.Conv2dTranspose(64, 64, kernel_size=2, stride=2, has_bias=False)
        self.classifier = nn.Conv2d(64, CLASS_COUNT, kernel_size=1, has_bias=True)

    def _make_layer(self, channels: int, block_count: int, stride: int) -> nn.SequentialCell:
        layers = [ResNetBottleneck(self.encoder_channels, channels, stride)]
        self.encoder_channels = channels * ResNetBottleneck.expansion
        layers.extend(
            ResNetBottleneck(self.encoder_channels, channels)
            for _ in range(block_count - 1)
        )
        return nn.SequentialCell(layers)

    def construct(self, value):
        stem = self.relu(self.bn1(self.conv1(value)))
        encoded = self.max_pool(stem)
        skip1 = self.layer1(encoded)
        skip2 = self.layer2(skip1)
        skip3 = self.layer3(skip2)
        encoded = self.layer4(skip3)

        decoded = self.decode4(ops.concat((self.up4(encoded), skip3), axis=1))
        decoded = self.decode3(ops.concat((self.up3(decoded), skip2), axis=1))
        decoded = self.decode2(ops.concat((self.up2(decoded), skip1), axis=1))
        decoded = self.decode1(ops.concat((self.up1(decoded), stem), axis=1))
        return self.classifier(self.up0(decoded))
