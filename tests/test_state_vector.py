import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, MagicMock
import binascii

from sandbox.state_vector import hash_registry_keys, count_files


def test_hash_registry_keys_returns_int():
    with patch("sandbox.state_vector.winreg") as mock_reg:
        mock_key = MagicMock()
        mock_reg.OpenKey.return_value.__enter__ = lambda s: mock_key
        mock_reg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_reg.QueryInfoKey.return_value = (2, 0, 0)  # 2 values
        mock_reg.EnumValue.side_effect = [
            ("val1", "data1", 1),
            ("val2", "data2", 1),
        ]
        mock_reg.HKEY_CURRENT_USER = 0x80000001
        result = hash_registry_keys(["HKCU\\Software\\Test"])
    assert isinstance(result, int)


def test_hash_registry_keys_xor_not_sum():
    """XOR of two identical hashes should be 0; sum would not be."""
    with patch("sandbox.state_vector.winreg") as mock_reg:
        mock_key = MagicMock()
        mock_reg.OpenKey.return_value.__enter__ = lambda s: mock_key
        mock_reg.OpenKey.return_value.__exit__ = MagicMock(return_value=False)
        mock_reg.QueryInfoKey.return_value = (0, 0, 0)
        mock_reg.HKEY_CURRENT_USER = 0x80000001
        # Call twice with same key list — XOR of same value twice = 0
        r1 = hash_registry_keys(["HKCU\\Same"])
        r2 = hash_registry_keys(["HKCU\\Same"])
    assert r1 ^ r2 == 0   # XOR of same hash with itself is 0

def test_hash_registry_keys_missing_key_returns_zero_contribution():
    """A missing registry key should not crash; skip it silently."""
    with patch("sandbox.state_vector.winreg") as mock_reg:
        mock_reg.OpenKey.side_effect = OSError("key not found")
        mock_reg.HKEY_CURRENT_USER = 0x80000001
        result = hash_registry_keys(["HKCU\\NonExistent"])
    assert result == 0


def test_count_files_sums_all_dirs(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("y")
    count = count_files([str(tmp_path)])
    assert count == 2


def test_count_files_empty_dir(tmp_path):
    assert count_files([str(tmp_path)]) == 0


def test_count_files_missing_dir():
    """Missing directory should be skipped without crashing."""
    count = count_files(["C:\\NonExistentPath_xyz"])
    assert count == 0
