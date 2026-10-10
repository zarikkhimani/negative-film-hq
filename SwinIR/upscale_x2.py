"""Upscale local photos using the official DF2K Classical SR x2 SwinIR."""
import argparse
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from main_test_swinir import define_model, test as run_inference
from download_model import MODEL

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}
OUTPUT_EXTENSIONS = {'tiff': '.tif', 'png': '.png'}


def select_files():
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    try:
        return filedialog.askopenfilenames(
            title='SwinIR Classical SR x2 - select photos',
            filetypes=[('Images', '*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp'),
                       ('All files', '*.*')])
    finally:
        root.destroy()


def collect_files(inputs):
    files = []
    for entry in inputs:
        path = Path(entry).expanduser().resolve()
        if path.is_dir():
            files.extend(sorted(p for p in path.iterdir()
                                if p.is_file() and p.suffix.lower() in EXTENSIONS))
        elif path.is_file() and path.suffix.lower() in EXTENSIONS:
            files.append(path)
        else:
            raise ValueError(f'Not a supported image or folder: {path}')
    return list(dict.fromkeys(files))


def read_image(path):
    # imdecode supports Windows filenames containing non-ASCII characters.
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f'Cannot decode image: {path}')
    if image.dtype not in (np.uint8, np.uint16):
        raise ValueError(f'Only 8-bit and 16-bit integer images are supported: {path}')
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f'Expected RGB or grayscale image without alpha: {path}')
    return image


def output_path(source, folder, output_format='tiff'):
    # Never overwrite an existing result or an original.
    extension = OUTPUT_EXTENSIONS[output_format]
    target = folder / f'{source.stem}_SwinIR_x2{extension}'
    number = 2
    while target.exists():
        target = folder / f'{source.stem}_SwinIR_x2_{number}{extension}'
        number += 1
    return target


def save_image(target, image):
    # Explicit LZW compression is lossless for both uint8 and uint16 RGB TIFFs.
    params = ([cv2.IMWRITE_TIFF_COMPRESSION, cv2.IMWRITE_TIFF_COMPRESSION_LZW]
              if target.suffix.lower() == '.tif' else [])
    success, encoded = cv2.imencode(target.suffix, image, params)
    if not success:
        raise RuntimeError(f'Failed to encode output: {target}')
    with target.open('xb') as destination:
        destination.write(encoded.tobytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='*', help='Image files or folders (nonrecursive)')
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    parser.add_argument('--format', choices=OUTPUT_EXTENSIONS, default='tiff',
                        help='Output format: tiff (default, lossless) or png; retains input bit depth')
    parser.add_argument('--tile', type=int, default=256, help='Multiple of 8; 0 processes the whole image')
    parser.add_argument('--tile-overlap', type=int, default=32)
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    args = parser.parse_args()
    if args.tile < 0 or args.tile % 8:
        parser.error('--tile must be 0 or a positive multiple of 8')
    if args.tile and not 0 <= args.tile_overlap < args.tile:
        parser.error('--tile-overlap must be nonnegative and smaller than --tile')
    entries = args.inputs or select_files()
    if not entries:
        print('No photos selected.')
        return
    files = collect_files(entries)
    if not files:
        raise ValueError('No supported images found in the selected folder(s).')
    if not MODEL.is_file():
        raise FileNotFoundError(f'Checkpoint missing: {MODEL}. Run download_model.py first.')
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable. Check the GPU environment, or explicitly use --device cpu.')
    device = torch.device(args.device)
    print(f'Model: {MODEL.name}', flush=True)
    print(f'Device: {torch.cuda.get_device_name(0) if device.type == "cuda" else "CPU"}', flush=True)
    print(f'Output format: {args.format.upper()}', flush=True)
    config = SimpleNamespace(task='classical_sr', scale=2, training_patch_size=64,
                             model_path=str(MODEL), tile=args.tile or None,
                             tile_overlap=args.tile_overlap)
    model = define_model(config).eval().to(device)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(files, 1):
        started = time.perf_counter()
        image = read_image(path)
        h, w = image.shape[:2]
        maximum = float(np.iinfo(image.dtype).max)
        rgb = np.ascontiguousarray(image[:, :, ::-1].transpose(2, 0, 1), dtype=np.float32) / maximum
        tensor = torch.from_numpy(rgb).unsqueeze(0).to(device)
        # Replication also supports very small photos; the model needs multiples of 8.
        pad_h, pad_w = (-h) % 8, (-w) % 8
        if pad_h or pad_w:
            tensor = F.pad(tensor, (0, pad_w, 0, pad_h), mode='replicate')
        actual_tile = min(args.tile, *tensor.shape[-2:]) if args.tile else 0
        if actual_tile and args.tile_overlap >= actual_tile:
            # A single tile needs no overlap. This avoids a zero or negative stride.
            config.tile_overlap = min(args.tile_overlap, actual_tile - 8)
        else:
            config.tile_overlap = args.tile_overlap
        print(f'[{index}/{len(files)}] {path.name}: {w}x{h} -> {w*2}x{h*2}', flush=True)
        with torch.inference_mode():
            output = run_inference(tensor, model, config, 8)[..., :h*2, :w*2]
        pixels = output.squeeze(0).float().cpu().clamp(0, 1).numpy()
        bgr = np.ascontiguousarray(pixels[::-1].transpose(1, 2, 0))
        result = np.rint(bgr * maximum).astype(image.dtype)
        target = output_path(path, args.output, args.format)
        save_image(target, result)
        print(f'Saved {target} ({time.perf_counter()-started:.1f}s)', flush=True)
        del tensor, output
    print(f'Done. Output folder: {args.output}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
