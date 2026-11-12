"""Select a trusted CA bundle and check verified HTTPS before Spack bootstrap."""
import argparse
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request


def select_bundle():
    explicit=os.environ.get('TSV_CA_BUNDLE') or os.environ.get('SSL_CERT_FILE')
    if explicit:
        bundle=Path(explicit).expanduser().resolve()
        if not bundle.is_file():raise ValueError(f'Configured CA bundle is missing: {bundle}')
        return bundle
    defaults=ssl.get_default_verify_paths()
    candidates=[defaults.cafile,'/opt/homebrew/etc/ca-certificates/cert.pem',
                '/opt/homebrew/etc/openssl@3/cert.pem','/etc/ssl/cert.pem']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():return Path(candidate).resolve()
    raise ValueError('No CA bundle found; provide a trusted PEM file using TSV_CA_BUNDLE')


def trusted_context(bundle):
    context=ssl.create_default_context(cafile=str(bundle))
    if context.verify_mode!=ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError('TLS certificate and hostname verification must remain enabled')
    if context.cert_store_stats()['x509_ca']==0:raise ValueError('CA bundle contains no trusted CA certificates')
    return context


def check_https(url,context):
    try:
        with urllib.request.urlopen(url,context=context,timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        # Any HTTP response proves this verified TLS handshake succeeded.
        # Mirrors need not serve an index page, and registries require auth.
        code=error.code
        error.close()
        return code


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--print-bundle',action='store_true')
    parser.add_argument('--check-network',action='store_true')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    report={'python':sys.executable,'status':'not_verified'}
    try:
        bundle=select_bundle();context=trusted_context(bundle)
        report.update(ca_bundle=str(bundle),trusted_ca_count=context.cert_store_stats()['x509_ca'],
                      certificate_verification=True,hostname_verification=True)
        if args.check_network:
            report['https_checks']={}
            for url in ('https://github.com/','https://mirror.spack.io/','https://ghcr.io/v2/'):
                report['https_checks'][url]=check_https(url,context)
        report['status']='verified_https' if args.check_network else 'local_ca_bundle_valid'
        if args.print_bundle:print(bundle)
        else:print(json.dumps(report,indent=2))
    except Exception as error:
        report['error']=str(error)
        print('TLS setup failed: '+str(error),file=sys.stderr)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['status']!='not_verified' else 1


if __name__=='__main__':raise SystemExit(main())
