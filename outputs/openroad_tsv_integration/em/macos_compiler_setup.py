"""Probe Apple's libc++ search path and configure scoped Spack compiler flags.

Run through `spack python`; no system compiler or SDK files are changed.
"""
import argparse
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

SOURCE='''#include <cerrno>
#include <exception>
#include <iostream>
#include <numeric>
#include <sstream>
#include <vector>
int main(){std::vector<int> v{1,2};std::stringstream s;
s << std::accumulate(v.begin(),v.end(),0);std::cout << s.str();return s.str()=="3"?0:1;}
'''


def sdk_flags(existing,sdk):
    """Preserve user flags, append an explicit libc++ SDK include path once."""
    tokens=shlex.split(existing)
    headers=str(Path(sdk)/'usr/include/c++/v1')
    pair=['-isystem',headers]
    if not any(tokens[i:i+2]==pair for i in range(len(tokens)-1)):
        tokens+=pair
    return shlex.join(tokens)


def probe(cxx,flags=''):
    with tempfile.TemporaryDirectory(prefix='tsv-cxx-probe-') as directory:
        root=Path(directory);source=root/'probe.cpp';source.write_text(SOURCE)
        cmd=[cxx,*shlex.split(flags),'-std=c++17',str(source),'-o',str(root/'probe')]
        built=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if built.returncode:return {'passed':False,'command':cmd,'output':built.stdout}
        ran=subprocess.run([str(root/'probe')],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        return {'passed':ran.returncode==0 and ran.stdout=='3','command':cmd,'output':built.stdout+ran.stdout}


def audit_lockfile(path,sdk,installation_database=None):
    path=Path(path)
    if not path.exists():return {'status':'not_concretized','missing_flags':[],'checked':0}
    specs=json.loads(path.read_text()).get('concrete_specs',{})
    header=str(Path(sdk)/'usr/include/c++/v1')
    installs={}
    if installation_database is not None and Path(installation_database).is_file():
        database=json.loads(Path(installation_database).read_text())
        installs=database.get('database',{}).get('installs',{})
    missing=[];missing_preprocessor=[];checked=0;reused=[]
    for package_hash,spec in specs.items():
        if spec.get('external'):continue
        apple_cxx=any(dep.get('name')=='apple-clang' and 'cxx' in dep.get('parameters',{}).get('virtuals',[])
                      for dep in spec.get('dependencies',[]))
        if not apple_cxx:continue
        record=installs.get(package_hash,{})
        prefix=record.get('path')
        if record.get('installed') is True and prefix and Path(prefix).is_dir():
            reused.append({'name':spec['name'],'hash':package_hash,'prefix':prefix})
            continue
        checked+=1
        flags=spec.get('parameters',{}).get('cxxflags',[])
        tokens=[token for flag in flags for token in shlex.split(flag)]
        if header not in tokens and '-isystem'+header not in tokens:
            missing.append(spec['name'])
        if spec['name']=='petsc':
            cppflags=spec.get('parameters',{}).get('cppflags',[])
            cpp_tokens=[token for flag in cppflags for token in shlex.split(flag)]
            if header not in cpp_tokens and '-isystem'+header not in cpp_tokens:
                missing_preprocessor.append(spec['name'])
    ssh=[spec for spec in specs.values() if spec['name']=='openssh']
    system_ssh=all((spec.get('external') or {}).get('path')=='/usr' for spec in ssh)
    status='passed' if (checked or reused) and not missing else 'missing_sdk_flags'
    if missing_preprocessor:status='missing_preprocessor_sdk_flags'
    if not system_ssh:status='openssh_not_system_external'
    return {'status':status,'missing_flags':sorted(missing),'checked':checked,
            'reused_installed':reused,'system_openssh_verified':system_ssh,
            'missing_preprocessor_flags':missing_preprocessor}


def system_ssh_version():
    for executable in ('/usr/bin/ssh','/usr/bin/scp'):
        if not os.path.isfile(executable) or not os.access(executable,os.X_OK):
            raise RuntimeError('Required macOS SSH client command is unavailable: '+executable)
    output=subprocess.check_output(['/usr/bin/ssh','-V'],stderr=subprocess.STDOUT,text=True)
    match=re.search(r'OpenSSH_([0-9]+\.[0-9]+(?:p[0-9]+)?)',output)
    if not match:raise RuntimeError('Cannot identify the installed macOS OpenSSH client version')
    return match.group(1),output.strip()


def with_system_ssh(data,version):
    import copy
    updated=copy.deepcopy(data)
    package=updated['spack'].setdefault('packages',{}).setdefault('openssh',{})
    external={'spec':'openssh@'+version,'prefix':'/usr'}
    externals=package.setdefault('externals',[])
    if external not in externals:externals.append(external)
    package['buildable']=False
    return updated,updated!=data


def ensure_system_ssh(environment):
    import spack.spec
    import spack.util.spack_yaml as syaml
    version,description=system_ssh_version()
    filename=Path(environment)/'spack.yaml'
    data=syaml.load(filename.read_text());updated,changed=with_system_ssh(data,version)
    spack.spec.Spec('openssh@'+version)
    if changed:
        filename.with_name('spack.yaml.before-system-ssh-'+str(time.time_ns())).write_bytes(filename.read_bytes())
        filename.write_text(syaml.dump_config(updated))
    return {'version':version,'description':description,'prefix':'/usr','changed':changed}


SDK_REQUIREMENT_MESSAGE='TSV EM: Apple C++ packages require the selected SDK libc++ headers'
PETSC_CPP_REQUIREMENT_MESSAGE='TSV EM: PETSc C++ preprocessing requires SDK libc++ headers'


def with_sdk_requirement(data,sdk):
    import copy
    updated=copy.deepcopy(data)
    all_packages=updated['spack'].setdefault('packages',{}).setdefault('all',{})
    requirements=all_packages.get('require',[])
    if isinstance(requirements,str):requirements=[requirements]
    if not isinstance(requirements,list):raise ValueError('Unsupported existing package requirements')
    requirement={'spec':'cxxflags='+json.dumps('-isystem '+str(Path(sdk)/'usr/include/c++/v1')),
                 'when':'%cxx=apple-clang','message':SDK_REQUIREMENT_MESSAGE}
    requirements=[item for item in requirements if not (isinstance(item,dict) and item.get('message')==SDK_REQUIREMENT_MESSAGE)]
    requirements.append(requirement)
    all_packages['require']=requirements
    # PETSc preprocesses separately from compilation. Spack's wrapper omits
    # cxxflags in -E mode, while cppflags reach this mode through OMPI_CXX.
    petsc=updated['spack']['packages'].setdefault('petsc',{})
    cpp_requirements=petsc.get('require',[])
    if isinstance(cpp_requirements,str):cpp_requirements=[cpp_requirements]
    if not isinstance(cpp_requirements,list):raise ValueError('Unsupported PETSc requirements')
    cpp_requirements=[item for item in cpp_requirements if not (
        isinstance(item,dict) and item.get('message')==PETSC_CPP_REQUIREMENT_MESSAGE)]
    # A package-specific require replaces packages:all:require in Spack.
    # Keep both flags in this single PETSc constraint.
    cpp_requirements.append({'spec':requirement['spec']+' cppflags='+json.dumps('-isystem '+str(Path(sdk)/'usr/include/c++/v1')),
                             'when':'%cxx=apple-clang','message':PETSC_CPP_REQUIREMENT_MESSAGE})
    petsc['require']=cpp_requirements
    return updated,updated!=data


def ensure_sdk_requirements(environment,sdk):
    """Explicit per-package requirements also cover dependencies declaring only C++."""
    import spack.spec
    import spack.util.spack_yaml as syaml
    filename=Path(environment)/'spack.yaml'
    data=syaml.load(filename.read_text())
    updated,changed=with_sdk_requirement(data,sdk)
    requirement=updated['spack']['packages']['all']['require'][-1]
    # Validate both expressions with the installed Spack parser before writing.
    spack.spec.Spec(requirement['spec']);spack.spec.Spec(requirement['when'])
    cpp_requirement=updated['spack']['packages']['petsc']['require'][-1]
    spack.spec.Spec(cpp_requirement['spec']);spack.spec.Spec(cpp_requirement['when'])
    if not changed:return False
    backup=filename.with_name('spack.yaml.before-sdk-requirement-'+str(time.time_ns()))
    backup.write_bytes(filename.read_bytes())
    filename.write_text(syaml.dump_config(updated))
    return True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--environment',type=Path,required=True)
    parser.add_argument('--install-db',type=Path,help='Spack install database for exact-hash reuse checks')
    parser.add_argument('--audit-lock',action='store_true',help='check concrete dependency flags before any build')
    args=parser.parse_args()
    install_db=args.install_db or args.environment.parent/'packages/.spack-db/index.json'
    sdk=Path(subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip())
    if args.audit_lock:
        report=audit_lockfile(args.environment/'spack.lock',sdk,install_db)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
        if report['status']!='passed':raise RuntimeError('Dependency plan audit failed: '+report['status']+'; missing SDK flags: '+', '.join(report['missing_flags'])+'; missing preprocessor flags: '+', '.join(report.get('missing_preprocessor_flags',[])))
        print('SDK flags verified for '+str(report['checked'])+' C++ packages needing build; '+str(len(report['reused_installed']))+' installed packages reused')
        return
    import spack.config
    externals=spack.config.get('packages:apple-clang:externals',default=[],scope='user')
    marker=args.environment/'.tsv-sdk-reconcretize-required'
    report={'sdk':str(sdk),'changed':False,'compiler_probes':[]}
    if not externals:raise RuntimeError('No detected Apple Clang compiler in shared Spack user configuration')
    for compiler in externals:
        extra=compiler.get('extra_attributes',{})
        cxx=extra.get('compilers',{}).get('cxx')
        if not cxx:continue
        existing=extra.get('flags',{}).get('cxxflags','')
        before=probe(cxx,existing)
        entry={'compiler':cxx,'before':before}
        if not before['passed']:
            if not (sdk/'usr/include/c++/v1/cerrno').is_file():
                raise RuntimeError('SDK libc++ headers are absent; repair Command Line Tools before building')
            fixed=sdk_flags(existing,sdk);after=probe(cxx,fixed)
            entry['after']=after
            if not after['passed']:
                args.report.parent.mkdir(parents=True,exist_ok=True)
                report['compiler_probes'].append(entry)
                args.report.write_text(json.dumps(report,indent=2)+'\n')
                raise RuntimeError('Explicit SDK include did not repair the C++ compile/link/run probe; see report')
            extra.setdefault('flags',{})['cxxflags']=fixed
            compiler['extra_attributes']=extra
            report['changed']=True
        report['compiler_probes'].append(entry)
    if not report['compiler_probes']:raise RuntimeError('No Apple C++ compiler path to test')
    report['sdk_requirement_changed']=ensure_sdk_requirements(args.environment,sdk)
    report['system_openssh']=ensure_system_ssh(args.environment)
    report['changed']=(report['changed'] or report['sdk_requirement_changed'] or report['system_openssh']['changed'])
    if report['changed']:
        # Preserve the prior lock; force a new solve so compiler defaults reach
        # previously failed dependency specs instead of reusing the old flags.
        lock=args.environment/'spack.lock'
        if lock.exists():
            backup=lock.with_name('spack.lock.before-sdk-flags-'+str(time.time_ns()))
            backup.write_bytes(lock.read_bytes());report['previous_lock_backup']=str(backup)
        marker.write_text('Scoped compiler flags changed; force reconcretization before installation.\n')
        spack.config.set('packages:apple-clang:externals',externals,scope='user')
    report['lock_audit_before']=audit_lockfile(args.environment/'spack.lock',sdk,install_db)
    report['reconcretize_required']=(report['changed'] or marker.exists() or report['lock_audit_before']['status']!='passed')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('Apple Clang probe and system OpenSSH registration passed; scoped macOS configuration '+('updated' if report['changed'] else 'unchanged'))


if __name__=='__main__':main()
