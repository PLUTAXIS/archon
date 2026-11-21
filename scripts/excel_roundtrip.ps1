# Real-Excel round trip for the scrubber (Windows with Excel installed).
# Builds a workbook with every privacy-sensitive feature (client names, quoted text in
# formulas, a dropdown list, a print header, a pivot table, a picture and an external
# link), or opens a file and reports whether Excel had to repair it.
#
#   powershell -ExecutionPolicy Bypass -File scripts\excel_roundtrip.ps1 build C:\temp\roundtrip
#     (put any small logo.png in C:\temp\roundtrip first)
#   python -m archon.scrubber.scrubber C:\temp\roundtrip\monster_original.xlsx -o C:\temp\roundtrip\scrubbed.xlsx
#   python -m archon.scrubber.verify_scrub C:\temp\roundtrip\monster_original.xlsx C:\temp\roundtrip\scrubbed.xlsx Acme Globex Closed Confidential Rates_Secret_Bob <your-windows-user>
#   powershell -ExecutionPolicy Bypass -File scripts\excel_roundtrip.ps1 open C:\temp\roundtrip\scrubbed.xlsx
#     -> expect: repaired=no pivots=1 pictures=1
#
# Excel runs hidden as its own instance; only that instance is closed afterwards.
param([string]$Mode, [string]$Target)
$ErrorActionPreference = "Stop"
$step = "start"

$before = @(Get-Process EXCEL -ErrorAction SilentlyContinue | ForEach-Object Id)
$xl = New-Object -ComObject Excel.Application
$mine = @(Get-Process EXCEL -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id } | ForEach-Object Id)
$xl.Visible = $false
$xl.DisplayAlerts = $false
$xl.AskToUpdateLinks = $false

try {
    if ($Mode -eq "build") {
        $step = "rates workbook"
        $rates = $xl.Workbooks.Add()
        $rates.Worksheets.Item(1).Range("A1").Value2 = [double]0.0725
        $rates.SaveAs((Join-Path $Target "Rates_Secret_Bob.xlsx"), 51)

        $step = "data sheet"
        $wb = $xl.Workbooks.Add()
        $ws = $wb.Worksheets.Item(1)
        $ws.Name = "Data"
        $ws.Range("A1").Value2 = "Client"
        $ws.Range("B1").Value2 = "Region"
        $ws.Range("C1").Value2 = "Revenue"
        $ws.Range("D1").Value2 = "Status"
        $clients = @("Acme Corp", "Globex Ltd", "Initech", "Umbrella plc")
        for ($r = 2; $r -le 21; $r++) {
            $ws.Range("A$r").Value2 = [string]$clients[$r % 4]
            $ws.Range("B$r").Value2 = [string](@("North", "South")[$r % 2])
            $ws.Range("C$r").Value2 = [double](1000 * $r + 0.5)
            $ws.Range("D$r").Value2 = [string](@("Open", "Closed", "Pending")[$r % 3])
            $ws.Range("E$r").Formula = "=IF(D$r=""Closed"",C$r*0.1,0)"
            $ws.Range("F$r").Formula = "=""Client: ""&A$r"
        }
        $step = "external link"
        $ws.Range("G2").Formula = "='" + $Target + "\[Rates_Secret_Bob.xlsx]Sheet1'!`$A`$1"
        $step = "dropdown list"
        $null = $ws.Range("D2:D21").Validation.Add(3, 1, 1, "Open,Closed,Pending")
        $step = "print header"
        $ws.PageSetup.CenterHeader = "Confidential - Acme Q3 board pack"
        $step = "picture"
        $null = $ws.Shapes.AddPicture((Join-Path $Target "logo.png"), 0, -1, 400, 10, 40, 40)
        $step = "pivot table"
        $pivotSheet = $wb.Worksheets.Add()
        $pivotSheet.Name = "Pivot"
        $cache = $wb.PivotCaches().Create(1, "Data!R1C1:R21C4")
        $pt = $cache.CreatePivotTable("Pivot!R3C1", "ByClient")
        $pt.PivotFields("Client").Orientation = 1
        $null = $pt.AddDataField($pt.PivotFields("Revenue"))
        $step = "save"
        $rates.Close($false)
        $out = Join-Path $Target "monster_original.xlsx"
        $wb.SaveAs($out, 51)
        $wb.Close($false)
        "built $out"
    }
    elseif ($Mode -eq "open") {
        $step = "open"
        $logs = { @(Get-ChildItem $env:TEMP -Filter "error*.xml" -ErrorAction SilentlyContinue | ForEach-Object FullName) }
        $logsBefore = & $logs
        $wb = $xl.Workbooks.Open($Target, 0, $true)   # don't update links, read-only
        $sheets = @($wb.Worksheets | ForEach-Object Name) -join ","
        $pivots = ($wb.Worksheets | ForEach-Object { $_.PivotTables().Count } | Measure-Object -Sum).Sum
        $pictures = $wb.Worksheets.Item("Data").Shapes.Count
        $e2 = $wb.Worksheets.Item("Data").Range("E2").Formula
        $wb.Close($false)
        $newLogs = @(& $logs | Where-Object { $logsBefore -notcontains $_ })
        "opened=yes repaired=" + $(if ($newLogs.Count) { "YES" } else { "no" }) + " sheets=$sheets pivots=$pivots pictures=$pictures E2=$e2"
        foreach ($l in $newLogs) { "repair log: " + (Get-Content $l -Raw); Remove-Item $l }
    }
}
catch { "EXCEL ERROR at [$step]: " + $_.Exception.Message }
finally {
    $xl.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
    Start-Sleep -Milliseconds 500
    foreach ($id in $mine) { Stop-Process -Id $id -ErrorAction SilentlyContinue }  # only the Excel we started
}
