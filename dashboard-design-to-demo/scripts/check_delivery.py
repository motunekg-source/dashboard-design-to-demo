#!/usr/bin/env python3
"""Check that the inspected build, every requested design and the mounted ZIP are accounted for."""
import argparse
import hashlib
import json
from pathlib import Path


WEIGHTS = {"轮廓与比例": 25, "部件与空间关系": 25, "材质与纹理": 20, "光影与渐变": 20, "构图与视觉效果": 10}
FEATURE_CHECKS = {
    "rigid": "刚体与附件",
    "support": "支撑与连接",
    "whole_surface": "背侧表面一致性",
    "material_extension": "材质交界路径",
    "display_detail": "展示尺寸与清晰度",
    "zoom": "缩放边缘与场景延展",
    "relief_shading": "浮雕明暗与细节",
    "halo": "光晕外观与状态",
    "data_terrain": "背坡色层与纹理密度",
    "around_axis": "同高度周向闭合",
}
STATE_VIEWS = {
    "材质交界路径": ("交界前", "反馈或交界机位", "交界后"),
    "展示尺寸与清晰度": ("原尺寸", "目标尺寸"),
    "缩放边缘与场景延展": ("最近", "最远"),
    "背坡色层与纹理密度": ("原机位", "过脊侧面", "背坡低侧"),
    "同高度周向闭合": ("缝前", "缝上", "缝后"),
    "刚体与附件": ("原机位", "单色斜侧", "背面"),
    "支撑与连接": ("侧面", "低侧"),
    "背侧表面一致性": ("原机位", "背侧近景"),
    "完整循环": ("起始", "中间", "近末"),
    "连续绕看": ("原机位", "侧面", "背面"),
}


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def inspect_subject(label, subject, errors):
    grades = subject.get("grades", {})
    if set(grades) != set(WEIGHTS):
        errors.append(f"{label} 需要完整的五维评定")
        return
    tenths = 0
    for dimension, weight in WEIGHTS.items():
        entry = grades[dimension]
        grade = entry.get("grade")
        if not has_text(entry.get("observation")):
            errors.append(f"{label} / {dimension} 缺少部位及实拍观察")
        if grade == "吻合":
            tenths += weight * 10
        elif grade == "细微":
            tenths += weight * 9
            if not has_text(entry.get("refinement")):
                errors.append(f"{label} / {dimension} 缺少细微差异的精调办法")
        else:
            errors.append(f"{label} / {dimension} 尚未达标")
    if tenths < 950:
        errors.append(f"{label} 设计特征复核 {tenths / 10:g} 分，低于 95 分")


