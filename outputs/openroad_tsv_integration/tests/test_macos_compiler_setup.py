"""Scoped SDK flag construction checks; no system compiler files are modified."""
import shlex
import json
import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'em'))
from macos_compiler_setup import sdk_flags,audit_lockfile,with_sdk_requirement,with_system_ssh

class MacOSCompilerSetupTests(unittest.TestCase):
    def test_sdk_include_added_once(self):
        flags=sdk_flags('', '/example/MacOSX.sdk')
        self.assertEqual(shlex.split(flags),['-isystem','/example/MacOSX.sdk/usr/include/c++/v1'])
        self.assertEqual(sdk_flags(flags,'/example/MacOSX.sdk'),flags)

    def test_existing_flags_are_preserved(self):
        flags=sdk_flags('-O2 -g -stdlib=libc++','/example/MacOSX.sdk')
        self.assertEqual(shlex.split(flags)[:3],['-O2','-g','-stdlib=libc++'])

class ConcreteLockAuditTests(unittest.TestCase):
    def audit(self,flags):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'spack.lock'
            path.write_text(json.dumps({'concrete_specs':{'libceed':{
                'name':'libceed','parameters':{'cxxflags':flags},
                'dependencies':[{'name':'apple-clang','parameters':{'virtuals':['cxx']}}]},
                'c_only':{'name':'c_only','parameters':{},
                'dependencies':[{'name':'apple-clang','parameters':{'virtuals':['c']}}]}}}))
            return audit_lockfile(path,'/SDK')

    def test_stale_plan_rejected(self):
        result=self.audit([])
        self.assertEqual(result['status'],'missing_sdk_flags')
        self.assertEqual(result['missing_flags'],['libceed'])

    def test_effective_dependency_flags_accepted(self):
        for flags in [['-isystem','/SDK/usr/include/c++/v1'],['-isystem /SDK/usr/include/c++/v1']]:
            result=self.audit(flags)
            self.assertEqual(result['status'],'passed')
            self.assertEqual(result['checked'],1)

class InstalledReuseAuditTests(unittest.TestCase):
    def audit(self,installed=True,matching_hash=True,prefix_exists=True):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'installed'
            if prefix_exists:prefix.mkdir()
            lock=root/'spack.lock';db=root/'index.json'
            lock.write_text(json.dumps({'concrete_specs':{'expected_hash':{
                'name':'cached_cpp_package','parameters':{'cxxflags':[]},
                'dependencies':[{'name':'apple-clang','parameters':{'virtuals':['c','cxx']}}]}}}))
            db.write_text(json.dumps({'database':{'installs':{
                'expected_hash' if matching_hash else 'different_hash':
                {'installed':installed,'path':str(prefix)}}}}))
            return audit_lockfile(lock,'/SDK',db)

    def test_exact_installed_package_is_reused_without_build_flag_requirement(self):
        report=self.audit()
        self.assertEqual(report['status'],'passed')
        self.assertEqual(report['checked'],0)
        self.assertEqual(report['reused_installed'][0]['hash'],'expected_hash')

    def test_wrong_hash_failed_install_or_missing_prefix_cannot_bypass_audit(self):
        for kwargs in [{'installed':False},{'matching_hash':False},{'prefix_exists':False}]:
            self.assertEqual(self.audit(**kwargs)['status'],'missing_sdk_flags')

