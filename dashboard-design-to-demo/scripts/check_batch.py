#!/usr/bin/env python3
"""Verify batch coverage, provenance, evidence identity and release separation."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

def sha(data):
    return hashlib.sha256(data).hexdigest()

def verify(root, batch, originals, archive):
    errors = []
    rows = batch['cases']
    if batch.get('mode') not in {'clean', 'project'}:
        errors.append('需指明从零测试或普通项目')
    expected = {row['id']: row['sha'] for row in originals}
    if len(expected) != len(originals) or len(rows) != len(expected) or {row['id'] for row in rows} != set(expected):
        errors.append('批次原稿数量或编号不一致')
    seen = set()
    for asset in batch['inputs']:
        path = root / asset['file']
        if not path.is_file() or sha(path.read_bytes()) != asset['sha256']:
            errors.append('输入已变更：' + asset['file'])
        origin = asset['kind']
        if origin not in {'current-original', 'current-attachment', 'generic-tool', 'previous-project'}:
            errors.append('未登记的来源类型：'+origin)
        if origin == 'previous-project':
            consent = asset.get('consent') or {}
            if (batch['mode'] == 'clean' or not isinstance(consent, dict)
                    or consent.get('approved') is not True or not consent.get('scope')
                    or not consent.get('user_message')):
                errors.append('历史素材不在授权范围：' + asset['file'])
        if origin == 'current-original':
            if expected.get(asset.get('id')) != asset['sha256']:
                errors.append('原稿指纹不匹配：'+asset['file'])
            seen.add(asset['id'])
    if seen != set(expected):
        errors.append('原稿指纹记录不完整')
    for case in rows:
        label = case['id']
        if case['status'] not in {'通过','待修'}:
            errors.append(label+' 缺少结论')
        if not case.get('observation') or not case.get('evidence'):
            errors.append(label+' 缺少实拍观察')
        if case['status']=='待修' and not case.get('next'):
            errors.append(label+' 缺少具体差异或修复方向')
        for state, entry in case['evidence'].items():
            path = root / entry['file']
            if not path.is_file() or sha(path.read_bytes()) != entry['sha256']:
                errors.append(label+' 实拍证据已变更：'+state)
        required = {'home','compare','interaction'}
        for name, fields in [('orbit',{'side','rear','clay','near','far','reset'}),('motion',{'motion'}),('variants',{'configuration'})]:
            if case['scope'][name]:
                required |= fields
        if case['status']=='通过' and not required.issubset(case['evidence']):
            errors.append(label+' 正式包缺少必要的 '+str(sorted(required-set(case['evidence']))))
    accepted = {row['id'] for row in rows if row['status']=='通过'}
    if accepted:
        if archive is None or not archive.is_file() or sha(archive.read_bytes()) != batch.get('release_sha256'):
            errors.append('正式包与实测包的指纹不一致')
        else:
            with ZipFile(archive) as package:
                names=[PurePosixPath(p).parts for p in package.namelist()]
                included={p[1] for p in names if len(p)>=2 and p[0]=='cases' and p[1] in expected}
                if included!=accepted:
                    errors.append('正式包内容与通过清单不一致')
    elif archive is not None or batch.get('release_sha256'):
        errors.append('没有通过项时请省略正式发布包，可单独提供写明状态的阶段预览')
    return errors

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('report',type=Path)
    cli.add_argument('manifest',type=Path)
    cli.add_argument('--release',type=Path)
    args=cli.parse_args()
    try:
        errors=verify(args.report.resolve().parent,json.loads(args.report.read_text()),json.loads(args.manifest.read_text()),args.release)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        cli.exit(1,'记录无法读取：'+str(exc)+'\n')
    if errors:
        cli.exit(1,'\n'.join(errors)+'\n')
    print('原稿、实拍与通过／待修清单一致。')

if __name__=='__main__':
    main()