def digest(path):
    with path.open("rb") as f:
        sha = hashlib.sha256()
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def problems(root, review, bundle, sources):
    errors = []
    if review.get("standard") != 7:
        errors.append("需使用第 7 版验收记录格式，并补查缺少的项目")
    if not bundle.is_file() or review.get("package_sha256") != digest(bundle):
        errors.append("实测包与拟交付包不一致")
    items = review.get("cases", [])
    expected = {digest(path) for path in sources}
    actual = [item.get("reference_sha256") for item in items]
    if set(actual) != expected or len(actual) != len(expected):
        errors.append("原稿清单与逐稿走查记录不一致")

    def inspect(label, record, required_views=()):
        if record.get("status") != "通过" or not has_text(record.get("observation")):
            errors.append(f"{label} 缺少通过的实查结论")
        evidence = record.get("evidence") or []
        if not evidence:
            errors.append(f"{label} 缺少对应证据")
        views = {}
        for entry in evidence:
            path = root / entry["file"]
            if not path.is_file() or path.stat().st_size == 0 or digest(path) != entry.get("sha256"):
                errors.append(f"{label} 证据已变更或缺失：{path.name}")
            elif entry.get("view") in required_views:
                if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".avif"}:
                    views[entry["view"]] = entry["sha256"]
        if len(set(views.values())) != len(required_views):
            errors.append(f"{label} 需要各状态不同的实拍关键帧：{'、'.join(required_views)}")

    for item in items:
        title = item.get("name")
        if not has_text(title):
            errors.append("缺少原稿名称")
        checks = item.get("checks", {})
        required = {"默认机位", "关键局部", "主要交互", "加载与流畅度"}
        scope = item.get("scope", {})
        for key in ("ui", "extended", *FEATURE_CHECKS):
            if not isinstance(scope.get(key), bool):
                errors.append(f"{title} 需要明确 {key} 的适用范围")
        for key, check in FEATURE_CHECKS.items():
            if scope.get(key):
                required.add(check)
        if scope.get("display_detail"):
            valid_samples = set()
            for sample in checks.get("展示尺寸与清晰度", {}).get("samples", []):
                sizes = [sample.get(key) for key in ("css", "buffer")]
                if (isinstance(sample.get("dpr"), (int, float)) and sample["dpr"] > 0
                        and all(isinstance(pair, list) and len(pair) == 2
                                and all(isinstance(n, (int, float)) and n > 0 for n in pair) for pair in sizes)):
                    valid_samples.add(sample.get("view"))
            if not {"原尺寸", "目标尺寸"} <= valid_samples:
                errors.append(f"{title} 缺少两种展示尺寸实测的画布、绘图缓冲和设备像素比")
        panels = item.get("panels", [])
        subjects = item.get("subjects", [])
        if not (scope.get("ui") or scope.get("extended")):
            errors.append(f"{title} 缺少待验收内容")
        if bool(panels) != scope.get("ui") or bool(subjects) != scope.get("extended"):
            errors.append(f"{title} 面板、图表或主视觉清单与读稿范围不一致")
        if scope.get("extended") and not scope.get("zoom"):
            errors.append(f"{title} 延展主体缺少缩放范围")
        if (item.get("orbit") or scope.get("data_terrain") or scope.get("around_axis")) and not subjects:
            errors.append(f"{title} 缺少空间主体")
        for group, entries in (("面板或图表", panels), ("主视觉", subjects)):
            names = set()
            for entry in entries:
                name = entry.get("name")
                if not has_text(name) or name in names:
                    errors.append(f"{title} / {group} 缺少唯一名称")
                names.add(name)
                label = f"{title} / {group} / {name}"
                inspect(label, entry)
                if group == "主视觉":
                    inspect_subject(label, entry, errors)
        if item.get("orbit") is True:
            required.update({"连续绕看", "背侧与顶面", "精确复位"})
        elif item.get("orbit") is not False:
            errors.append(f"{title} 缺少事先确定的视角范围")
        for flag, check in (("variants", "状态或换色"), ("animation", "完整循环")):
            if not isinstance(item.get(flag), bool):
                errors.append(f"{title} 需要明确 {flag} 的适用范围")
            elif item[flag]:
                required.add(check)
        if item.get("variants"):
            groups = item.get("configurations", [])
            if not groups:
                errors.append(f"{title} 缺少逐组配置实拍")
            for group in groups:
                options = group["options"]
                if len(set(options)) < 2:
                    errors.append(f"{title} 配置组需包含至少两种可见状态")
                inspect(f"{title} / {group['name']}", group, options)
        for name in sorted(required.union(checks)):
            inspect(f"{title} / {name}", checks.get(name, {}), STATE_VIEWS.get(name, ()))
    inspect("同一包的宿主导入", review.get("host", {}))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("zip", type=Path)
    parser.add_argument("sources", nargs="+", type=Path, help="本次要求还原的所有原稿")
    args = parser.parse_args()
    try:
        review = json.loads(args.review.read_text(encoding="utf-8"))
        errors = problems(args.review.resolve().parent, review, args.zip, args.sources)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(1, f"走查记录无效：{exc}\n")
    if errors:
        parser.exit(1, "正式验收未通过，可先交阶段预览并标明待修或待验证项目\n" + "\n".join(errors) + "\n")
    remaining = []
    for case in review["cases"]:
        for subject in case.get("subjects", []):
            for entry in subject["grades"].values():
                if entry["grade"] == "细微":
                    remaining.append(f"{case['name']} / {subject['name']}：{entry['observation'].rstrip('。')}。可选精调：{entry['refinement']}")
    print("逐稿走查记录、证据和实测包一致")
    if remaining:
        print("随成品说明的细微差异")
        print("\n".join(remaining))


if __name__ == "__main__":
    main()
