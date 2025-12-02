Param(
  [Parameter(Mandatory = $true)]
  [string]$Input,

  [Parameter(Mandatory = $true)]
  [string]$Out
)

$ErrorActionPreference = 'Stop'

if (!(Test-Path -LiteralPath $Input)) {
  Write-Error "找不到輸入 CSV: $Input"
  exit 1
}

function Pick-Col($row, [string[]]$names) {
  foreach ($n in $names) {
    if ($row.PSObject.Properties.Name -contains $n) {
      $v = $row.$n
      if ($null -ne $v -and "$v".Trim() -ne '') { return $v }
    }
  }
  return $null
}

$data = Import-Csv -LiteralPath $Input
$mapped = @()
foreach ($row in $data) {
  $name = Pick-Col $row @('路徑名稱','路線名稱','路線','路名')
  $direction = Pick-Col $row @('路程','方向','去回程')
  $seq = Pick-Col $row @('站次','站序','序號','順序')
  $stopName = Pick-Col $row @('站點','站名','站點名稱')
  $eta = Pick-Col $row @('首站到此站時間','預估到站(分)','行駛時間(分)','行車時間','預估行車(分)')
  $lat = Pick-Col $row @('去程緯度','緯度','Lat','lat','Latitude','Y','y')
  $lng = Pick-Col $row @('去程經度','經度','Lng','lng','Longitude','X','x')

  $seqNum = $null; if ($seq -ne $null -and "$seq" -ne '') { try { $seqNum = [int]$seq } catch { $seqNum = $seq } }
  $etaNum = $null; if ($eta -ne $null -and "$eta" -ne '') { try { $etaNum = [int]$eta } catch { $etaNum = $eta } }
  $latNum = $null; if ($lat -ne $null -and "$lat" -ne '') { try { $latNum = [double]$lat } catch { $latNum = $lat } }
  $lngNum = $null; if ($lng -ne $null -and "$lng" -ne '') { try { $lngNum = [double]$lng } catch { $lngNum = $lng } }

  $mapped += [PSCustomObject]@{
    '路徑名稱' = $name
    '路程' = $direction
    '站次' = $seqNum
    '站點' = $stopName
    '首站到此站時間' = $etaNum
    '去程緯度' = $latNum
    '去程經度' = $lngNum
  }
}

$mapped = $mapped | Where-Object { $_.'路徑名稱' -or $_.'站點' -or $_.'去程緯度' -or $_.'去程經度' }

$contentJson = $mapped | ConvertTo-Json -Depth 5 -Compress
$content = "export default $contentJson`n"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Out) | Out-Null
Set-Content -Path $Out -Value $content -Encoding UTF8
Write-Host ("已輸出 {0} 筆 -> {1}" -f $mapped.Count, $Out)

