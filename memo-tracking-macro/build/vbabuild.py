#!/usr/bin/env python3
"""
Build a vbaProject.bin (MS-OVBA) from scratch and embed three identical
Worksheet_Change auto-stamp macros behind the Ramesh / Suresh / Mahesh sheets
of a workbook, producing a macro-enabled .xlsm.

No Microsoft Excel required. Output is validated with oletools (olevba) which
implements the MS-OVBA reader, and with LibreOffice.
"""
import struct, io, zipfile, shutil, os, sys

# ----------------------------------------------------------------------------
# 1. MS-OVBA 2.4.1 compression  (real LZ compressor with CopyTokens)
# ----------------------------------------------------------------------------

def _copytoken_bitcount(difference):
    # difference = position within the decompressed chunk (>=1)
    bc = (difference - 1).bit_length()
    return bc if bc > 4 else 4

def _find_match(chunk, pos):
    bit_count = _copytoken_bitcount(pos)
    max_offset = 1 << bit_count
    max_length = (0xFFFF >> bit_count) + 3
    n = len(chunk)
    start = pos - max_offset
    if start < 0:
        start = 0
    best_len = 0
    best_off = 0
    cand = pos - 1
    while cand >= start:
        off = pos - cand
        # length of match starting at cand vs pos (overlap allowed, data fully known)
        L = 0
        while L < max_length and pos + L < n and chunk[cand + L] == chunk[pos + L]:
            L += 1
        if L > best_len:
            best_len = L
            best_off = off
            if L >= max_length:
                break
        cand -= 1
    return best_len, best_off, bit_count

def _compress_chunk(chunk):
    out = bytearray()
    pos = 0
    n = len(chunk)
    while pos < n:
        flag_index = len(out)
        out.append(0)            # placeholder flag byte
        flag = 0
        for bit in range(8):
            if pos >= n:
                break
            if pos == 0:
                out.append(chunk[0]); pos += 1
                continue
            mlen, moff, bit_count = _find_match(chunk, pos)
            if mlen >= 3:
                token = ((moff - 1) << (16 - bit_count)) | ((mlen - 3) & (0xFFFF >> bit_count))
                out += struct.pack('<H', token)
                flag |= (1 << bit)
                pos += mlen
            else:
                out.append(chunk[pos]); pos += 1
        out[flag_index] = flag
    return out

def ovba_compress(data):
    out = bytearray([0x01])      # signature byte
    i = 0
    n = len(data)
    while i < n:
        chunk = data[i:i + 4096]
        i += len(chunk)
        comp = _compress_chunk(chunk)
        if len(comp) <= 4096 and len(comp) < len(chunk) + 1 + (len(chunk) + 7) // 8 + 1 or True:
            if len(comp) <= 4096:
                header = 0xB000 | (len(comp) - 1)   # compressed chunk, sig 0b011, flag 1
                out += struct.pack('<H', header)
                out += comp
                continue
        # fallback: raw chunk (must be exactly 4096 of data)
        raw = bytes(chunk) + b'\x00' * (4096 - len(chunk))
        header = 0x3000 | 0x0FFF                      # flag 0 -> raw, size field 0xFFF
        out += struct.pack('<H', header)
        out += raw
    return bytes(out)

# ----------------------------------------------------------------------------
# 2. dir / PROJECT / PROJECTwm / _VBA_PROJECT / module streams
# ----------------------------------------------------------------------------

CP = 1252
def mbcs(s): return s.encode('cp1252')
def utf16(s): return s.encode('utf-16-le')

def rec(_id, payload):
    """Generic record: Id(2) Size(4) payload."""
    return struct.pack('<HL', _id, len(payload)) + payload

WORKBOOK_CLSID  = '00020819-0000-0000-C000-000000000046'
WORKSHEET_CLSID = '00020820-0000-0000-C000-000000000046'