class PackageRequirementTests(unittest.TestCase):
    def test_petsc_preprocessor_requirement_is_scoped_and_preserves_options(self):
        data={'spack':{'packages':{'petsc':{'require':['+complex'],'buildable':True}}}}
        updated,changed=with_sdk_requirement(data,'/SDK')
        self.assertTrue(changed)
        requirements=updated['spack']['packages']['petsc']['require']
        self.assertEqual(requirements[0],'+complex')
        self.assertEqual(requirements[1]['spec'],'cxxflags="-isystem /SDK/usr/include/c++/v1" cppflags="-isystem /SDK/usr/include/c++/v1"')
        self.assertEqual(requirements[1]['when'],'%cxx=apple-clang')
        self.assertTrue(updated['spack']['packages']['petsc']['buildable'])
        self.assertFalse(with_sdk_requirement(updated,'/SDK')[1])

    def test_previous_cpp_only_requirement_is_upgraded(self):
        from macos_compiler_setup import PETSC_CPP_REQUIREMENT_MESSAGE
        data={'spack':{'packages':{'petsc':{'require':[{
            'spec':'cppflags="-isystem /SDK/usr/include/c++/v1"',
            'when':'%cxx=apple-clang','message':PETSC_CPP_REQUIREMENT_MESSAGE}]}}}}
        updated,changed=with_sdk_requirement(data,'/SDK')
        self.assertTrue(changed)
        requirements=updated['spack']['packages']['petsc']['require']
        self.assertEqual(len(requirements),1)
        self.assertIn('cxxflags=',requirements[0]['spec'])
        self.assertIn('cppflags=',requirements[0]['spec'])

    def test_petsc_preprocessor_flags_are_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'spack.lock'
            spec={'name':'petsc','parameters':{'cxxflags':['-isystem /SDK/usr/include/c++/v1']},
                  'dependencies':[{'name':'apple-clang','parameters':{'virtuals':['cxx']}}]}
            path.write_text(json.dumps({'concrete_specs':{'petsc':spec}}))
            self.assertEqual(audit_lockfile(path,'/SDK')['status'],'missing_preprocessor_sdk_flags')
            spec['parameters']['cppflags']=['-isystem /SDK/usr/include/c++/v1']
            path.write_text(json.dumps({'concrete_specs':{'petsc':spec}}))
            self.assertEqual(audit_lockfile(path,'/SDK')['status'],'passed')

    def test_system_ssh_registration_preserves_options_and_is_idempotent(self):
        data={'spack':{'specs':['palace@0.16.0~cuda'],'packages':{
            'all':{'require':['target=m1']},'openssh':{'permissions':{'read':'world'}}}}}
        updated,changed=with_system_ssh(data,'10.3p1')
        self.assertTrue(changed)
        self.assertFalse(updated['spack']['packages']['openssh']['buildable'])
        self.assertEqual(updated['spack']['packages']['openssh']['externals'],
                         [{'spec':'openssh@10.3p1','prefix':'/usr'}])
        self.assertEqual(updated['spack']['packages']['all'],data['spack']['packages']['all'])
        self.assertEqual(updated['spack']['packages']['openssh']['permissions'],{'read':'world'})
        self.assertFalse(with_system_ssh(updated,'10.3p1')[1])
        self.assertNotIn('externals',data['spack']['packages']['openssh'])

    def test_audit_requires_system_ssh_external(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'spack.lock'
            specs={'cpp':{'name':'cpp','parameters':{'cxxflags':['-isystem /SDK/usr/include/c++/v1']},
                   'dependencies':[{'name':'apple-clang','parameters':{'virtuals':['cxx']}}]},
                   'ssh':{'name':'openssh','external':None}}
            for external,expected in [(None,'openssh_not_system_external'),
                                      ({'path':'/other'},'openssh_not_system_external'),
                                      ({'path':'/usr'},'passed')]:
                specs['ssh']['external']=external
                path.write_text(json.dumps({'concrete_specs':specs}))
                self.assertEqual(audit_lockfile(path,'/SDK')['status'],expected)

    def test_scoped_requirement_preserves_existing_options_and_is_idempotent(self):
        data={'spack':{'specs':['palace@0.16.0~cuda'],'packages':{'all':{'require':['target=m1']}}}}
        updated,changed=with_sdk_requirement(data,'/SDK')
        self.assertTrue(changed)
        self.assertEqual(updated['spack']['specs'],data['spack']['specs'])
        self.assertEqual(updated['spack']['packages']['all']['require'][0],'target=m1')
        self.assertEqual(updated['spack']['packages']['all']['require'][-1]['when'],'%cxx=apple-clang')
        self.assertFalse(with_sdk_requirement(updated,'/SDK')[1])
        self.assertNotEqual(updated,data)

if __name__=='__main__':unittest.main()
