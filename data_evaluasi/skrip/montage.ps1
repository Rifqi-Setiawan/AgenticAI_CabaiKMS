Add-Type -AssemblyName System.Drawing
$root = 'D:\college\Semester 6\Penulisan Proposal\project\data_evaluasi\gambar'
$rows = Import-Csv -Path "$root\manifest\gold_gambar_manifest.csv" -Encoding UTF8
# order by class so related images sit together
$newT = Get-Content 'C:\Users\Rifqi\AppData\Local\Temp\cabai_data\new_titles.txt' -Encoding UTF8
$rows = $rows | Where-Object { $newT -contains $_.commons_title }
$rows = $rows | Sort-Object label_kind, true_variety, filename
$out = 'C:\Users\Rifqi\AppData\Local\Temp\cabai_data\review'
New-Item -ItemType Directory -Force -Path $out | Out-Null
Get-ChildItem $out -Filter *.png | Remove-Item -Force
$cols = 4; $per = 12; $tw = 330; $th = 250; $pad = 6
$index = @()
for ($s = 0; $s -lt [math]::Ceiling($rows.Count / $per); $s++) {
  $bmp = New-Object System.Drawing.Bitmap ($cols * ($tw + $pad)), (3 * ($th + $pad))
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::White)
  $g.InterpolationMode = 'HighQualityBicubic'
  $font = New-Object System.Drawing.Font 'Arial', 15, ([System.Drawing.FontStyle]::Bold)
  for ($k = 0; $k -lt $per; $k++) {
    $i = $s * $per + $k
    if ($i -ge $rows.Count) { break }
    $r = $rows[$i]
    $path = Join-Path "$root\drive_upload" $r.filename
    $img = [System.Drawing.Image]::FromFile($path)
    $x = ($k % $cols) * ($tw + $pad); $y = [math]::Floor($k / $cols) * ($th + $pad)
    $scale = [math]::Min($tw / $img.Width, $th / $img.Height)
    $w = [int]($img.Width * $scale); $h = [int]($img.Height * $scale)
    $g.DrawImage($img, $x + [int](($tw - $w) / 2), $y + [int](($th - $h) / 2), $w, $h)
    $img.Dispose()
    $label = "{0}" -f ($i + 1)
    $g.FillRectangle([System.Drawing.Brushes]::Black, $x, $y, 44, 24)
    $g.DrawString($label, $font, [System.Drawing.Brushes]::Yellow, $x, $y)
    $index += [pscustomobject]@{ n = $i + 1; sheet = $s + 1; filename = $r.filename; kind = $r.label_kind; variety = $r.true_variety; reason = $r.uncertain_reason; part = $r.true_part; title = $r.commons_title }
  }
  $bmp.Save("$out\sheet_{0:D2}.png" -f ($s + 1), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}
$index | Export-Csv -Path "$out\index.csv" -NoTypeInformation -Encoding UTF8
"sheets: " + [math]::Ceiling($rows.Count / $per) + " tiles: " + $rows.Count
