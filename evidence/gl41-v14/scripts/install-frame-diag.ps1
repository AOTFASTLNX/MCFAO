param([Parameter(Mandatory)][string]$Unsigned)
$ErrorActionPreference='Stop'
$r=$PSScriptRoot
$p="$r/python"
$env:PYTHONPATH="$p;$p/win32;$p/win32/lib"
$env:PATH="$p/pywin32_system32;$env:PATH"
$bundle='app.perseus4004.sunset349'
$exe=Get-ChildItem "$r/zsign" -Filter zsign.exe -Recurse | Select-Object -First 1 -ExpandProperty FullName
$signed="$r/FabricAOT-GL41-frame-diag-signed.ipa"
& $exe -q -z 1 -k "$r/identity.p12" -p ([string][char]49) -m "$r/device.mobileprovision" -b $bundle -r 7 -o $signed $Unsigned
if ($LASTEXITCODE) {throw 'Signing failed'}
@"
import zipfile,plistlib
with zipfile.ZipFile(r'$signed') as z:
 assert z.testzip() is None
 p=plistlib.loads(z.read('Payload/C0Harness.app/Info.plist'))
 assert p['CFBundleIdentifier']=='$bundle'
 assert str(p['CFBundleVersion'])=='7'
 assert b'outsideSwapP95=' in z.read('Payload/C0Harness.app/Frameworks/libglfw.dylib')
"@ | python -
if ($LASTEXITCODE) {throw 'Signed IPA verification failed'}
python -m pymobiledevice3 apps install $signed
if ($LASTEXITCODE) {throw 'Installation failed'}
$query=python -m pymobiledevice3 apps query $bundle | ConvertFrom-Json
if ($LASTEXITCODE -or $query.$bundle.CFBundleVersion -ne '7') {throw 'Installed version verification failed'}
python -m pymobiledevice3 developer dvt launch --userspace $bundle
if ($LASTEXITCODE) {throw 'Launch failed'}
