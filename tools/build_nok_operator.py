"""Build a versioned, self-contained PowerShell operator from reviewed repo code.

No production files, secrets, runtime content or keys are ever packaging inputs.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=('wire.py','operator_common.py','openssl_delegate.py','render_worker.py','windows_operator.py',
       '1-KLARGJOR.cmd','2-GODKJENN-OG-AKTIVER.cmd','VERSION','README.md')


def build(destination):
    source=ROOT/'tools/nok_operator'
    version=(source/'VERSION').read_text().strip()
    values={name:(source/name).read_bytes() for name in FILES}
    manifest=dict(version=version,files={n:hashlib.sha256(v).hexdigest() for n,v in values.items()})
    values['MANIFEST.json']=json.dumps(manifest,sort_keys=True,indent=2).encode()
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',compression=zipfile.ZIP_DEFLATED) as packed:
        for name,data in values.items():
            info=zipfile.ZipInfo(name,date_time=(2026,10,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o600<<16;packed.writestr(info,data)
    payload=memory.getvalue();encoded=base64.b64encode(payload).decode()
    template=r'''# NOK-operator __VERSION__. Kopier HELE teksten til Windows PowerShell.
& {
 $ErrorActionPreference = 'Stop'
 $NokPayload = [Convert]::FromBase64String('__PAYLOAD__')
 $NokHasher = [Security.Cryptography.SHA256]::Create()
 try { $NokDigest = ([BitConverter]::ToString($NokHasher.ComputeHash($NokPayload))).Replace('-','').ToLowerInvariant() }
 finally { $NokHasher.Dispose() }
 if ($NokDigest -ne '__SHA__') { throw 'Operatorkoden har feil SHA256. Ingen handling.' }
 $NokDestination = Join-Path $env:LOCALAPPDATA ('AksjeNokOperator\operator-__VERSION__-' + [Guid]::NewGuid().ToString('N'))
 [void][IO.Directory]::CreateDirectory($NokDestination)
 Add-Type -AssemblyName System.IO.Compression
 $NokMemory = [IO.MemoryStream]::new($NokPayload,$false)
 $NokArchive = [IO.Compression.ZipArchive]::new($NokMemory,[IO.Compression.ZipArchiveMode]::Read)
 try {
  foreach ($NokEntry in $NokArchive.Entries) {
   if ($NokEntry.Name -ne $NokEntry.FullName -or [string]::IsNullOrWhiteSpace($NokEntry.Name)) { throw 'Ugyldig operatorkode.' }
   $NokInput = $NokEntry.Open()
   $NokOutput = [IO.File]::Open((Join-Path $NokDestination $NokEntry.Name),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
   try { $NokInput.CopyTo($NokOutput) } finally { $NokOutput.Dispose(); $NokInput.Dispose() }
  }
 } finally { $NokArchive.Dispose(); $NokMemory.Dispose() }
 Write-Host ('NOK-operator __VERSION__: ' + $NokDestination)
 Write-Host 'Starter kun ordrefri aktiveringskontroll. Stopper ved personlig B.'
 $NokPython = Get-Command py.exe -ErrorAction SilentlyContinue
 if ($NokPython) { & $NokPython.Source -3 (Join-Path $NokDestination 'windows_operator.py') prepare }
 else { & python.exe (Join-Path $NokDestination 'windows_operator.py') prepare }
 if ($LASTEXITCODE -ne 0) { throw ('Klargjoringen stoppet. Resultater og privat logg er bevart. Kode: ' + $NokDestination) }
}
'''
    script=template.replace('__VERSION__',version).replace('__PAYLOAD__',encoded).replace('__SHA__',hashlib.sha256(payload).hexdigest())
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(script,encoding='utf-8-sig')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'docs/nok_operator/START-HER.ps1'))
    print(json.dumps(build(parser.parse_args().output),indent=2))
