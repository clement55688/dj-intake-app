#!/usr/bin/env python3
"""Build the macOS launcher; optionally install a copy on the Desktop."""
import argparse
import plistlib
from pathlib import Path
import shlex
import shutil
import subprocess
from make_icon import make_icon


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--desktop',action='store_true',help='Copy the launcher to ~/Desktop/DJ Intake.app')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    output=root/'outputs/DJ Intake.app'
    output.parent.mkdir(exist_ok=True)
    python=root/'.venv/bin/python'
    if not python.exists():
        raise SystemExit('Run scripts/setup.command first.')
    log=Path.home()/'Library/Logs/dj-intake-app.log'
    log.parent.mkdir(parents=True,exist_ok=True)
    executable=root/'work/DJIntake'
    executable.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['swiftc','-O','-framework','AppKit','-framework','WebKit',str(root/'native/MenuBarApp.swift'),'-o',str(executable)],check=True)
    if output.exists():
        shutil.rmtree(output)
    (output/'Contents/MacOS').mkdir(parents=True)
    (output/'Contents/Resources').mkdir()
    shutil.copyfile(executable,output/'Contents/MacOS/DJIntake')
    (output/'Contents/MacOS/DJIntake').chmod(0o755)
    icon=make_icon(root/'work/DJIntake.icns')
    shutil.copyfile(icon,output/'Contents/Resources/DJIntake.icns')
    plist=output/'Contents/Info.plist'
    data={'CFBundleExecutable':'DJIntake','CFBundlePackageType':'APPL','CFBundleVersion':'0.4.0','CFBundleShortVersionString':'0.4.0','LSUIElement':True,'LSMinimumSystemVersion':'12.0','NSHighResolutionCapable':True,'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},'DJIntakeProjectRoot':str(root)}
    data.update(CFBundleIconFile='DJIntake',CFBundleIdentifier='local.djintake.launcher',CFBundleDisplayName='DJ Intake',CFBundleName='DJ Intake')
    plist.write_bytes(plistlib.dumps(data))
    subprocess.run(['codesign','--force','--sign','-',str(output)],check=True)
    if args.desktop:
        desktop=Path.home()/'Desktop/DJ Intake.app'
        if desktop.exists():
            existing=plistlib.loads((desktop/'Contents/Info.plist').read_bytes())
            if existing.get('CFBundleIdentifier') != 'local.djintake.launcher':
                raise SystemExit('An unrelated Desktop app has that name; left it unchanged.')
        if desktop.exists():
            shutil.rmtree(desktop)
        shutil.copytree(output,desktop)
        subprocess.run(['touch',str(desktop)],check=True)
        print(desktop)
    print(output)


if __name__=='__main__':main()