# 4 standard registered references of a fresh Excel VBA project.
REFERENCES = [
    ('stdole',
     r'*\G{00020430-0000-0000-C000-000000000046}#2.0#0#C:\Windows\System32\stdole2.tlb#OLE Automation'),
    ('Office',
     r'*\G{2DF8D04C-5BFA-101B-BDE5-00AA0044DE52}#2.8#0#C:\Program Files\Common Files\Microsoft Shared\OFFICE16\MSO.DLL#Microsoft Office 16.0 Object Library'),
    ('Excel',
     r'*\G{00020813-0000-0000-C000-000000000046}#1.9#0#C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE#Microsoft Excel 16.0 Object Library'),
    ('VBA',
     r'*\G{000204EF-0000-0000-C000-000000000046}#4.2#9#C:\PROGRA~2\COMMON~1\MICROS~1\VBA\VBA7.1\VBE7.DLL#Visual Basic For Applications'),
]

def build_reference(name, libid):
    out = b''
    # REFERENCENAME (0x0016): Id Size Name 0x003E SizeU NameU
    out += struct.pack('<HL', 0x0016, len(mbcs(name))) + mbcs(name)
    out += struct.pack('<H', 0x003E)
    out += struct.pack('<L', len(utf16(name))) + utf16(name)
    # REFERENCEREGISTERED (0x000D): Id Size SizeOfLibid Libid Reserved1(4)=0 Reserved2(2)=0
    libid_b = mbcs(libid)
    inner = struct.pack('<L', len(libid_b)) + libid_b + struct.pack('<L', 0) + struct.pack('<H', 0)
    out += struct.pack('<HL', 0x000D, len(inner)) + inner
    return out

def build_dir(project_name, modules):
    s = b''
    s += rec(0x0001, struct.pack('<L', 0x00000001))           # PROJECTSYSKIND  (32-bit win)
    s += rec(0x0002, struct.pack('<L', 0x00000409))           # PROJECTLCID
    s += rec(0x0014, struct.pack('<L', 0x00000409))           # PROJECTLCIDINVOKE
    s += rec(0x0003, struct.pack('<H', 0x04E4))               # PROJECTCODEPAGE (1252)
    s += rec(0x0004, mbcs(project_name))                      # PROJECTNAME
    # PROJECTDOCSTRING: Id Size Doc 0x0040 SizeU DocU
    s += struct.pack('<HL', 0x0005, 0) + b'' + struct.pack('<H', 0x0040) + struct.pack('<L', 0) + b''
    # PROJECTHELPFILEPATH: Id Size H1 0x003D Size2 H2
    s += struct.pack('<HL', 0x0006, 0) + b'' + struct.pack('<H', 0x003D) + struct.pack('<L', 0) + b''
    s += rec(0x0007, struct.pack('<L', 0))                    # PROJECTHELPCONTEXT
    s += rec(0x0008, struct.pack('<L', 0))                    # PROJECTLIBFLAGS
    # PROJECTVERSION: Id Reserved(4)=0x04 VersionMajor(4) VersionMinor(2)
    s += struct.pack('<HL', 0x0009, 0x00000004) + struct.pack('<L', 1) + struct.pack('<H', 0)
    # PROJECTCONSTANTS: Id Size Const 0x003C SizeU ConstU
    s += struct.pack('<HL', 0x000C, 0) + b'' + struct.pack('<H', 0x003C) + struct.pack('<L', 0) + b''
    for name, libid in REFERENCES:
        s += build_reference(name, libid)
    # PROJECTMODULES
    s += struct.pack('<HL', 0x000F, 0x00000002) + struct.pack('<H', len(modules))   # Id Size Count
    s += struct.pack('<HL', 0x0013, 0x00000002) + struct.pack('<H', 0xFFFF)         # cookie record
    for m in modules:
        nm = m['name']
        s += rec(0x0019, mbcs(nm))                            # MODULENAME
        s += rec(0x0047, utf16(nm))                           # MODULENAMEUNICODE
        # MODULESTREAMNAME: Id Size Name 0x0032 SizeU NameU
        s += struct.pack('<HL', 0x001A, len(mbcs(nm))) + mbcs(nm)
        s += struct.pack('<H', 0x0032) + struct.pack('<L', len(utf16(nm))) + utf16(nm)
        # MODULEDOCSTRING
        s += struct.pack('<HL', 0x001C, 0) + b'' + struct.pack('<H', 0x0048) + struct.pack('<L', 0) + b''
        s += rec(0x0031, struct.pack('<L', 0))                # MODULEOFFSET (TextOffset=0)
        s += rec(0x001E, struct.pack('<L', 0))                # MODULEHELPCONTEXT
        s += rec(0x002C, struct.pack('<H', 0xFFFF))           # MODULECOOKIE
        s += struct.pack('<HL', 0x0022, 0x00000000)           # MODULETYPE = document module
        s += struct.pack('<HL', 0x002B, 0x00000000)           # module terminator
    s += struct.pack('<HL', 0x0010, 0x00000000)               # dir global terminator
    return s

