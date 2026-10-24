"""Windows USB installation diagnostics; only the selected app is installed.

The tool downloads Google's Windows platform-tools with its published checksum.
It never changes phone security settings or uninstalls an application.
"""
from pathlib import Path
import hashlib
import os
import platform
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

APK_NAME = "KakaoMessageFilter-Android-0.1.3.apk"
APK_SHA256 = "08fb7560b0a0ac6a9b6e48f3f0055177a9e3f1c37a1559dd0996c793e0b8ca5d"
REPOSITORY = "https://dl.google.com/android/repository/"


def verify_apk(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != APK_SHA256:
        raise RuntimeError("APK checksum differs. Use the unmodified 0.1.3 APK from the diagnostic bundle.")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() or "AndroidManifest.xml" not in archive.namelist() or "classes.dex" not in archive.namelist():
            raise RuntimeError("APK ZIP validation failed")


def windows_tools(metadata):
    root = ET.fromstring(metadata)
    tag = lambda element: element.tag.rsplit("}", 1)[-1]
    for package in root.iter():
        if tag(package) != "remotePackage" or package.get("path") != "platform-tools":
            continue
        for archive in package.iter():
            if tag(archive) != "archive":
                continue
            children = {tag(child): child for child in archive}
            if children.get("host-os") is None or children["host-os"].text != "windows":
                continue
            complete = children.get("complete")
            if complete is None:
                continue
            fields = {tag(child): child.text for child in complete}
            checksum = fields.get("checksum", "").strip().lower()
            url = urllib.parse.urljoin(REPOSITORY, fields.get("url", ""))
            if urllib.parse.urlparse(url).scheme != "https" or urllib.parse.urlparse(url).hostname != "dl.google.com" or not re.fullmatch(r"[0-9a-f]{40}", checksum):
                raise RuntimeError("Unexpected SDK archive URL or checksum")
            return url, checksum
    raise RuntimeError("Windows platform-tools missing from Google's SDK metadata")


def extract_tools(archive, destination, expected):
    if hashlib.sha1(archive.read_bytes()).hexdigest() != expected:
        raise RuntimeError("Google SDK archive checksum failed")
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            parts = item.filename.replace("\\", "/").split("/")
            if not parts or parts[0] != "platform-tools" or ".." in parts or ":" in item.filename:
                raise RuntimeError("Unexpected SDK archive path")
        zipped.extractall(destination)
    adb = destination / "platform-tools" / "adb.exe"
    if not adb.is_file():
        raise RuntimeError("adb.exe missing from the verified SDK archive")
    return adb


def failure_code(output):
    found = re.search(r"(?:INSTALL|INSTALL_PARSE)_FAILED_[A-Z0-9_]+", output)
    return found.group(0) if found else None


def download(url, path):
    with urllib.request.urlopen(url, timeout=90) as response, path.open("wb") as target:
        import shutil
        shutil.copyfileobj(response, target)


def run_adb(adb, arguments, timeout=30):
    result = subprocess.run([str(adb), "-d", *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return result.returncode, result.stdout.strip()


def main():
    if platform.system() != "Windows":
        raise RuntimeError("Run this tool on the Windows PC connected to your phone")
    folder = Path(__file__).resolve().parent
    apk = folder / APK_NAME
    verify_apk(apk)
    print("APK checksum and ZIP: OK (0.1.3)")
    print("This tool attempts to install this APK on ONE USB-connected phone.")
    print("Connect the phone, enable USB debugging yourself, and approve its USB debugging dialog.")
    print("It does not uninstall apps or alter security/verification settings.")
    cache = Path(os.environ.get("LOCALAPPDATA", str(folder))) / "KakaoFilterInstallDiagnostics"
    cache.mkdir(parents=True, exist_ok=True)
    metadata = cache / "repository.xml"
    download(REPOSITORY + "repository2-1.xml", metadata)
    url, checksum = windows_tools(metadata.read_bytes())
    archive = cache / "platform-tools.zip"
    if not archive.exists() or hashlib.sha1(archive.read_bytes()).hexdigest() != checksum:
        print("Downloading official Google platform-tools...")
        download(url, archive)
    adb = extract_tools(archive, cache, checksum)
    ready = False
    for _ in range(30):
        code, output = run_adb(adb, ["get-state"], timeout=10)
        if code == 0 and output.splitlines()[-1:] == ["device"]:
            ready = True
            break
        print("Waiting for one USB phone and its debugging approval...")
        time.sleep(2)
    if not ready:
        raise RuntimeError("USB phone not authorized/found. Check the data cable, USB debugging, and Samsung USB driver. Connect one phone only.")
    record = ["Kakao Message Filter installation diagnosis", "APK SHA256: " + APK_SHA256]
    for label, prop in [("Model", "ro.product.model"), ("Android", "ro.build.version.release"), ("SDK", "ro.build.version.sdk")]:
        code, value = run_adb(adb, ["shell", "getprop", prop])
        if code:
            raise RuntimeError("Cannot read phone version")
        record.append(label + ": " + value)
    print("Installing the verified APK; the phone may ask you to confirm...")
    code, output = run_adb(adb, ["install", "-r", str(apk)], timeout=180)
    output = output.replace(str(apk), "<APK>").replace(str(folder), "<folder>")
    result = failure_code(output) or ("SUCCESS" if code == 0 and "Success" in output else "NO_INSTALL_ERROR_CODE")
    record += ["Result: " + result, "ADB exit: " + str(code), output]
    log = folder / "INSTALL_RESULT.txt"
    log.write_text("\n".join(record) + "\n", encoding="utf-8-sig")
    print("\n" + "\n".join(record))
    print("\nSaved INSTALL_RESULT.txt next to this script. Share its Result/Failure line for diagnosis.")
    return 0 if result == "SUCCESS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("ERROR:", error, file=sys.stderr)
        raise SystemExit(1)
