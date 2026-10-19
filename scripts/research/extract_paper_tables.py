"""Extract selected published tables from pdftotext -layout output.

These are derived transcriptions, not author-supplied machine-readable releases.
Retain source PDFs and inspect table notes before using them for regression.
"""
from pathlib import Path
import csv
import re

ROOT = Path(__file__).resolve().parents[2]


def write_csv(path, header, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def main():
    name = 'Kainulainen_Science2014'
    source = ROOT / 'playground/paper/ISM' / (name + '.txt')
    table = source.read_text().rsplit('Table S1.', 1)[1]
    rows = []
    for line in table.splitlines():
        fields = re.split(r'\s{2,}', line.strip())
        if len(fields) == 10 and fields[0] not in ('Cloud name',):
            try:
                [float(v) for v in fields[1:]]
            except ValueError:
                continue
            rows.append(fields)
    assert len(rows) == 17, f'Expected 16 clouds plus aggregate, got {len(rows)}'
    write_csv(ROOT / 'data/ISM' / name / 'table_S1_transcribed.csv',
              ['cloud', 'mu_log_density', 'sigma_s', 'n0_cm-3', 'max_s',
               'kappa', 'M_sf_Msun', 'M_sf_over_Mtot_percent', 'M_Av_gt7_Msun', 'N_YSO'], rows)

    name = 'Feng_Science2022'
    # Table S2, including uncertainty and upper-limit flags. No imputed values.
    rows = [
        ['20121102A',565.8,81542,30.9,.4,.43,'',True],
        ['20180301A',517,546,6.3,.4,'','',False],
        ['20180916B',349.2,-115,.12,.01,.009,'',False],
        ['20190303A',222.4,-411,3.6,.1,.19,.04,False],
        ['20190417A',1378.2,4681,6.1,.5,.21,.06,False],
        ['20190520B',1210.3,2759,218.9,10.2,9.8,2.0,False],
        ['20201124A',413.5,-684,2.5,.1,.59,'',False],
    ]
    write_csv(ROOT / 'data/FRB' / name / 'table_S2_transcribed.csv',
              ['FRB','DM_pc_cm-3','RM_rad_m-2','sigma_RM_rad_m-2',
               'sigma_RM_error_rad_m-2','tau_sc_1300MHz_ms','tau_sc_error_ms',
               'tau_sc_upper_limit'], rows)

    # Keep original layout and footnotes when automatic CSV conversion is unsafe.
    excerpts = [
        ('FRB','Feng_Science2022','Table S2: Properties',None),
        ('FRB','Bruni_Nature2024','Extended Data Table 2 ','Extended Data Table 3'),
        ('FRB','Macquart_Nature2020','Table 1: Properties',None),
        ('ISM','Kruijssen_Nature2019','Table 1: Constrained',None),
        ('ISM','Tabatabaei_NatureAstronomy2018','Table 1: Thermal','The magnetic field in the center'),
        ('ISM','Li_NatureAstronomy2017','Table 1 Cloud long axis','Figure 1 -'),
        ('ISM','Kainulainen_Science2014','Table S1.\nProperties',None),
    ]
    for topic, name, start, end in excerpts:
        src = ROOT / 'playground/paper' / topic / (name + '.txt')
        text = src.read_text()
        begin = text.index(start)
        if name in ('Macquart_Nature2020', 'Kruijssen_Nature2019'):
            begin = text.rfind('\f', 0, begin) + 1
            end = '\f'
        stop = text.find(end, begin + len(start)) if end else -1
        if stop < 0:
            stop = min(len(text), begin + (20000 if name == 'Feng_Science2022' else 6500))
        dst = ROOT / 'data' / topic / name / 'published_tables_extracted.txt'
        dst.write_text('DERIVED TEXT EXTRACTION; consult the source PDF for layout, units and footnotes.\n'
                       + f'Source: playground/paper/{topic}/{name}.pdf\n\n' + text[begin:stop])


if __name__ == '__main__':
    main()
