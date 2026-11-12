"""Fetch a selected public repository and record the exact resolved commit.

Example: python3 checkout_openroad.py --destination ../../repos/OpenROAD --ref master
Use --repository research only after verifying the required features on that branch.
No build, push, or changes to an existing checkout are performed.
"""
import argparse
import json
from pathlib import Path
import subprocess

REPOS={'upstream':'https://github.com/The-OpenROAD-Project/OpenROAD.git',
       'research':'https://github.com/ieee-ceda-datc/OpenROAD-Research.git'}

def git(*args,cwd=None):
    return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repository',choices=REPOS,default='upstream')
    p.add_argument('--ref',required=True,help='full commit preferred; master selects and then records its current commit')
    p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args()
    if a.ref.startswith('-'):p.error('ref must not be an option')
    if a.destination.exists():p.error('destination exists; refusing to alter an existing checkout')
    a.destination.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['git','clone','--no-checkout',REPOS[a.repository],str(a.destination)],check=True)
    subprocess.run(['git','checkout','--detach',a.ref],cwd=a.destination,check=True)
    # Read project instructions before any future code changes.
    instructions=list(a.destination.rglob('AGENTS.md'))
    sha=git('rev-parse','HEAD',cwd=a.destination)
    lock={'repository':REPOS[a.repository],'requested_ref':a.ref,'commit':sha,
          'paper_revision_verified':False,'submodules_initialized':False,
          'instructions':[str(x.relative_to(a.destination)) for x in instructions]}
    lockpath=a.destination.parent/(a.destination.name+'.lock.json')
    lockpath.write_text(json.dumps(lock,indent=2)+'\n')
    print(json.dumps(lock,indent=2))
    print('Before editing, read all applicable AGENTS.md files. Initialize submodules before building.')

if __name__=='__main__':main()
