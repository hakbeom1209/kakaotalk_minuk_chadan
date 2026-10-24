"""Prepare the Linux x64 cloud toolchain; never rewrite tracked app/build files."""
from pathlib import Path
import gzip
import hashlib
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile

WORK = Path('/workspace')
TOOLS = WORK / '.toolchains'
SDK = WORK / '.android-sdk'
ANDROID_USER = WORK / '.android'
CACHE = WORK / '.gradle-kakao-android'
PROJECT = Path(__file__).resolve().parents[1] / 'android'


def download(url, destination):
    with urllib.request.urlopen(url, timeout=120) as source, destination.open('wb') as target:
        shutil.copyfileobj(source, target)


def prepare_jdk():
    link = TOOLS / 'jdk-21'
    if (link / 'bin/javac').is_file():
        return link
    if link.exists() or link.is_symlink():
        raise RuntimeError('Existing task JDK path is unusable; preserve and inspect it before replacement.')
    keys = TOOLS / 'msjdk-public-keys'
    keys.mkdir(exist_ok=True); keys.chmod(0o700)
    gpg = ['gpg', '--batch', '--homedir', str(keys)]
    with tempfile.TemporaryDirectory(prefix='kakao-jdk-') as temp:
        temp = Path(temp)
        base = 'https://packages.microsoft.com/debian/12/prod/'
        for name, url in [('key.asc', 'https://packages.microsoft.com/keys/microsoft.asc'), ('InRelease', base+'dists/bookworm/InRelease'), ('Packages.gz', base+'dists/bookworm/main/binary-amd64/Packages.gz')]:
            download(url, temp/name)
        shown = subprocess.run(gpg+['--with-colons','--import-options','show-only','--import',str(temp/'key.asc')], capture_output=True, text=True, check=True)
        if 'BC528686B50D79E339D3721CEB3E94ADBE1229CF' not in shown.stdout:
            raise RuntimeError('Unexpected Microsoft signing key fingerprint')
        subprocess.run(gpg+['--import',str(temp/'key.asc')], capture_output=True, check=True)
        subprocess.run(gpg+['--yes','--output',str(temp/'Release'),'--decrypt',str(temp/'InRelease')], capture_output=True, check=True)
        in_sha = False
        expected = None
        for line in (temp/'Release').read_text().splitlines():
            if line == 'SHA256:': in_sha = True; continue
            if line and not line.startswith(' '): in_sha = False
            if in_sha and line.split()[-1:] == ['main/binary-amd64/Packages.gz']: expected = line.split()[0]
        if not expected or hashlib.sha256((temp/'Packages.gz').read_bytes()).hexdigest() != expected:
            raise RuntimeError('Signed package index checksum failed')
        entries = []
        for block in gzip.decompress((temp/'Packages.gz').read_bytes()).decode().split('\n\n'):
            fields = dict(line.split(': ',1) for line in block.splitlines() if ': ' in line and not line.startswith(' '))
            if fields.get('Package') == 'msopenjdk-21' and fields.get('Architecture') == 'amd64': entries.append(fields)
        package = max(entries, key=lambda p: tuple(map(int,re.findall(r'\d+',p['Version']))))
        download(base+package['Filename'], temp/'jdk.deb')
        if hashlib.sha256((temp/'jdk.deb').read_bytes()).hexdigest() != package['SHA256']:
            raise RuntimeError('JDK package checksum failed')
        root = TOOLS/'msjdk-21'; root.mkdir(exist_ok=True)
        subprocess.run(['dpkg-deb','-x',str(temp/'jdk.deb'),str(root)],check=True)
        jdk = next(p for p in (root/'usr/lib/jvm').iterdir() if p.is_dir() and (p/'bin/javac').is_file())
        link.symlink_to(jdk,target_is_directory=True)
    return link


