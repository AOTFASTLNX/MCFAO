param([string[]]$ExtraEnv=@(), [int]$Seconds=45, [string]$Label="default")
$ErrorActionPreference='Stop'
$r=$PSScriptRoot
$p="$r/python"
$env:PYTHONPATH="$p;$p/win32;$p/win32/lib"
$env:PATH="$p/pywin32_system32;$env:PATH"
$args=@('-m','pymobiledevice3','developer','dvt','launch','--userspace','--kill-existing')
foreach($e in $ExtraEnv){$args+='--env';$args+=$e}
$args+='app.perseus4004.sunset349'
$start=Get-Date
& python @args
if($LASTEXITCODE){throw 'launch failed'}
Start-Sleep -Seconds $Seconds
& python -m pymobiledevice3 apps pull --documents app.perseus4004.sunset349 /Documents/c0-logs "$r/bench-$Label"
if($LASTEXITCODE){throw 'log pull failed'}
$log=Get-ChildItem "$r/bench-$Label" -Recurse -Filter 'run-*.log' | Sort-Object Name | Select-Object -Last 1
$lines=Get-Content $log.FullName
$ready=($lines | Select-String 'level_load_ready.*ready=true' | Select-Object -First 1).LineNumber
$startLine=$ready
$disp=$lines[($startLine)..($lines.Count-1)] | Select-String 'display fps=([\d.]+) p95=(\d+)ms long34=(\d+) drops=(\d+)' | ForEach-Object { $_.Matches[0].Groups }
$perf=$lines[($startLine)..($lines.Count-1)] | Select-String 'perf fps=([\d.]+) finish=([\d.]+)ms present=([\d.]+)ms finishP95=(\d+)ms outsideSwapP95=(\d+)ms' | ForEach-Object { $_.Matches[0].Groups }
$fps=@($disp | ForEach-Object {[double]$_[1].Value})
$long=@($disp | ForEach-Object {[int]$_[3].Value})
"label=$Label samples=$($fps.Count) min=$(($fps|Measure-Object -Minimum).Minimum) median=$([math]::Round((($fps|Sort-Object)[[int]($fps.Count/2)]),1)) max=$(($fps|Measure-Object -Maximum).Maximum) long34sum=$(($long|Measure-Object -Sum).Sum)"
