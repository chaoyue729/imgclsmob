"""
    ResNet, implemented in Gluon.
    Original paper: 'Deep Residual Learning for Image Recognition'
"""

from mxnet import cpu
from mxnet.gluon import nn, HybridBlock


class ResConv(HybridBlock):

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size,
                 strides,
                 padding,
                 bn_use_global_stats,
                 activate,
                 **kwargs):
        super(ResConv, self).__init__(**kwargs)
        self.activate = activate

        with self.name_scope():
            self.conv = nn.Conv2D(
                channels=out_channels,
                kernel_size=kernel_size,
                strides=strides,
                padding=padding,
                use_bias=False,
                in_channels=in_channels)
            self.bn = nn.BatchNorm(
                in_channels=out_channels,
                use_global_stats=bn_use_global_stats)
            if self.activate:
                self.activ = nn.Activation('relu')

    def hybrid_forward(self, F, x):
        x = self.conv(x)
        x = self.bn(x)
        if self.activate:
            x = self.activ(x)
        return x


def res_conv1x1(in_channels,
                out_channels,
                strides,
                bn_use_global_stats,
                activate):
    return ResConv(
        in_channels=in_channels,
        out_channels=out_channels,
        kernel_size=1,
        strides=strides,
        padding=0,
        bn_use_global_stats=bn_use_global_stats,
        activate=activate)


def res_conv3x3(in_channels,
                out_channels,
                strides,
                bn_use_global_stats,
                activate):
    return ResConv(
        in_channels=in_channels,
        out_channels=out_channels,
        kernel_size=3,
        strides=strides,
        padding=1,
        bn_use_global_stats=bn_use_global_stats,
        activate=activate)


class ResBlock(HybridBlock):

    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 bn_use_global_stats,
                 **kwargs):
        super(ResBlock, self).__init__(**kwargs)
        with self.name_scope():
            self.conv1 = res_conv3x3(
                in_channels=in_channels,
                out_channels=out_channels,
                strides=strides,
                bn_use_global_stats=bn_use_global_stats,
                activate=True)
            self.conv2 = res_conv3x3(
                in_channels=out_channels,
                out_channels=out_channels,
                strides=1,
                bn_use_global_stats=bn_use_global_stats,
                activate=False)

    def hybrid_forward(self, F, x):
        x = self.conv1(x)
        x = self.conv2(x)
        return x


class ResBottleneck(HybridBlock):

    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 bn_use_global_stats,
                 conv1_stride,
                 **kwargs):
        super(ResBottleneck, self).__init__(**kwargs)
        mid_channels = out_channels // 4

        with self.name_scope():
            self.conv1 = res_conv1x1(
                in_channels=in_channels,
                out_channels=mid_channels,
                strides=(strides if conv1_stride else 1),
                bn_use_global_stats=bn_use_global_stats,
                activate=True)
            self.conv2 = res_conv3x3(
                in_channels=mid_channels,
                out_channels=mid_channels,
                strides=(1 if conv1_stride else strides),
                bn_use_global_stats=bn_use_global_stats,
                activate=True)
            self.conv3 = res_conv1x1(
                in_channels=mid_channels,
                out_channels=out_channels,
                strides=1,
                bn_use_global_stats=bn_use_global_stats,
                activate=False)

    def hybrid_forward(self, F, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        return x


class ResUnit(HybridBlock):

    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 bn_use_global_stats,
                 bottleneck,
                 conv1_stride,
                 **kwargs):
        super(ResUnit, self).__init__(**kwargs)
        self.resize_identity = (in_channels != out_channels) or (strides != 1)

        with self.name_scope():
            if bottleneck:
                self.body = ResBottleneck(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    strides=strides,
                    bn_use_global_stats=bn_use_global_stats,
                    conv1_stride=conv1_stride)
            else:
                self.body = ResBlock(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    strides=strides,
                    bn_use_global_stats=bn_use_global_stats)
            if self.resize_identity:
                self.identity_conv = res_conv1x1(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    strides=strides,
                    bn_use_global_stats=bn_use_global_stats,
                    activate=False)
            self.activ = nn.Activation('relu')

    def hybrid_forward(self, F, x):
        if self.resize_identity:
            identity = self.identity_conv(x)
        else:
            identity = x
        x = self.body(x)
        x = x + identity
        x = self.activ(x)
        return x


class ResInitBlock(HybridBlock):

    def __init__(self,
                 in_channels,
                 out_channels,
                 bn_use_global_stats,
                 **kwargs):
        super(ResInitBlock, self).__init__(**kwargs)
        with self.name_scope():
            self.conv = ResConv(
                in_channels=in_channels,
                out_channels=out_channels,
                kernel_size=7,
                strides=2,
                padding=3,
                bn_use_global_stats=bn_use_global_stats,
                activate=True)
            self.pool = nn.MaxPool2D(
                pool_size=3,
                strides=2,
                padding=1)

    def hybrid_forward(self, F, x):
        x = self.conv(x)
        x = self.pool(x)
        return x


