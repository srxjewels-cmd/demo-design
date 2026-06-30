#!/usr/bin/env python3
"""Package the macro-enabled workbook: take the original .xlsx, inject
vbaProject.bin, set codeNames, fix content-types/rels, write .xlsm."""
import zipfile, shutil, sys, re

SRC = sys.argv[1]            # original .xlsx
BIN = sys.argv[2]            # vbaProject.bin
OUT = sys.argv[3]            # output .xlsm

# codeName per worksheet part (sheet1..4 -> Dashboard, Ramesh, Suresh, Mahesh)
SHEET_CODENAMES = {
    'xl/worksheets/sheet1.xml': 'Dashboard',
    'xl/worksheets/sheet2.xml': 'Ramesh',
    'xl/worksheets/sheet3.xml': 'Suresh',
    'xl/worksheets/sheet4.xml': 'Mahesh',
}

with open(BIN, 'rb') as f:
    vba_bytes = f.read()

zin = zipfile.ZipFile(SRC, 'r')
names = zin.namelist()
out_items = []   # (ZipInfo-ish name, bytes)

for name in names:
    data = zin.read(name)

    if name == '[Content_Types].xml':
        text = data.decode('utf-8')
        # workbook main part -> macro-enabled
        text = text.replace(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml',
            'application/vnd.ms-excel.sheet.macroEnabled.main+xml')
        # declare the vbaProject part
        if 'vbaProject' not in text:
            text = text.replace(
                '</Types>',
                '<Override PartName="/xl/vbaProject.bin" '
                'ContentType="application/vnd.ms-office.vbaProject"/></Types>')
        data = text.encode('utf-8')

    elif name == 'xl/_rels/workbook.xml.rels':
        text = data.decode('utf-8')
        if 'vbaProject' not in text:
            # pick an unused rId
            used = set(int(x) for x in re.findall(r'Id="rId(\d+)"', text))
            rid = 'rId%d' % (max(used) + 1)
            rel = ('<Relationship Id="%s" '
                   'Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" '
                   'Target="vbaProject.bin"/>' % rid)
            text = text.replace('</Relationships>', rel + '</Relationships>')
        data = text.encode('utf-8')

    elif name == 'xl/workbook.xml':
        text = data.decode('utf-8')
        if 'codeName=' not in text:
            text = text.replace('<workbookPr/>',
                                '<workbookPr codeName="ThisWorkbook"/>', 1)
            if 'codeName="ThisWorkbook"' not in text:
                # workbookPr may have attributes
                text = re.sub(r'<workbookPr([^>]*)/>',
                              r'<workbookPr\1 codeName="ThisWorkbook"/>', text, count=1)
        data = text.encode('utf-8')

    elif name in SHEET_CODENAMES:
        text = data.decode('utf-8')
        cn = SHEET_CODENAMES[name]
        if 'codeName=' not in text.split('</sheetPr>')[0]:
            if '<sheetPr>' in text:
                text = text.replace('<sheetPr>', '<sheetPr codeName="%s">' % cn, 1)
            elif '<sheetPr/>' in text:
                text = text.replace('<sheetPr/>', '<sheetPr codeName="%s"/>' % cn, 1)
            else:
                text = re.sub(r'<sheetPr([^>]*)>',
                              r'<sheetPr\1 codeName="%s">' % cn, text, count=1)
        data = text.encode('utf-8')

    out_items.append((name, data))

zin.close()

# add the vbaProject.bin part
out_items.append(('xl/vbaProject.bin', vba_bytes))

with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as zout:
    for name, data in out_items:
        zout.writestr(name, data)

print('wrote', OUT)
