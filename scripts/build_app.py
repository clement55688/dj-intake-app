#!/usr/bin/env python3
"""Build the macOS launcher; optionally put a link to it on the Desktop."""
import argparse
import plistlib
from pathlib import Path
import shlex
import shutil
import subprocess
from make_icon import make_icon


def install_desktop(output,desktop):
    """Make the Desktop icon a link to the built app.

    Once it is a link, rebuilding never touches the Desktop, so in-app updates
    don't need macOS permission to change files there.
    """
    if desktop.is_symlink():
        if desktop.resolve()==output.resolve():
            return desktop
        desktop.unlink()
    elif desktop.exists():
        existing=plistlib.loads((desktop/'Contents/Info.plist').read_bytes())
        if existing.get('CFBundleIdentifier')!='local.djintake.launcher':
            raise SystemExit('An unrelated Desktop app has that name; left it unchanged.')
        shutil.rmtree(desktop)
    desktop.symlink_to(output)
    return desktop


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--desktop',action='store_true',help='Link ~/Desktop/DJ Intake.app to the built launcher')
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
    # Build next to the current app and swap at the end, so a failed build keeps the old one.
    building=output.with_name('DJ Intake.building.app')
    if building.exists():
        shutil.rmtree(building)
    (building/'Contents/MacOS').mkdir(parents=True)
    (building/'Contents/Resources').mkdir()
    shutil.copyfile(executable,building/'Contents/MacOS/DJIntake')
    (building/'Contents/MacOS/DJIntake').chmod(0o755)
    icon=make_icon(root/'work/DJIntake.icns')
    shutil.copyfile(icon,building/'Contents/Resources/DJIntake.icns')
    plist=building/'Contents/Info.plist'
    data={'CFBundleExecutable':'DJIntake','CFBundlePackageType':'APPL','CFBundleVersion':'0.4.4','CFBundleShortVersionString':'0.4.4','LSUIElement':True,'LSMinimumSystemVersion':'12.0','NSHighResolutionCapable':True,'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True},'DJIntakeProjectRoot':str(root)}
    data.update(CFBundleIconFile='DJIntake',CFBundleIdentifier='local.djintake.launcher',CFBundleDisplayName='DJ Intake',CFBundleName='DJ Intake')
    plist.write_bytes(plistlib.dumps(data))
    subprocess.run(['codesign','--force','--sign','-',str(building)],check=True)
    if output.exists():
        shutil.rmtree(output)
    building.rename(output)
    if args.desktop:
        print(install_desktop(output,Path.home()/'Desktop/DJ Intake.app'))
    print(output)


if __name__=='__main__':main()
