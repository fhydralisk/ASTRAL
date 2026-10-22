"""Verify or restore the curated paper/data download inventory.

Default: list files. --verify checks local checksums. --download restores missing
files only; changed upstream content is rejected. Downloaded files stay gitignored.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'research/gaia_frb_ism/download_manifest.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--download', action='store_true')
    args = parser.parse_args()
    entries = json.loads(MANIFEST.read_text())
    errors = []
    for item in entries:
        path = (ROOT / item['path']).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError('Manifest path escapes repository')
        try:
            if args.download and not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(path.suffix + '.part')
                try:
                    request = urllib.request.Request(item['url'], headers={'User-Agent': 'ASTRAL-research/1.0'})
                    with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as out:
                        received = 0
                        while block := response.read(1024 * 1024):
                            received += len(block)
                            if received > item['bytes']:
                                raise ValueError('Upstream file exceeds recorded size')
                            out.write(block)
                    if digest(temporary) != item['sha256']:
                        raise ValueError('Upstream content changed; checksum mismatch')
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            if args.verify or args.download:
                if not path.exists():
                    raise FileNotFoundError(item['path'])
                if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                    raise ValueError('Local size or checksum mismatch')
            else:
                print(f"{item['bytes']:>10}  {item['path']}")
        except Exception as exc:
            errors.append(f"{item['path']}: {exc}")
    if errors:
        print('\n'.join(errors))
        raise SystemExit(1)
    print(f'{len(entries)} source files; {sum(x["bytes"] for x in entries):,} bytes')


if __name__ == '__main__':
    main()