class ResNet(HybridBlock):

    def __init__(self,
                 channels,
                 init_block_channels,
                 bottleneck,
                 conv1_stride,
                 bn_use_global_stats=False,
                 in_channels=3,
                 classes=1000,
                 **kwargs):
        super(ResNet, self).__init__(**kwargs)

        with self.name_scope():
            self.features = nn.HybridSequential(prefix='')
            self.features.add(ResInitBlock(
                in_channels=in_channels,
                out_channels=init_block_channels,
                bn_use_global_stats=bn_use_global_stats))
            in_channels = init_block_channels
            for i, channels_per_stage in enumerate(channels):
                stage = nn.HybridSequential(prefix='stage{}_'.format(i + 1))
                with stage.name_scope():
                    for j, out_channels in enumerate(channels_per_stage):
                        strides = 2 if (j == 0) and (i != 0) else 1
                        stage.add(ResUnit(
                            in_channels=in_channels,
                            out_channels=out_channels,
                            strides=strides,
                            bn_use_global_stats=bn_use_global_stats,
                            bottleneck=bottleneck,
                            conv1_stride=conv1_stride))
                        in_channels = out_channels
                self.features.add(stage)
            self.features.add(nn.AvgPool2D(
                pool_size=7,
                strides=1))

            self.output = nn.HybridSequential(prefix='')
            self.output.add(nn.Flatten())
            self.output.add(nn.Dense(
                units=classes,
                in_units=in_channels))

    def hybrid_forward(self, F, x):
        x = self.features(x)
        x = self.output(x)
        return x


def get_resnet(blocks,
               conv1_stride=True,
               width_scale=1.0,
               pretrained=False,
               ctx=cpu(),
               **kwargs):
    if blocks == 10:
        layers = [1, 1, 1, 1]
    elif blocks == 12:
        layers = [2, 1, 1, 1]
    elif blocks == 14:
        layers = [2, 2, 1, 1]
    elif blocks == 16:
        layers = [2, 2, 2, 1]
    elif blocks == 18:
        layers = [2, 2, 2, 2]
    elif blocks == 34:
        layers = [3, 4, 6, 3]
    elif blocks == 50:
        layers = [3, 4, 6, 3]
    elif blocks == 101:
        layers = [3, 4, 23, 3]
    elif blocks == 152:
        layers = [3, 8, 36, 3]
    elif blocks == 200:
        layers = [3, 24, 36, 3]
    else:
        raise ValueError("Unsupported ResNet with number of blocks: {}".format(blocks))

    init_block_channels = 64

    if blocks < 50:
        channels_per_layers = [64, 128, 256, 512]
        bottleneck = False
    else:
        channels_per_layers = [256, 512, 1024, 2048]
        bottleneck = True

    channels = [[ci] * li for (ci, li) in zip(channels_per_layers, layers)]

    if width_scale != 1.0:
        channels = [[int(cij * width_scale) for cij in ci] for ci in channels]
        init_block_channels = int(init_block_channels * width_scale)

    if pretrained:
        raise ValueError("Pretrained model is not supported")

    return ResNet(
        channels=channels,
        init_block_channels=init_block_channels,
        bottleneck=bottleneck,
        conv1_stride=conv1_stride,
        **kwargs)


def resnet10(**kwargs):
    return get_resnet(blocks=10, **kwargs)


def resnet12(**kwargs):
    return get_resnet(blocks=12, **kwargs)


def resnet14(**kwargs):
    return get_resnet(blocks=14, **kwargs)


def resnet16(**kwargs):
    return get_resnet(blocks=16, **kwargs)


def resnet18(**kwargs):
    return get_resnet(blocks=18, **kwargs)


def resnet18_w3d4(**kwargs):
    return get_resnet(blocks=18, width_scale=0.75, **kwargs)


def resnet18_wd2(**kwargs):
    return get_resnet(blocks=18, width_scale=0.5, **kwargs)


def resnet18_wd4(**kwargs):
    return get_resnet(blocks=18, width_scale=0.25, **kwargs)


def resnet34(**kwargs):
    return get_resnet(blocks=34, **kwargs)


def resnet50(**kwargs):
    return get_resnet(blocks=50, **kwargs)


def resnet50b(**kwargs):
    return get_resnet(blocks=50, conv1_stride=False, **kwargs)


def resnet101(**kwargs):
    return get_resnet(blocks=101, **kwargs)


def resnet101b(**kwargs):
    return get_resnet(blocks=101, conv1_stride=False, **kwargs)


def resnet152(**kwargs):
    return get_resnet(blocks=152, **kwargs)


def resnet152b(**kwargs):
    return get_resnet(blocks=152, conv1_stride=False, **kwargs)


def resnet200(**kwargs):
    return get_resnet(blocks=200, **kwargs)


def resnet200b(**kwargs):
    return get_resnet(blocks=200, conv1_stride=False, **kwargs)


def _test():
    import numpy as np
    import mxnet as mx

    global TESTING
    TESTING = True

    models = [
        resnet18,
        resnet34,
        resnet50,
        resnet50b,
        resnet101,
        resnet101b,
        resnet152,
        resnet152b,
    ]

    for model in models:

        net = model()

        ctx = mx.cpu()
        net.initialize(ctx=ctx)

        net_params = net.collect_params()
        weight_count = 0
        for param in net_params.values():
            if (param.shape is None) or (not param._differentiable):
                continue
            weight_count += np.prod(param.shape)
        assert (model != resnet18 or weight_count == 11689512)  # resnet18_v1
        assert (model != resnet34 or weight_count == 21797672)  # resnet34_v1
        assert (model != resnet50 or weight_count == 25557032)  # resnet50_v1b; resnet50_v1 -> 25575912
        assert (model != resnet50b or weight_count == 25557032)  # resnet50_v1b; resnet50_v1 -> 25575912
        assert (model != resnet101 or weight_count == 44549160)  # resnet101_v1b
        assert (model != resnet101b or weight_count == 44549160)  # resnet101_v1b
        assert (model != resnet152 or weight_count == 60192808)  # resnet152_v1b
        assert (model != resnet152b or weight_count == 60192808)  # resnet152_v1b

        x = mx.nd.zeros((1, 3, 224, 224), ctx=ctx)
        y = net(x)
        assert (y.shape == (1, 1000))


if __name__ == "__main__":
    _test()

