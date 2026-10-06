from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import private_files as storage


class PrivateFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pam-private-files-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private.dat"

    def append(self, data):
        fd = storage.private_append_fd(self.path)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)

    def assert_private(self):
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.path.stat().st_uid, os.geteuid())
            return
        script = """
        $acl = Get-Acl -LiteralPath $env:PAM_TEST_PRIVATE_FILE -ErrorAction Stop
        $sidType = [System.Security.Principal.SecurityIdentifier]
        $rules = @($acl.GetAccessRules($true, $true, $sidType) | ForEach-Object {
            @{identity=$_.IdentityReference.Value; kind=$_.AccessControlType.ToString(); inherited=$_.IsInherited; mask=[int]$_.FileSystemRights}
        })
        @{owner=$acl.GetOwner($sidType).Value; user=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
          protected=$acl.AreAccessRulesProtected; rules=$rules} | ConvertTo-Json -Compress -Depth 4
        """
        result = json.loads(subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "PAM_TEST_PRIVATE_FILE": str(self.path)}, text=True))
        self.assertEqual(result["owner"], result["user"])
        self.assertTrue(result["protected"])
        self.assertEqual(len(result["rules"]), 1)
        rule = result["rules"][0]
        self.assertEqual(rule["identity"], result["user"])
        self.assertEqual(rule["kind"], "Allow")
        self.assertFalse(rule["inherited"])
        self.assertEqual(rule["mask"] & 0x1F01FF, 0x1F01FF)

    def test_new_file_is_private_to_its_owner(self):
        self.append(b"synthetic private data\n")
        self.assert_private()

    def test_existing_file_is_secured_without_losing_contents(self):
        self.path.write_bytes(b"existing\n")
        self.append(b"additional\n")
        self.assertEqual(self.path.read_bytes(), b"existing\nadditional\n")
        self.assert_private()

    def test_append_keeps_earlier_bytes_and_permissions(self):
        self.append(b"first\n")
        fd = storage.private_append_fd(self.path)
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"second\n")
        finally:
            os.close(fd)
        self.assertEqual(self.path.read_bytes(), b"first\nsecond\n")
        self.assert_private()

    def test_failure_to_secure_file_does_not_append_data(self):
        self.append(b"unchanged\n")
        protection = (patch.object(storage._windows_file_api()[1], "SetSecurityInfo", return_value=5)
                      if os.name == "nt" else patch.object(storage.os, "fchmod", side_effect=PermissionError("denied")))
        with protection, self.assertRaises(OSError):
            self.append(b"must not be written\n")
        self.assertEqual(self.path.read_bytes(), b"unchanged\n")
        self.append(b"recovered\n")
        self.assertEqual(self.path.read_bytes(), b"unchanged\nrecovered\n")

    def test_wrong_owner_is_rejected_before_writing(self):
        self.append(b"unchanged\n")
        wrong_owner = (patch.object(storage._windows_file_api()[1], "EqualSid", return_value=False)
                       if os.name == "nt" else patch.object(storage.os, "fstat",
                           return_value=SimpleNamespace(st_uid=os.geteuid() + 1)))
        with wrong_owner, self.assertRaises(PermissionError):
            self.append(b"must not be written\n")
        self.assertEqual(self.path.read_bytes(), b"unchanged\n")

    def test_descriptor_is_not_inherited_by_child_processes(self):
        fd = storage.private_append_fd(self.path)
        try:
            self.assertFalse(os.get_inheritable(fd))
        finally:
            os.close(fd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
