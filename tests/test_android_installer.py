from pathlib import Path
import hashlib
import importlib.util
import zipfile
import pytest

source=Path(__file__).parents[1]/"android/tools/install_diagnostics.py"
spec=importlib.util.spec_from_file_location("android_install_diagnostics",source)
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_published_apk_matches_diagnostic_checksum():
    installer.verify_apk(source.parents[1]/"downloads"/installer.APK_NAME)


def test_corrupted_apk_is_rejected_before_using_adb(tmp_path):
    altered=tmp_path/"bad.apk"
    altered.write_bytes(b"not an APK")
    with pytest.raises(RuntimeError,match="checksum"):
        installer.verify_apk(altered)


def test_windows_archive_is_selected_from_google_metadata():
    xml=b'''<repo><remotePackage path="platform-tools"><archives>
    <archive><host-os>linux</host-os><complete><url>linux.zip</url></complete></archive>
    <archive><host-os>windows</host-os><complete><url>platform-tools-win.zip</url><checksum>aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</checksum></complete></archive>
    </archives></remotePackage></repo>'''
    url,digest=installer.windows_tools(xml)
    assert url=="https://dl.google.com/android/repository/platform-tools-win.zip"
    assert digest=="a"*40


def test_sdk_archive_with_wrong_checksum_is_rejected(tmp_path):
    archive=tmp_path/"tools.zip"
    archive.write_bytes(b"broken")
    with pytest.raises(RuntimeError,match="checksum"):
        installer.extract_tools(archive,tmp_path,"0"*40)


def test_unsafe_sdk_archive_paths_are_rejected(tmp_path):
    archive=tmp_path/"tools.zip"
    with zipfile.ZipFile(archive,"w") as z:z.writestr("platform-tools/../escape.exe",b"bad")
    digest=hashlib.sha1(archive.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError,match="path"):
        installer.extract_tools(archive,tmp_path,digest)


@pytest.mark.parametrize("output,expected",[
    ("Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled]","INSTALL_FAILED_USER_RESTRICTED"),
    ("Failure [INSTALL_PARSE_FAILED_NO_CERTIFICATES: failed]","INSTALL_PARSE_FAILED_NO_CERTIFICATES"),
    ("Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: conflicting certificates]","INSTALL_FAILED_UPDATE_INCOMPATIBLE"),
    ("Success",None),
])
def test_installer_error_is_preserved(output,expected):
    assert installer.failure_code(output)==expected