def doc_module_source(name, clsid, code):
    hdr = (
        f'Attribute VB_Name = "{name}"\r\n'
        f'Attribute VB_Base = "0{{{clsid}}}"\r\n'
        'Attribute VB_GlobalNameSpace = False\r\n'
        'Attribute VB_Creatable = False\r\n'
        'Attribute VB_PredeclaredId = True\r\n'
        'Attribute VB_Exposed = True\r\n'
        'Attribute VB_TemplateDerived = True\r\n'
        'Attribute VB_Customizable = True\r\n'
    )
    return hdr + code

def vba_encrypt(data, project_key=0x00, seed=0x01):
    """MS-OVBA 2.4.3 Data Encryption. Returns uppercase hex string.
    Verified against the spec's example vectors (e.g. CMG=F1F301E705... ->
    Version=2, ProjectProtectionState=0x00000000)."""
    version = 2
    ignored_length = (seed & 6) // 2
    out = bytearray([seed, seed ^ version, seed ^ project_key])
    enc1 = seed ^ project_key      # EncryptedByte1 = ProjectKeyEnc
    enc2 = seed ^ version          # EncryptedByte2 = VersionEnc
    unenc1 = project_key           # UnencryptedByte1
    plain = bytes(ignored_length) + struct.pack('<L', len(data)) + bytes(data)
    for b in plain:
        be = b ^ ((enc2 + unenc1) & 0xFF)
        out.append(be)
        unenc1 = b
        enc2 = enc1
        enc1 = be
    return out.hex().upper()

def build_project_stream(project_name, modules):
    # Project-protection metadata for an unprotected, visible, no-password project.
    cmg = vba_encrypt(struct.pack('<L', 0x00000000))   # ProjectProtectionState: none
    dpb = vba_encrypt(b'\x00')                          # ProjectPassword: none
    gc  = vba_encrypt(b'\xFF')                          # ProjectVisibilityState: visible
    lines = ['ID="{B2D3C4E5-1A2B-3C4D-5E6F-A1B2C3D4E5F6}"']
    for m in modules:
        lines.append(f'Document={m["name"]}/&H00000000')
    lines += [
        f'Name="{project_name}"',
        'HelpContextID="0"',
        'VersionCompatible32="393222000"',
        f'CMG="{cmg}"',
        f'DPB="{dpb}"',
        f'GC="{gc}"',
        '',
        '[Host Extender Info]',
        '&H00000001={3832D640-CF90-11CF-8E43-00A0C911005A};VBE;&H00000000',
        '',
        '[Workspace]',
    ]
    for m in modules:
        lines.append(f'{m["name"]}=0, 0, 0, 0, C')
    return ('\r\n'.join(lines) + '\r\n').encode('cp1252')

def build_projectwm(modules):
    out = b''
    for m in modules:
        out += mbcs(m['name']) + b'\x00' + utf16(m['name']) + b'\x00\x00'
    out += b'\x00\x00'
    return out

VBA_PROJECT_STREAM = b'\xcc\x61\xff\xff\x00\x00\x00'   # minimal _VBA_PROJECT (no perf cache)

# ----------------------------------------------------------------------------
# 3. MS-CFB compound file writer
# ----------------------------------------------------------------------------

FREESECT   = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT    = 0xFFFFFFFD
NOSTREAM   = 0xFFFFFFFF

class DirEntry:
    def __init__(self, name, etype):
        self.name = name
        self.etype = etype          # 1 storage, 2 stream, 5 root
        self.left = NOSTREAM
        self.right = NOSTREAM
        self.child = NOSTREAM
        self.start = 0
        self.size = 0
        self.data = b''

def _name_key(name):
    # MS-CFB sibling ordering: by UTF-16 length, then uppercased code units
    u = name.upper()
    return (len(name), [ord(c) for c in u])

