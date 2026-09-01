import base64
import gzip
import hashlib
import unittest
from unittest.mock import patch

from pathlib import Path

from scripts import azure_prediction_worker as worker
from scripts.azure_prediction_worker import patch_from_environment


class AzurePredictionWorkerTests(unittest.TestCase):
    def _environment(self, patch: bytes) -> dict[str, str]:
        encoded = base64.b64encode(gzip.compress(patch, mtime=0)).decode()
        chunks = [encoded[index : index + 7] for index in range(0, len(encoded), 7)]
        return {
            "ESG_PATCH_CHUNK_COUNT": str(len(chunks)),
            "ESG_PATCH_SHA256": hashlib.sha256(patch).hexdigest(),
            **{
                f"ESG_PATCH_CHUNK_{index:03d}": chunk
                for index, chunk in enumerate(chunks)
            },
        }

    def test_patch_transport_round_trips_exact_bytes(self) -> None:
        patch = b"diff --git a/a b/a\n+prospective\n"
        self.assertEqual(patch_from_environment(self._environment(patch)), patch)

    def test_patch_transport_rejects_hash_drift(self) -> None:
        environment = self._environment(b"patch")
        environment["ESG_PATCH_SHA256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            patch_from_environment(environment)

    def test_patch_transport_rejects_unbounded_chunk_count(self) -> None:
        environment = self._environment(b"patch")
        environment["ESG_PATCH_CHUNK_COUNT"] = "129"
        with self.assertRaisesRegex(ValueError, "outside the frozen bound"):
            patch_from_environment(environment)

    def test_git_identity_uses_scoped_safe_directory_without_global_mutation(self) -> None:
        repository = Path("/opt/futureq/evaluator")
        with patch.object(worker, "_checked", return_value="abc") as checked:
            self.assertEqual(worker.git_head(repository), "abc")
        checked.assert_called_once_with(
            [
                "git", "-c", "safe.directory=/opt/futureq/evaluator",
                "rev-parse", "HEAD",
            ],
            cwd=repository,
        )


if __name__ == "__main__":
    unittest.main()
