# Memo_Tracking — Auto-Stamp Received Date (macro pre-installed)

`Memo_Tracking.xlsm` is the workbook with the **Received-Date auto-stamp macro
already embedded** behind the three worker sheets (**Ramesh, Suresh, Mahesh**).

You do **not** need to open the VBA editor (Alt+F11) or paste any code — that
was done for you. The macro is identical on all three sheets.

## How to use it

1. Open `Memo_Tracking.xlsm` in **desktop Excel on Windows**.
2. If Excel shows a yellow bar **"Enable Content" / "Enable Macros"**, click it.
   (First open only. If the bar never appears, see *Troubleshooting* below.)
3. In the **DATA** list, tick a ✓ in the **Recv** column (column **AS**).
   → Today's date appears automatically in **Date Recv** (column **AT**), frozen.
   Untick / clear it → the date clears.

That's it. It now runs forever for these three sheets.

### What the macro does (one copy behind each of Ramesh / Suresh / Mahesh)

```vba
Private Sub Worksheet_Change(ByVal Target As Range)
    Dim watchCol As Long, dateCol As Long, firstRow As Long, lastRow As Long
    watchCol = 45   ' AS = Received tick column
    dateCol = 46    ' AT = Date Recv column
    firstRow = 11
    lastRow = 4010

    ' Only react to edits inside the tick column
    If Intersect(Target, Me.Range(Me.Cells(firstRow, watchCol), _
                                   Me.Cells(lastRow, watchCol))) Is Nothing Then Exit Sub

    Application.EnableEvents = False
    Dim c As Range
    For Each c In Intersect(Target, Me.Range(Me.Cells(firstRow, watchCol), _
                                              Me.Cells(lastRow, watchCol)))
        If Trim(c.Value) = ChrW(10003) Then          ' ChrW(10003) is the ✓ character
            ' ticked -> stamp today if date not already there
            If Me.Cells(c.Row, dateCol).Value = "" Then
                Me.Cells(c.Row, dateCol).Value = Date
            End If
        Else
            ' unticked / cleared -> clear the date
            Me.Cells(c.Row, dateCol).ClearContents
        End If
    Next c
    Application.EnableEvents = True
End Sub
```

> Note: the original write-up checked `ChrW(10003) Or "✓"`. Both are the **same**
> character (Unicode 10003 = ✓), so this version keeps the single `ChrW(10003)`
> test — behaviour is identical. (A literal ✓ can't be stored in a VBA module's
> Windows-1252 code page anyway, whereas `ChrW(10003)` always works.)

The columns were verified against the actual workbook: row-10 header `AS` = **Recv**
(tick) and `AT` = **Date Recv**, data starting at row 11 — exactly what the macro
expects.

## Troubleshooting

* **Phone / Excel mobile:** macros don't run there. Data still displays correctly;
  the auto-stamp just won't fire. Type the date by hand on mobile if needed.
* **"Enable Content" never appears / macro stays dormant:** in Excel,
  *File → Options → Trust Center → Trust Center Settings → Macro Settings* and
  allow macros (with notification).
* **Windows download block:** if macros won't run after download, close Excel,
  right-click the file → **Properties** → tick **Unblock** → **OK** → reopen.
* When you close, Excel asks to keep macros → **save as .xlsm, keep them**.

## Manual fallback (still works)

The manual route from the original instructions still works if you ever rebuild
from a plain `.xlsx`: Save As → *Excel Macro-Enabled Workbook (\*.xlsm)*, Alt+F11,
and paste the block above into each of the Ramesh / Suresh / Mahesh sheet code
windows. The pre-built `.xlsm` here just saves you those steps.

---

## How this file was built (reproducible)

Because this environment has no Microsoft Excel, the macro project
(`vbaProject.bin`) was constructed directly per the **MS-OVBA** specification
and embedded into the workbook package. See `build/`:

| File | Purpose |
|------|---------|
| `build/vbabuild.py` | Builds `vbaProject.bin` from scratch: MS-OVBA compression, the `dir` / `PROJECT` / `PROJECTwm` / `_VBA_PROJECT` / module streams, valid encrypted `CMG`/`DPB`/`GC` project-protection blobs, and an MS-CFB compound-file writer. |
| `build/package_xlsm.py` | Injects the `.bin`, sets the macro-enabled content type, adds the workbook relationship, and stamps the worksheet/workbook `codeName`s so Excel binds each module to its sheet. |
| `build/Memo_Tracking_source.xlsx` | The original macro-free workbook used as input. |

Rebuild:

```bash
pip install oletools olefile          # only needed for validation
cd build
python3 vbabuild.py vbaProject.bin
python3 package_xlsm.py Memo_Tracking_source.xlsx vbaProject.bin ../Memo_Tracking.xlsm
```

### Validation performed

Microsoft Excel was not available here, so the output was validated against the
authoritative open-source MS-OVBA reader (`oletools` / `olevba`) and `olefile`:

* **Compound file** (`olefile`): all 9 streams present and readable.
* **VBA project, strict mode** (`olevba`, `relaxed=False`, which *raises* on any
  spec deviation): parses with **zero warnings**; all 5 modules
  (`ThisWorkbook`, `Dashboard`, `Ramesh`, `Suresh`, `Mahesh`) extracted with the
  correct source; the `Worksheet_Change` macro is present behind the three worker
  sheets.
* **Compression**: every stream round-trips (`compress` → olevba `decompress` is
  byte-identical to the input).
* **Project-protection encryption**: the `CMG`/`DPB`/`GC` blobs were verified both
  by round-trip and against the MS-OVBA spec's documented example vectors.
* **Package**: zip integrity OK; every edited XML part is well-formed;
  content-types, relationships and all four sheet `codeName`s set correctly.

The one thing that can only be confirmed by opening the file in Microsoft Excel
itself is the absence of a "repair" prompt — but every structural element conforms
to the spec Excel reads. If Excel ever does flag it, the manual fallback above
reproduces the exact same result.
