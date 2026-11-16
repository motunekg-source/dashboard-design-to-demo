#!/usr/bin/env python3
"""Compare two equal-size frames. Optionally inspect named regions in original design coordinates."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def difference_stats(delta, threshold):
    red, green, blue = delta.split()
    maxima = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    count = delta.width * delta.height
    return {
        "size": list(delta.size),
        "threshold_8bit": threshold,
        "fraction_with_any_channel_above_threshold": round(sum(maxima.histogram()[threshold + 1:]) / count, 6),
        "mean_abs_channel_error_8bit": [round(x, 3) for x in ImageStat.Stat(delta).mean],
    }


def read_regions(path, size):
    if path is None:
        return {}
    regions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(regions, dict) or not regions:
        raise ValueError("Supply a JSON object mapping region names to [left, top, right, bottom].")
    width, height = size
    for name, box in regions.items():
        if not name.strip() or not isinstance(box, list) or len(box) != 4 or any(type(i) is not int for i in box):
            raise ValueError(f"Invalid region name or integer bounds: {name!r} {box!r}")
        left, top, right, bottom = box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(f"Empty or out-of-frame region: {name!r} {box!r} in {size!r}")
    return regions


def compare(reference, actual, out, threshold, regions_path=None):
    with Image.open(reference) as r, Image.open(actual) as a:
        ref, result = r.convert("RGB"), a.convert("RGB")
    if ref.size != result.size:
        raise ValueError(f"Compare in the same viewport and DPR: {ref.size} vs {result.size}")
    regions = read_regions(regions_path, ref.size)
    out.mkdir(parents=True, exist_ok=True)
    delta = ImageChops.difference(ref, result)
    overlay = Image.blend(ref, result, .5)
    amplified = delta.point(lambda x: min(255, x * 4))
    overlay.save(out / "overlay.png")
    amplified.save(out / "difference-4x.png")
    stats = difference_stats(delta, threshold)
    if regions:
        stats["regions"] = {}
        for i, (name, box) in enumerate(regions.items(), 1):
            w, h = box[2] - box[0], box[3] - box[1]
            strip = Image.new("RGB", (w * 4, h))
            for j, frame in enumerate((ref, result, overlay, amplified)):
                strip.paste(frame.crop(box), (w * j, 0))
            filename = f"region-{i:02}.png"
            strip.save(out / filename)
            stats["regions"][name] = dict(difference_stats(delta.crop(box), threshold), box=box, image=filename)
    (out / "metrics.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("reference", "actual", "out"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--threshold", type=int, default=16, choices=range(256), metavar="0..255")
    parser.add_argument("--regions", type=Path, help="JSON object of named rectangles. Right and bottom are exclusive.")
    args = parser.parse_args()
    compare(args.reference, args.actual, args.out, args.threshold, args.regions)
