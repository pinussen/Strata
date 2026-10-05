"""Exercise CUDA architecture admission with a real CUDA 12 toolkit; no GPU or downloads.

STRATA_TEST_CMAKE and STRATA_TEST_NVCC may select the tools. The normal setup unit tests
do not require CUDA; this separate suite skips when the toolkit is unavailable.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CMAKE = os.environ.get("STRATA_TEST_CMAKE") or shutil.which("cmake")
NVCC = os.environ.get("STRATA_TEST_NVCC") or shutil.which("nvcc")


@unittest.skipUnless(CMAKE and NVCC, "CMake and a CUDA toolkit are required")
class ArchitectureConfigure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run([NVCC, "--version"], capture_output=True, text=True, check=True)
        if "release 12." not in result.stdout:
            raise unittest.SkipTest("this matrix targets CUDA 12 (Maxwell, Pascal, Volta and Turing)")

    def configure(self, arch, flag=None):
        with tempfile.TemporaryDirectory(prefix="strata-cuda-arch-") as build:
            args = [CMAKE, "-S", str(ROOT), "-B", build, "-DSTRATA_ENABLE_CUDA=ON",
                    "-DSTRATA_BUILD_TESTS=OFF", "-DSTRATA_NATIVE_EXPERTS=OFF",
                    f"-DCMAKE_CUDA_COMPILER={NVCC}", f"-DCMAKE_CUDA_ARCHITECTURES={arch}"]
            if flag:
                args.append(f"-D{flag}=ON")
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            return result.returncode, result.stdout + result.stderr

    def test_maxwell_requires_its_own_opt_in(self):
        for flag in (None, "STRATA_EXPERIMENTAL_SM60"):
            with self.subTest(flag=flag):
                code, output = self.configure(50, flag)
                self.assertNotEqual(code, 0, output)
                self.assertIn("STRATA_EXPERIMENTAL_SM50", output)

    def test_supported_architectures_configure(self):
        for arch, flag in ((50, "STRATA_EXPERIMENTAL_SM50"),
                           (60, "STRATA_EXPERIMENTAL_SM60"),
                           (70, "STRATA_EXPERIMENTAL_SM60"), (75, None)):
            with self.subTest(arch=arch, flag=flag):
                code, output = self.configure(arch, flag)
                self.assertEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main()
