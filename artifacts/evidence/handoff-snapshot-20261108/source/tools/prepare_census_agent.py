"""Build and sandbox-test the first-party Mac build-JVM diagnostic agent."""
import argparse
import json
import shutil
import socket
import zipfile
from pathlib import Path

from capture import ROOT, capture
from bootstrap_toolchain import sha256
from run_b0_reference import execute, sandbox_policy, require_run


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((ROOT/'artifacts/b0/prepared-04/result.json').read_text())
    home=Path(manifest['javaHome']);driver=ROOT/'artifacts/b0/prepared-04/driver.jar'
    if sha256(home/'bin/java')!=manifest['javaSHA256'] or sha256(driver)!=manifest['binaries']['driver.jar']['sha256']:
        parser.error('Pinned control Java/JAR changed')
    source=ROOT/'interop/diagnostics';shutil.copytree(source,out/'source')
    result={'status':'BLOCKED','scope':'first-party diagnostic self-test only; no game execution'}
    try:
        library=out/'liboomcensus.dylib'
        r=capture(['/usr/bin/xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-dynamiclib',
            '-I'+str(home/'include'),'-I'+str(home/'include/darwin'),str(source/'oom_census.c'),'-o',str(library)],out/'compile',60)
        if r['exitCode']:raise RuntimeError('Agent compile failed')
        r=capture([str(home/'bin/javac'),'--release','25','-proc:none','-d',str(out),str(source/'CensusFixture.java')],out/'compile-fixture',60)
        if r['exitCode']:raise RuntimeError('Fixture compile failed')
        work=out/'work';(work/'tmp').mkdir(parents=True)
        with zipfile.ZipFile(work/'fixture.jar','w') as archive:archive.write(out/'CensusFixture.class','CensusFixture.class')
        shutil.copy2(library,work/library.name)
        policy=out/'policy.sb';policy.write_text(sandbox_policy(work,home,[driver]))
        base=['/usr/bin/sandbox-exec','-f',str(policy),str(home/'bin/java'),'-XX:+DisableAttachMechanism','-XX:-UsePerfData',
            '-Duser.home='+str(work),'-Djava.io.tmpdir='+str(work/'tmp')]
        forbidden=out/'outside-control.txt';forbidden.write_text('agent test control\n')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));sock.listen(1);sock.settimeout(.05)
            step=out/'sandbox-control'
            r=execute([*base,'-Xmx128m','-cp',str(driver),'fabricaot.b0.bootstrap.SandboxProbe',str(forbidden),str(out/'outside-write.txt'),str(sock.getsockname()[1])],step,work)
            require_run(r,step,'B0_SANDBOX_PASS')
            if (out/'outside-write.txt').exists():raise RuntimeError('Outside write allowed')
            try:
                conn,_=sock.accept();conn.close();raise RuntimeError('Network allowed')
            except socket.timeout:pass
        r=execute([*base,'-Xmx24m','-agentpath:'+str(work/library.name)+'='+str(work/'census.tsv'),'-cp',str(work/'fixture.jar'),'CensusFixture'],out/'fixture-run',work,timeout=30,cpu_seconds=30)
        text=(work/'census.tsv').read_text()
        lines=text.splitlines()
        arrays=[line.split('\t') for line in lines if line.startswith('CLASS\t[B\t')]
        if (r['exitCode']!=1 or r['timedOut'] or 'ITERATION_STATUS\t0\t0' not in lines
            or 'CENSUS_END' not in lines or not arrays or int(arrays[0][3])<12*1024**2
            or not any(line.startswith('FRAME\tLCensusFixture;\tmain\t') for line in lines)):
            raise RuntimeError('OOM callback/census self-test failed')
        result.update(status='VERIFIED',sandboxProbe='PASS',fixtureTest='PASS',librarySHA256=sha256(library),
            sourceSHA256=sha256(source/'oom_census.c'),javaSHA256=manifest['javaSHA256'])
    except Exception as error:result['error']=str(error)
    result['filesSHA256']={str(p.relative_to(out)):sha256(p) for p in out.rglob('*') if p.is_file() and p.name!='result.json'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='filesSHA256'},indent=2))
    return 0 if result['status']=='VERIFIED' else 2


if __name__=='__main__':raise SystemExit(main())
