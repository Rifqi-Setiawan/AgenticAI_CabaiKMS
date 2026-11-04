Add-Type -AssemblyName System.Drawing
$root = 'D:\college\Semester 6\Penulisan Proposal\project\data_evaluasi\gambar'
$rows = Import-Csv -Path "$root\manifest\gold_gambar_manifest.csv" -Encoding UTF8
$rows = $rows | Sort-Object label_kind, true_variety, filename
$out = 'C:\Users\Rifqi\AppData\Local\Temp\tinjau'
New-Item -ItemType Directory -Force -Path $out | Out-Null
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
    $img = [System.Drawing.Image]::FromFile((Join-Path "$root\drive_upload" $r.filename))
    $x = ($k % $cols) * ($tw + $pad); $y = [math]::Floor($k / $cols) * ($th + $pad)
    $scale = [math]::Min($tw / $img.Width, $th / $img.Height)
    $w = [int]($img.Width * $scale); $h = [int]($img.Height * $scale)
    $g.DrawImage($img, $x + [int](($tw - $w) / 2), $y + [int](($th - $h) / 2), $w, $h)
    $img.Dispose()
    $g.FillRectangle([System.Drawing.Brushes]::Black, $x, $y, 46, 24)
    $g.DrawString(("{0}" -f ($i + 1)), $font, [System.Drawing.Brushes]::Yellow, $x + 1, $y)
    $index += ("{0},{1},{2},{3},{4}" -f ($i + 1), $r.filename, $r.label_kind, $r.true_variety, $r.true_part)
  }
  $bmp.Save("$out\sheet_{0:D2}.png" -f ($s + 1), [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}
$index | Set-Content "$out\index.csv" -Encoding UTF8
"sheets: " + [math]::Ceiling($rows.Count / $per)
