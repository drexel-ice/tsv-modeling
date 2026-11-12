"""Register shared user-wide tools without overriding the user's Python command."""
import argparse
import os
from pathlib import Path
import shlex
import time

MARKER = '# Managed by TSV EM setup'
START = '# >>> TSV EM tools >>>'
END = '# <<< TSV EM tools <<<'


def registration_plan(prefix, bin_dir, profile, python_executable=None):
    prefix=Path(prefix).resolve();bin_dir=Path(bin_dir).resolve();profile=Path(profile).expanduser()
    exports='\n'.join('export '+name+'='+shlex.quote(str(prefix/folder)) for name,folder in [
        ('SPACK_USER_CONFIG_PATH','spack_config'),('SPACK_USER_CACHE_PATH','spack_cache'),
        ('SPACK_SYSTEM_CONFIG_PATH','spack_system_config')])
    if python_executable is not None:
        exports+='\nexport SPACK_PYTHON='+shlex.quote(str(Path(python_executable).resolve()))
    activate=prefix/'activate.sh'
    activation=MARKER+'\n'+exports+'\n'
    activation+='export PATH='+shlex.quote(str(bin_dir))+':"$PATH"\n'
    activation+='. '+shlex.quote(str(prefix/'spack/share/spack/setup-env.sh'))+'\n'
    commands={
        'palace':prefix/'palace_env/.spack-env/view/bin/palace',
        'gmsh':prefix/'python/bin/gmsh',
        'spack':prefix/'spack/bin/spack',
        'tsv-em-python':prefix/'python/bin/python',
    }
    plan=[(activate,activation)]
    for name,target in commands.items():
        wrapper='#!/bin/sh\n'+MARKER+'\n'
        if name=='spack':wrapper+=exports+'\n'
        wrapper+='exec '+shlex.quote(str(target))+' "$@"\n'
        plan.append((bin_dir/name,wrapper))
    block=START+'\n. '+shlex.quote(str(activate))+'\n'+END
    existing=profile.read_text() if profile.exists() else ''
    if (START in existing)!=(END in existing):
        raise ValueError('Incomplete existing TSV EM profile block; inspect before modifying')
    if START in existing:
        if existing.count(START)!=1 or existing.count(END)!=1 or existing.index(START)>existing.index(END):
            raise ValueError('Ambiguous TSV EM profile block')
        begin=existing.index(START);end=existing.index(END)+len(END)
        updated=existing[:begin]+block+existing[end:]
    else:updated=existing+('' if not existing or existing.endswith('\n') else '\n')+'\n'+block+'\n'
    plan.append((profile,updated))
    return plan,commands


def apply_plan(plan,profile):
    profile=Path(profile).expanduser()
    # Check every collision before changing files.
    for path,content in plan:
        if path==profile:continue
        if path.is_symlink() or (path.exists() and MARKER not in path.read_text()):
            raise ValueError(f'Refusing to overwrite an existing unmanaged tool: {path}')
    for path,content in plan:
        if path.exists() and path.read_text()==content:continue
        path.parent.mkdir(parents=True,exist_ok=True)
        if path==profile and path.exists():
            backup=path.with_name(path.name+'.before-tsv-em-'+str(time.time_ns()))
            backup.write_bytes(path.read_bytes())
            backup.chmod(path.stat().st_mode & 0o777)
        path.write_text(content)
        if path!=profile:path.chmod(0o755)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prefix',type=Path,required=True)
    parser.add_argument('--bin-dir',type=Path,default=Path.home()/'.local/bin')
    parser.add_argument('--profile',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--python',dest='python_executable',type=Path,help='pin the Spack interpreter in shared shell registration')
    args=parser.parse_args()
    if args.profile is None:
        shell=Path(os.environ.get('SHELL','/bin/zsh')).name
        if shell not in ('zsh','bash'):raise ValueError('Use --profile for shells other than zsh/bash')
        args.profile=Path.home()/('.zshrc' if shell=='zsh' else '.bash_profile')
    plan,commands=registration_plan(args.prefix,args.bin_dir,args.profile,args.python_executable)
    if not args.dry_run:
        for name,target in commands.items():
            if not target.is_file() or not os.access(target,os.X_OK):
                raise ValueError(f'Install and verify {name} first: {target}')
        apply_plan(plan,args.profile)
    print(('Planned' if args.dry_run else 'Registered')+' shared commands: '+', '.join(commands))
    print('Activate in the current shell: . '+shlex.quote(str(args.prefix.resolve()/'activate.sh')))


if __name__=='__main__':main()
