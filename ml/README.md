# MindSpore Model

The ML package contains a MindSpore 2.10.0 ResNet-50 U-Net for binary flood segmentation and a weighted focal plus Dice loss. The model input contract is `[batch, channels, height, width]`, with channels in the order declared once in `configs/model_config.py`: VV, VH, NDVI, NDWI, red, NIR. The output contains two class logits per pixel in the configured class order.

Input tiles are 512 by 512 pixels. Do not change their size, channel order, classes, or loss parameters without updating the shared training and inference configuration. The loss requires explicit class weights and focal/Dice parameters; this repository does not invent training values that the strategy report did not specify.

The model architecture is not trained and does not contain pretrained weights. Training requires labeled, aligned raster tiles and a confirmed hyperparameter configuration. Export requires a trained MindSpore checkpoint; the export script writes MindIR for deployment through Huawei ModelArts.

Training manifests are CSV files with `image_path` and `mask_path` columns. Each image path points to one NumPy tile shaped `[6, 512, 512]`; each mask path points to one integer-label tile shaped `[512, 512]`. Paths may be relative to the manifest. The dataset reads tiles on demand, not complete satellite scenes. The preprocessing pipeline that creates these aligned tiles is not implemented yet.

The local ML environment uses MindSpore 2.10.0 and NumPy 1.26.4. The latter avoids a binary compatibility warning in the Windows CPU runtime. The package was smoke-tested on CPU with a 64 by 64 input; full 512 by 512 training and Huawei Ascend execution still require validation on the selected ModelArts runtime.

Install the official MindSpore package for a supported platform and Python 3.10 through 3.12. The Windows x64 option is listed by MindSpore; production training and inference should use the compatible ModelArts runtime and hardware selected for deployment: https://www.mindspore.cn/install/en.
