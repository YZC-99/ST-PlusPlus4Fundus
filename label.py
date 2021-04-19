from dataset.pascal import PASCAL
from model.deeplabv3plus import DeepLabV3Plus
from util.utils import color_map, count_params, meanIOU

import argparse
import numpy as np
import os
from PIL import Image
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser(description=
                                     'Semi-supervised Semantic Segmentation -- Testing(or Pseudo Labeling)')

    parser.add_argument('--data-root',
                        type=str,
                        default='/data/lihe/datasets/PASCAL-VOC-2012',
                        help='root path of training dataset')
    parser.add_argument('--dataset',
                        type=str,
                        default='pascal',
                        choices=['pascal'],
                        help='training dataset')
    parser.add_argument('--backbone',
                        type=str,
                        choices=['resnet50', 'resnet101'],
                        default='resnet50',
                        help='backbone of semantic segmentation model')
    parser.add_argument('--model',
                        type=str,
                        default='deeplabv3plus',
                        help='model for semantic segmentation')
    parser.add_argument('--load-from',
                        type=str,
                        default='',
                        help='path of trained model')
    parser.add_argument('--tta',
                        dest='tta',
                        default=False,
                        action='store_true',
                        help='whether to use tta (multi-scale testing and horizontal fliping)')
    parser.add_argument('--visualize',
                        dest='visualize',
                        default=False,
                        action='store_true',
                        help='whether to visualize pseudo masks along with groundtruth masks')
    parser.add_argument('--labeled-id-path',
                        type=str,
                        default='/data/lihe/datasets/PASCAL-VOC-2012/ImageSets/train.txt',
                        help='path of labeled image ids')

    args = parser.parse_args()
    return args


def label(dataloader, model, args):
    model.eval()
    tbar = tqdm(dataloader)

    metric = meanIOU(num_classes=len(dataloader.dataset.CLASSES))
    cmap = color_map()

    with torch.no_grad():
        for img, mask, id in tbar:
            img = img.cuda()
            pred = model(img, args.tta)
            pred = torch.argmax(pred, dim=1)

            metric.add_batch(pred.cpu().numpy(), mask.numpy())
            mIOU = metric.evaluate()[-1]

            pred = Image.fromarray(pred.squeeze(0).cpu().numpy().astype(np.uint8), mode='P')
            pred.putpalette(cmap)
            pred.save(os.path.join(args.data_root, 'PseudoLabel', id[0] + '.png'))

            if args.visualize:
                mask = Image.open(os.path.join(args.data_root, 'SegmentationClass', id[0] + '.png'))
                img = Image.open(os.path.join(args.data_root, 'JPEGImages', id[0] + '.jpg'))

                images = [img, mask, pred]

                widths, heights = zip(*(i.size for i in images))

                total_width = sum(widths) + 40
                max_height = max(heights)

                new_image = Image.new('RGB', (total_width, max_height), color=(255, 255, 255))

                x_offset = 0
                for im in images:
                    new_image.paste(im, (x_offset, 0))
                    x_offset += im.size[0] + 20

                new_image.save('outdir/masks/%s.jpg' % id[0])

            tbar.set_description('mIOU: %.2f' % (mIOU * 100.0))


if __name__ == '__main__':
    args = parse_args()

    if args.dataset == 'pascal':
        valset = PASCAL(args.data_root, 'label', None, args.train_split)
    valloader = DataLoader(valset, batch_size=1, shuffle=False,
                           pin_memory=True, num_workers=16, drop_last=False)

    if args.model == 'deeplabv3plus':
        model = DeepLabV3Plus(args.backbone, len(valset.CLASSES))
    print('\nParams: %.1fM\n' % count_params(model))

    model.load_state_dict(torch.load(args.load_from), strict=True)
    model = model.cuda()

    label(valloader, model, args)