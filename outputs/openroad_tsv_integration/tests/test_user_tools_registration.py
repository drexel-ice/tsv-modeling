"""Check registration preservation and conflicts without touching home files."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'em'))
from register_user_tools import apply_plan,registration_plan,MARKER,START

class UserToolsRegistrationTests(unittest.TestCase):
    def test_registration_preserves_profile_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile=root/'zshrc';profile.write_text('export CUSTOM_SETTING=kept\n')
            args=(root/'shared tools',root/'bin',profile)
            plan,_=registration_plan(*args,python_executable='/opt/homebrew/bin/python3.11');apply_plan(plan,profile)
            first=profile.read_text()
            plan,_=registration_plan(*args,python_executable='/opt/homebrew/bin/python3.11');apply_plan(plan,profile)
            self.assertEqual(first,profile.read_text())
            self.assertEqual(first.count(START),1)
            self.assertIn('export CUSTOM_SETTING=kept',first)
            self.assertEqual(len(list(root.glob('zshrc.before-tsv-em-*'))),1)
            self.assertIn(MARKER,(root/'bin/palace').read_text())
            activation=(root/'shared tools/activate.sh').read_text()
            self.assertNotIn('python/bin',activation)
            self.assertIn('export SPACK_PYTHON=',activation)
            self.assertIn('export SPACK_PYTHON=',(root/'bin/spack').read_text())

    def test_unmanaged_command_conflict_changes_no_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile=root/'zshrc';profile.write_text('keep\n')
            bin_dir=root/'bin';bin_dir.mkdir();(bin_dir/'gmsh').write_text('existing tool')
            plan,_=registration_plan(root/'tools',bin_dir,profile)
            with self.assertRaisesRegex(ValueError,'unmanaged'):apply_plan(plan,profile)
            self.assertEqual(profile.read_text(),'keep\n')
            self.assertFalse((root/'tools/activate.sh').exists())

    def test_incomplete_profile_block_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);profile=root/'zshrc';profile.write_text(START+'\n')
            with self.assertRaisesRegex(ValueError,'Incomplete'):
                registration_plan(root/'tools',root/'bin',profile)

if __name__=='__main__':unittest.main()
