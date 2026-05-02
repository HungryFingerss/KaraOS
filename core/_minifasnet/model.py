# MiniFASNet architecture — vendored from minivision-ai/Silent-Face-Anti-Spoofing
# Original source: src/model_lib/MiniFASNet.py, Copyright (c) 2020 Minivision, MIT License.
# Only cosmetic changes here (add load_pretrained helper). Do not modify architecture
# — loaded state_dicts assume these exact layer names and shapes.
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import torch
import torch.nn.functional as F
from torch.nn import (
    Linear, Conv2d, BatchNorm1d, BatchNorm2d, PReLU, ReLU, Sigmoid,
    AdaptiveAvgPool2d, Sequential, Module,
)


class L2Norm(Module):
    def forward(self, input):
        return F.normalize(input)


class Flatten(Module):
    def forward(self, input):
        return input.view(input.size(0), -1)


class Conv_block(Module):
    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        super().__init__()
        self.conv = Conv2d(in_c, out_c, kernel_size=kernel, groups=groups,
                           stride=stride, padding=padding, bias=False)
        self.bn = BatchNorm2d(out_c)
        self.prelu = PReLU(out_c)

    def forward(self, x):
        x = self.conv(x)
        x = self.bn(x)
        x = self.prelu(x)
        return x


class Linear_block(Module):
    def __init__(self, in_c, out_c, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        super().__init__()
        self.conv = Conv2d(in_c, out_channels=out_c, kernel_size=kernel,
                           groups=groups, stride=stride, padding=padding, bias=False)
        self.bn = BatchNorm2d(out_c)

    def forward(self, x):
        x = self.conv(x)
        x = self.bn(x)
        return x


class Depth_Wise(Module):
    def __init__(self, c1, c2, c3, residual=False, kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=1):
        super().__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = Conv_block(c1_in, out_c=c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = Linear_block(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual

    def forward(self, x):
        if self.residual:
            short_cut = x
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)
        if self.residual:
            output = short_cut + x
        else:
            output = x
        return output


class Residual(Module):
    def __init__(self, c1, c2, c3, num_block, groups, kernel=(3, 3), stride=(1, 1), padding=(1, 1)):
        super().__init__()
        modules = []
        for i in range(num_block):
            modules.append(Depth_Wise(c1[i], c2[i], c3[i], residual=True,
                                      kernel=kernel, padding=padding, stride=stride, groups=groups))
        self.model = Sequential(*modules)

    def forward(self, x):
        return self.model(x)


class SEModule(Module):
    def __init__(self, channels, reduction):
        super().__init__()
        self.avg_pool = AdaptiveAvgPool2d(1)
        self.fc1 = Conv2d(channels, channels // reduction, kernel_size=1, padding=0, bias=False)
        self.bn1 = BatchNorm2d(channels // reduction)
        self.relu = ReLU(inplace=True)
        self.fc2 = Conv2d(channels // reduction, channels, kernel_size=1, padding=0, bias=False)
        self.bn2 = BatchNorm2d(channels)
        self.sigmoid = Sigmoid()

    def forward(self, x):
        module_input = x
        x = self.avg_pool(x)
        x = self.fc1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.fc2(x)
        x = self.bn2(x)
        x = self.sigmoid(x)
        return module_input * x


class Depth_Wise_SE(Module):
    def __init__(self, c1, c2, c3, residual=False, kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=1, se_reduct=8):
        super().__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = Conv_block(c1_in, out_c=c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = Conv_block(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = Linear_block(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual
        self.se_module = SEModule(c3_out, se_reduct)

    def forward(self, x):
        if self.residual:
            short_cut = x
        x = self.conv(x)
        x = self.conv_dw(x)
        x = self.project(x)
        if self.residual:
            x = self.se_module(x)
            output = short_cut + x
        else:
            output = x
        return output


class ResidualSE(Module):
    def __init__(self, c1, c2, c3, num_block, groups, kernel=(3, 3), stride=(1, 1), padding=(1, 1), se_reduct=4):
        super().__init__()
        modules = []
        for i in range(num_block):
            if i == num_block - 1:
                modules.append(Depth_Wise_SE(c1[i], c2[i], c3[i], residual=True, kernel=kernel,
                                             padding=padding, stride=stride, groups=groups, se_reduct=se_reduct))
            else:
                modules.append(Depth_Wise(c1[i], c2[i], c3[i], residual=True, kernel=kernel,
                                          padding=padding, stride=stride, groups=groups))
        self.model = Sequential(*modules)

    def forward(self, x):
        return self.model(x)


class MiniFASNet(Module):
    def __init__(self, keep, embedding_size, conv6_kernel=(7, 7),
                 drop_p=0.0, num_classes=3, img_channel=3):
        super().__init__()
        self.embedding_size = embedding_size

        self.conv1 = Conv_block(img_channel, keep[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1))
        self.conv2_dw = Conv_block(keep[0], keep[1], kernel=(3, 3), stride=(1, 1), padding=(1, 1), groups=keep[1])

        c1 = [(keep[1], keep[2])]; c2 = [(keep[2], keep[3])]; c3 = [(keep[3], keep[4])]
        self.conv_23 = Depth_Wise(c1[0], c2[0], c3[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[3])

        c1 = [(keep[4], keep[5]), (keep[7], keep[8]), (keep[10], keep[11]), (keep[13], keep[14])]
        c2 = [(keep[5], keep[6]), (keep[8], keep[9]), (keep[11], keep[12]), (keep[14], keep[15])]
        c3 = [(keep[6], keep[7]), (keep[9], keep[10]), (keep[12], keep[13]), (keep[15], keep[16])]
        self.conv_3 = Residual(c1, c2, c3, num_block=4, groups=keep[4], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[16], keep[17])]; c2 = [(keep[17], keep[18])]; c3 = [(keep[18], keep[19])]
        self.conv_34 = Depth_Wise(c1[0], c2[0], c3[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[19])

        c1 = [(keep[19], keep[20]), (keep[22], keep[23]), (keep[25], keep[26]),
              (keep[28], keep[29]), (keep[31], keep[32]), (keep[34], keep[35])]
        c2 = [(keep[20], keep[21]), (keep[23], keep[24]), (keep[26], keep[27]),
              (keep[29], keep[30]), (keep[32], keep[33]), (keep[35], keep[36])]
        c3 = [(keep[21], keep[22]), (keep[24], keep[25]), (keep[27], keep[28]),
              (keep[30], keep[31]), (keep[33], keep[34]), (keep[36], keep[37])]
        self.conv_4 = Residual(c1, c2, c3, num_block=6, groups=keep[19], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[37], keep[38])]; c2 = [(keep[38], keep[39])]; c3 = [(keep[39], keep[40])]
        self.conv_45 = Depth_Wise(c1[0], c2[0], c3[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[40])

        c1 = [(keep[40], keep[41]), (keep[43], keep[44])]
        c2 = [(keep[41], keep[42]), (keep[44], keep[45])]
        c3 = [(keep[42], keep[43]), (keep[45], keep[46])]
        self.conv_5 = Residual(c1, c2, c3, num_block=2, groups=keep[40], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        self.conv_6_sep = Conv_block(keep[46], keep[47], kernel=(1, 1), stride=(1, 1), padding=(0, 0))
        self.conv_6_dw = Linear_block(keep[47], keep[48], groups=keep[48], kernel=conv6_kernel,
                                      stride=(1, 1), padding=(0, 0))
        self.conv_6_flatten = Flatten()
        self.linear = Linear(512, embedding_size, bias=False)
        self.bn = BatchNorm1d(embedding_size)
        self.drop = torch.nn.Dropout(p=drop_p)
        self.prob = Linear(embedding_size, num_classes, bias=False)

    def forward(self, x):
        out = self.conv1(x)
        out = self.conv2_dw(out)
        out = self.conv_23(out)
        out = self.conv_3(out)
        out = self.conv_34(out)
        out = self.conv_4(out)
        out = self.conv_45(out)
        out = self.conv_5(out)
        out = self.conv_6_sep(out)
        out = self.conv_6_dw(out)
        out = self.conv_6_flatten(out)
        if self.embedding_size != 512:
            out = self.linear(out)
        out = self.bn(out)
        out = self.drop(out)
        out = self.prob(out)
        return out


class MiniFASNetSE(MiniFASNet):
    def __init__(self, keep, embedding_size, conv6_kernel=(7, 7), drop_p=0.75, num_classes=4, img_channel=3):
        super().__init__(keep=keep, embedding_size=embedding_size, conv6_kernel=conv6_kernel,
                         drop_p=drop_p, num_classes=num_classes, img_channel=img_channel)

        c1 = [(keep[4], keep[5]), (keep[7], keep[8]), (keep[10], keep[11]), (keep[13], keep[14])]
        c2 = [(keep[5], keep[6]), (keep[8], keep[9]), (keep[11], keep[12]), (keep[14], keep[15])]
        c3 = [(keep[6], keep[7]), (keep[9], keep[10]), (keep[12], keep[13]), (keep[15], keep[16])]
        self.conv_3 = ResidualSE(c1, c2, c3, num_block=4, groups=keep[4], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[19], keep[20]), (keep[22], keep[23]), (keep[25], keep[26]),
              (keep[28], keep[29]), (keep[31], keep[32]), (keep[34], keep[35])]
        c2 = [(keep[20], keep[21]), (keep[23], keep[24]), (keep[26], keep[27]),
              (keep[29], keep[30]), (keep[32], keep[33]), (keep[35], keep[36])]
        c3 = [(keep[21], keep[22]), (keep[24], keep[25]), (keep[27], keep[28]),
              (keep[30], keep[31]), (keep[33], keep[34]), (keep[36], keep[37])]
        self.conv_4 = ResidualSE(c1, c2, c3, num_block=6, groups=keep[19], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[40], keep[41]), (keep[43], keep[44])]
        c2 = [(keep[41], keep[42]), (keep[44], keep[45])]
        c3 = [(keep[42], keep[43]), (keep[45], keep[46])]
        self.conv_5 = ResidualSE(c1, c2, c3, num_block=2, groups=keep[40], kernel=(3, 3), stride=(1, 1), padding=(1, 1))


keep_dict = {
    '1.8M':  [32, 32, 103, 103, 64, 13, 13, 64, 26, 26,
              64, 13, 13, 64, 52, 52, 64, 231, 231, 128,
              154, 154, 128, 52, 52, 128, 26, 26, 128, 52,
              52, 128, 26, 26, 128, 26, 26, 128, 308, 308,
              128, 26, 26, 128, 26, 26, 128, 512, 512],
    '1.8M_': [32, 32, 103, 103, 64, 13, 13, 64, 13, 13, 64, 13,
              13, 64, 13, 13, 64, 231, 231, 128, 231, 231, 128, 52,
              52, 128, 26, 26, 128, 77, 77, 128, 26, 26, 128, 26, 26,
              128, 308, 308, 128, 26, 26, 128, 26, 26, 128, 512, 512],
}


def MiniFASNetV2(embedding_size=128, conv6_kernel=(7, 7), drop_p=0.2, num_classes=3, img_channel=3):
    return MiniFASNet(keep_dict['1.8M_'], embedding_size, conv6_kernel, drop_p, num_classes, img_channel)


def MiniFASNetV1SE(embedding_size=128, conv6_kernel=(7, 7), drop_p=0.75, num_classes=3, img_channel=3):
    return MiniFASNetSE(keep_dict['1.8M'], embedding_size, conv6_kernel, drop_p, num_classes, img_channel)


def _parse_model_filename(name: str) -> tuple[int, int, str, float]:
    """Extract (h, w, model_type, scale) from upstream weights filename convention
    e.g. '2.7_80x80_MiniFASNetV2.pth' → (80, 80, 'MiniFASNetV2', 2.7)."""
    info = name.split('_')[0:-1]
    h_input, w_input = info[-1].split('x')
    model_type = name.split('.pth')[0].split('_')[-1]
    scale = float(info[0]) if info[0] != "org" else None
    return int(h_input), int(w_input), model_type, scale


def _get_kernel(height: int, width: int) -> tuple[int, int]:
    """conv6_kernel inferred from input size (ceil-div by 16)."""
    return ((height + 15) // 16, (width + 15) // 16)


_MODEL_FACTORY = {
    "MiniFASNetV2":   MiniFASNetV2,
    "MiniFASNetV1SE": MiniFASNetV1SE,
}


def load_pretrained(weight_path: "str | Path", device: torch.device) -> "tuple[Module, float]":
    """Load a .pth weight file and return (ready-for-eval model, crop scale).

    The scale is parsed from the filename (e.g. '2.7_80x80_MiniFASNetV2.pth' → 2.7),
    and is used by the caller to control how much padding around the face the crop
    should include before resizing to 80x80.
    """
    p = Path(weight_path)
    h_input, w_input, model_type, scale = _parse_model_filename(p.name)
    if model_type not in _MODEL_FACTORY:
        raise ValueError(
            f"Unknown MiniFASNet variant '{model_type}' in {p.name}. "
            f"Known: {sorted(_MODEL_FACTORY)}"
        )
    model = _MODEL_FACTORY[model_type](conv6_kernel=_get_kernel(h_input, w_input)).to(device)

    # load_weights — also tolerate DataParallel checkpoints with the 'module.' prefix
    state_dict = torch.load(str(p), map_location=device, weights_only=True)
    keys: Iterator[str] = iter(state_dict)
    first = next(keys)
    if first.startswith("module."):
        state_dict = {k[len("module."):]: v for k, v in state_dict.items()}
    model.load_state_dict(state_dict)
    model.eval()
    return model, scale
