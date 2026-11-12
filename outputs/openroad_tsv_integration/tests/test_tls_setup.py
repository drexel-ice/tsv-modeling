"""Exercise the local CA store while retaining full TLS verification."""
from pathlib import Path
import os
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'em'))
from tls_setup import select_bundle,trusted_context

class TLSSetupTests(unittest.TestCase):
    def test_actual_ca_store_requires_certificate_and_hostname(self):
        context=trusted_context(select_bundle())
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()['x509_ca'],0)

    def test_explicit_missing_bundle_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{'TSV_CA_BUNDLE':str(Path(directory)/'missing.pem')}):
                with self.assertRaisesRegex(ValueError,'missing'):select_bundle()

    def test_invalid_pem_rejected_by_ssl(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.pem';path.write_text('not a certificate')
            with self.assertRaises(ssl.SSLError):trusted_context(path)

if __name__=='__main__':unittest.main()