def main():
    if platform.system() != 'Linux' or platform.machine() not in {'x86_64','amd64'}:
        raise RuntimeError('This helper targets the Linux x64 cloud only. Use Android Studio elsewhere.')
    for command in ['gpg','dpkg-deb']:
        if not shutil.which(command): raise RuntimeError(command+' is required')
    for folder in [TOOLS,SDK,ANDROID_USER/'cache',CACHE]: folder.mkdir(parents=True,exist_ok=True)
    jdk = prepare_jdk()
    env = os.environ.copy()
    env.update(JAVA_HOME=str(jdk),ANDROID_HOME=str(SDK),ANDROID_USER_HOME=str(ANDROID_USER),ANDROID_SDK_HOME=str(WORK),GRADLE_USER_HOME=str(CACHE))
    trust = TOOLS/'kakao-java-cacerts'
    cert = os.environ.get('CODEX_PROXY_CERT')
    if cert:
        if not trust.exists(): shutil.copyfile(jdk/'lib/security/cacerts',trust)
        keytool = str(jdk/'bin/keytool')
        exists = subprocess.run([keytool,'-list','-alias','cloud-proxy','-keystore',str(trust),'-storepass','changeit'],capture_output=True).returncode == 0
        if not exists: subprocess.run([keytool,'-importcert','-noprompt','-alias','cloud-proxy','-file',cert,'-keystore',str(trust),'-storepass','changeit'],check=True)
        env['JAVA_TOOL_OPTIONS'] = env.get('JAVA_TOOL_OPTIONS','')+' -Djavax.net.ssl.trustStore='+str(trust)
    proxy = urllib.parse.urlparse(os.environ.get('HTTPS_PROXY',os.environ.get('https_proxy','')))
    proxy_args = []
    properties = CACHE/'gradle.properties'
    if proxy.hostname:
        # Only routing host/port; authentication remains with the platform proxy.
        lines = properties.read_text().splitlines() if properties.exists() else []
        lines = [line for line in lines if not re.match(r'systemProp\.https?\.proxy(?:Host|Port)=',line)]
        for protocol in ['http','https']:
            lines += [f'systemProp.{protocol}.proxyHost={proxy.hostname}',f'systemProp.{protocol}.proxyPort={proxy.port or 80}']
        properties.write_text('\n'.join(lines)+'\n')
        proxy_args = ['--proxy=http',f'--proxy_host={proxy.hostname}',f'--proxy_port={proxy.port or 80}']
    cli = SDK/'cmdline-tools/19.0'
    if not (cli/'bin/sdkmanager').exists():
        if cli.exists(): raise RuntimeError('Preserve and inspect the incomplete existing command-line tools directory')
        with tempfile.TemporaryDirectory(prefix='kakao-sdk-') as temp:
            archive = Path(temp)/'sdk.zip'
            download('https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip',archive)
            # Google's HTTPS repository metadata checksum for command-line tools 19.0.
            if hashlib.sha1(archive.read_bytes()).hexdigest() != '5fdcc763663eefb86a5b8879697aa6088b041e70':
                raise RuntimeError('Android command-line tools checksum failed')
            with zipfile.ZipFile(archive) as zipped: zipped.extractall(temp)
            cli.parent.mkdir(exist_ok=True); shutil.move(str(Path(temp)/'cmdline-tools'),cli)
            for binary in (cli/'bin').iterdir(): binary.chmod(binary.stat().st_mode | 0o111)
    with (ANDROID_USER/'sdk-setup.log').open('w') as log:
        subprocess.run([str(cli/'bin/sdkmanager'),'--sdk_root='+str(SDK),*proxy_args,'platforms;android-35','build-tools;35.0.0','platform-tools'],input='y\n'*30,text=True,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    lines = [f'export {name}={value}' for name,value in [('JAVA_HOME',jdk),('ANDROID_HOME',SDK),('ANDROID_USER_HOME',ANDROID_USER),('ANDROID_SDK_HOME',WORK),('GRADLE_USER_HOME',CACHE)]]
    lines += ['export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"']
    if cert: lines += ['export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djavax.net.ssl.trustStore='+str(trust)+'"']
    (TOOLS/'android-env.sh').write_text('\n'.join(lines)+'\n')
    # Use ANDROID_HOME; preserve an existing local.properties rather than overwrite it.
    subprocess.run([str(PROJECT/'gradlew'),'--no-daemon',':app:assembleDebug',':app:assembleRelease',':app:testReleaseUnitTest',':app:lintRelease'],cwd=PROJECT,env=env,check=True)
    subprocess.run([str(SDK/'build-tools/35.0.0/apksigner'),'verify',str(PROJECT/'app/build/outputs/apk/release/app-release.apk')],env=env,check=True)
    print('Android build, unit tests, lint and APK signature passed. Source /workspace/.toolchains/android-env.sh in new shells.')


if __name__ == '__main__':
    main()
