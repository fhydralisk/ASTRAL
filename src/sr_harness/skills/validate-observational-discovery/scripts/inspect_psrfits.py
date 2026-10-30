"""Header-only PSRFITS inventory. Does not infer Stokes values or a target law."""
from pathlib import Path


def inspect(path):
    from astropy.io import fits
    with fits.open(path, memmap=True, lazy_load_hdus=True) as hdus:
        primary = hdus[0].header
        sub = hdus['SUBINT']
        header = sub.header
        result = {'path': str(path), 'primary': {}, 'subint': {}, 'columns': {}, 'warnings': []}
        for key in ('FITSTYPE', 'TELESCOP', 'SRC_NAME', 'RA', 'DEC', 'DATE-OBS',
                    'FD_POLN', 'FD_HAND', 'FD_SANG', 'FD_XYPH', 'BE_PHASE'):
            result['primary'][key] = primary.get(key)
        for key in ('NAXIS2', 'NPOL', 'NCHAN', 'NBIN', 'NSBLK', 'TBIN',
                    'POL_TYPE', 'SCALE', 'INT_TYPE', 'INT_UNIT'):
            result['subint'][key] = header.get(key)
        for col in sub.columns:
            result['columns'][col.name] = {'format': col.format, 'dim': col.dim, 'unit': col.unit}
        pol = str(header.get('POL_TYPE', '')).strip()
        if pol != 'IQUV':
            result['warnings'].append(f'POL_TYPE={pol!r}: four channels do not imply I,Q,U,V. Verify receiver basis and conversion conventions before measuring polarization.')
        if not header.get('SCALE'):
            result['warnings'].append('Missing intensity scale; physical flux units are not established.')
        result['warnings'].append('Header inventory only: verify actual array axes, scale/offset, weights and processing history before reduction.')
        return result


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rows = []
    for name in args.inputs:
        p = Path(name)
        files = sorted(p.rglob('*.fits')) if p.is_dir() else [p]
        for file in files:
            try:
                rows.append(inspect(file))
            except Exception as error:
                rows.append({'path': str(file), 'error': f'{type(error).__name__}: {error}'})
    Path(args.output).write_text(json.dumps(rows, indent=2))
    print(f'Saved {len(rows)} records; {sum("error" in row for row in rows)} errors')