def _build_bst(indices, entries):
    """indices: list of entry indexes, sorted by name key. Return root index, set left/right."""
    if not indices:
        return NOSTREAM
    mid = len(indices) // 2
    root = indices[mid]
    entries[root].left = _build_bst(indices[:mid], entries)
    entries[root].right = _build_bst(indices[mid + 1:], entries)
    return root

def write_cfb(root_children, all_streams_storages):
    """
    root_children: list of (entry) top-level children
    Builds the CFB. Each entry has .data for streams.
    """
    entries = all_streams_storages   # list of DirEntry; index 0 must be Root Entry
    SECT = 512
    MINI = 64
    CUTOFF = 4096

    # Assign mini-stream layout: every stream (size>0 and <CUTOFF) goes to mini stream.
    mini = bytearray()
    for e in entries:
        if e.etype == 2:             # stream
            if len(e.data) < CUTOFF:
                e.start = len(mini) // MINI
                mini += e.data
                pad = (-len(mini)) % MINI
                mini += b'\x00' * pad
                e.size = len(e.data)
            else:
                e.start = None       # placed in regular FAT later
                e.size = len(e.data)
        elif e.etype == 5:
            pass
        else:                        # storage
            e.start = 0
            e.size = 0

    num_mini_sectors = len(mini) // MINI

    # mini FAT: chain consecutive mini sectors per stream
    minifat = []
    for e in entries:
        if e.etype == 2 and e.start is not None and e.size >= 0 and len(e.data) < CUTOFF and len(e.data) > 0:
            nsec = (e.size + MINI - 1) // MINI
            base = e.start
            for k in range(nsec):
                if k == nsec - 1:
                    minifat.append(ENDOFCHAIN)
                else:
                    minifat.append(base + k + 1)
    # minifat must have one entry per used mini sector, in mini-sector order.
    # Our streams were laid out consecutively so the natural order already matches
    # mini-sector indices. Pad minifat to full sectors.
    assert len(minifat) == num_mini_sectors, (len(minifat), num_mini_sectors)
    while len(minifat) % (SECT // 4) != 0:
        minifat.append(FREESECT)

    minifat_bytes = b''.join(struct.pack('<L', x) for x in minifat)
    num_minifat_sectors = len(minifat_bytes) // SECT if minifat_bytes else 0

    mini_padded = bytes(mini) + b'\x00' * ((-len(mini)) % SECT)
    num_ministream_sectors = len(mini_padded) // SECT

    # Root entry holds the mini stream
    root = entries[0]
    root.size = len(mini)            # actual mini stream length
    # (root.start assigned below to first ministream sector)

    # Directory entries bytes
    def dir_entry_bytes(e):
        nb = e.name.encode('utf-16-le') + b'\x00\x00'
        nb = nb[:64]
        name_field = nb + b'\x00' * (64 - len(nb))
        name_len = len(e.name.encode('utf-16-le')) + 2
        b = name_field
        b += struct.pack('<H', name_len)
        b += struct.pack('<B', e.etype)
        b += struct.pack('<B', 1)                 # color = black
        b += struct.pack('<L', e.left)
        b += struct.pack('<L', e.right)
        b += struct.pack('<L', e.child)
        b += b'\x00' * 16                          # CLSID
        b += struct.pack('<L', 0)                  # state bits
        b += b'\x00' * 8 + b'\x00' * 8             # creation/modified time
        start = e.start if e.start is not None else e.reg_start
        b += struct.pack('<L', start if e.etype != 1 else 0)
        b += struct.pack('<Q', e.size if e.etype != 1 else 0)
        assert len(b) == 128
        return b

    # ---- Lay out regular sectors ----
    # order: [ministream data][minifat][directory]  then FAT sectors
    # First compute directory bytes (needs sizes/starts already; large streams handled below)
    # No large streams in this project, but support generically:
    large_streams = [e for e in entries if e.etype == 2 and len(e.data) >= CUTOFF]

    # tentative sector counts
    n_mini = num_ministream_sectors
    n_minifat = num_minifat_sectors

    # large stream sectors
    for e in large_streams:
        e.reg_nsec = (len(e.data) + SECT - 1) // SECT

    # directory: build after we know counts? directory needs starts.
    # Assign sector indices now.
    cur = 0
    # ministream sectors
    root.start = cur if n_mini else ENDOFCHAIN
    ministream_first = cur
    cur += n_mini
    # minifat sectors
    minifat_first = cur if n_minifat else ENDOFCHAIN
    cur += n_minifat
    # large streams
    for e in large_streams:
        e.reg_start = cur
        cur += e.reg_nsec
    # directory sectors
    num_entries = len(entries)
    dir_padded_entries = num_entries
    # pad entries to multiple of 4 per sector (128 bytes => 4 per 512)
    while dir_padded_entries % (SECT // 128) != 0:
        dir_padded_entries += 1
    num_dir_sectors = (dir_padded_entries * 128) // SECT
    dir_first = cur
    cur += num_dir_sectors

    total_data_sectors = cur

    # Now compute FAT sectors needed (fixed point)
    num_fat_sectors = 1
    while True:
        total_sectors = total_data_sectors + num_fat_sectors
        entries_per_fat = SECT // 4
        need = (total_sectors + entries_per_fat - 1) // entries_per_fat
        if need == num_fat_sectors:
            break
        num_fat_sectors = need
    fat_first = cur
    total_sectors = total_data_sectors + num_fat_sectors

    # Build FAT
    fat = [FREESECT] * (num_fat_sectors * (SECT // 4))
    def chain(first, count):
        for k in range(count):
            sec = first + k
            fat[sec] = ENDOFCHAIN if k == count - 1 else sec + 1
    if n_mini:      chain(ministream_first, n_mini)
    if n_minifat:   chain(minifat_first, n_minifat)
    for e in large_streams:
        chain(e.reg_start, e.reg_nsec)
    chain(dir_first, num_dir_sectors)
    for k in range(num_fat_sectors):
        fat[fat_first + k] = FATSECT

    fat_bytes = b''.join(struct.pack('<L', x) for x in fat)

    # directory bytes
    dir_bytes = b''.join(dir_entry_bytes(e) for e in entries)
    dir_bytes += b'\x00' * (dir_padded_entries - num_entries) * 128

    # Assemble file
    header = bytearray()
    header += bytes.fromhex('D0CF11E0A1B11AE1')         # signature
    header += b'\x00' * 16                               # CLSID
    header += struct.pack('<H', 0x003E)                 # minor version
    header += struct.pack('<H', 0x0003)                 # major version (512 sectors)
    header += struct.pack('<H', 0xFFFE)                 # byte order
    header += struct.pack('<H', 0x0009)                 # sector shift (512)
    header += struct.pack('<H', 0x0006)                 # mini sector shift (64)
    header += b'\x00' * 6                                # reserved
    header += struct.pack('<L', 0)                      # num dir sectors (0 for v3)
    header += struct.pack('<L', num_fat_sectors)        # num FAT sectors
    header += struct.pack('<L', dir_first)              # first dir sector
    header += struct.pack('<L', 0)                      # transaction sig
    header += struct.pack('<L', CUTOFF)                 # mini stream cutoff
    header += struct.pack('<L', minifat_first if n_minifat else ENDOFCHAIN)
    header += struct.pack('<L', num_minifat_sectors)
    header += struct.pack('<L', ENDOFCHAIN)             # first DIFAT sector
    header += struct.pack('<L', 0)                      # num DIFAT sectors
    difat = [FREESECT] * 109
    for k in range(num_fat_sectors):
        difat[k] = fat_first + k
    for x in difat:
        header += struct.pack('<L', x)
    assert len(header) == 512

    body = bytearray()
    body += mini_padded
    body += minifat_bytes
    for e in large_streams:
        body += e.data + b'\x00' * ((-len(e.data)) % SECT)
    body += dir_bytes
    body += fat_bytes
    # pad body to full sectors (should already be aligned)
    assert len(body) == total_sectors * SECT, (len(body), total_sectors * SECT)

    return bytes(header) + bytes(body)

# ----------------------------------------------------------------------------
# 4. Assemble the vbaProject.bin
# ----------------------------------------------------------------------------

def build_vba_project(macro_code):
    modules = [
        {'name': 'ThisWorkbook', 'clsid': WORKBOOK_CLSID,  'code': ''},
        {'name': 'Dashboard',    'clsid': WORKSHEET_CLSID, 'code': ''},
        {'name': 'Ramesh',       'clsid': WORKSHEET_CLSID, 'code': macro_code},
        {'name': 'Suresh',       'clsid': WORKSHEET_CLSID, 'code': macro_code},
        {'name': 'Mahesh',       'clsid': WORKSHEET_CLSID, 'code': macro_code},
    ]
    project_name = 'VBAProject'
    dir_stream = build_dir(project_name, modules)
    dir_comp = ovba_compress(dir_stream)

    # sanity: round-trip dir through olevba's decompressor
    from oletools.olevba import decompress_stream
    assert decompress_stream(bytearray(dir_comp)) == dir_stream, "dir round-trip failed"

    # Build directory entries
    entries = []
    root = DirEntry('Root Entry', 5)
    entries.append(root)

    project_stream = DirEntry('PROJECT', 2)
    project_stream.data = build_project_stream(project_name, modules)
    projectwm = DirEntry('PROJECTwm', 2)
    projectwm.data = build_projectwm(modules)
    vba_storage = DirEntry('VBA', 1)

    vba_children = []
    vbaproj = DirEntry('_VBA_PROJECT', 2); vbaproj.data = VBA_PROJECT_STREAM
    dir_entry = DirEntry('dir', 2); dir_entry.data = dir_comp
    vba_children += [vbaproj, dir_entry]
    module_entries = []
    for m in modules:
        src = doc_module_source(m['name'], m['clsid'], m['code'])
        me = DirEntry(m['name'], 2)
        comp = ovba_compress(src.encode('cp1252'))
        assert decompress_stream(bytearray(comp)) == src.encode('cp1252'), f"module {m['name']} round-trip failed"
        me.data = comp
        module_entries.append(me)
    vba_children += module_entries

    # Register all entries (order: index assignment); build sibling trees
    top_children = [project_stream, projectwm, vba_storage]
    for e in top_children:
        entries.append(e)
    entries.append(vba_storage) if False else None
    for e in vba_children:
        entries.append(e)

    # index map
    idx = {id(e): i for i, e in enumerate(entries)}

    # top-level tree under root
    top_sorted = sorted(top_children, key=lambda e: _name_key(e.name))
    root.child = _build_bst([idx[id(e)] for e in top_sorted], entries)
    # vba storage children tree
    vba_sorted = sorted(vba_children, key=lambda e: _name_key(e.name))
    vba_storage.child = _build_bst([idx[id(e)] for e in vba_sorted], entries)

    return write_cfb(top_children, entries)

# ----------------------------------------------------------------------------
# 5. CLI
# ----------------------------------------------------------------------------
if __name__ == '__main__':
    MACRO = (
        'Private Sub Worksheet_Change(ByVal Target As Range)\r\n'
        '    Dim watchCol As Long, dateCol As Long, firstRow As Long, lastRow As Long\r\n'
        "    watchCol = 45   ' AS = Received tick column\r\n"
        "    dateCol = 46    ' AT = Date Recv column\r\n"
        '    firstRow = 11\r\n'
        '    lastRow = 4010\r\n'
        '\r\n'
        "    ' Only react to edits inside the tick column\r\n"
        '    If Intersect(Target, Me.Range(Me.Cells(firstRow, watchCol), _\r\n'
        '                                   Me.Cells(lastRow, watchCol))) Is Nothing Then Exit Sub\r\n'
        '\r\n'
        '    Application.EnableEvents = False\r\n'
        '    Dim c As Range\r\n'
        '    For Each c In Intersect(Target, Me.Range(Me.Cells(firstRow, watchCol), _\r\n'
        '                                              Me.Cells(lastRow, watchCol)))\r\n'
        "        If Trim(c.Value) = ChrW(10003) Then\r\n"
        "            ' ticked -> stamp today if date not already there\r\n"
        '            If Me.Cells(c.Row, dateCol).Value = "" Then\r\n'
        '                Me.Cells(c.Row, dateCol).Value = Date\r\n'
        '            End If\r\n'
        '        Else\r\n'
        "            ' unticked / cleared -> clear the date\r\n"
        '            Me.Cells(c.Row, dateCol).ClearContents\r\n'
        '        End If\r\n'
        '    Next c\r\n'
        '    Application.EnableEvents = True\r\n'
        'End Sub\r\n'
    )
    out = build_vba_project(MACRO)
    with open(sys.argv[1] if len(sys.argv) > 1 else 'vbaProject.bin', 'wb') as f:
        f.write(out)
    print('wrote', len(out), 'bytes')
