"""Draw the app's simple record logo without runtime imaging dependencies."""
import math
from pathlib import Path
import struct
import subprocess
import zlib


def png(path, size):
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            # Supersample each pixel for smooth circles and corners.
            values = [0,0,0,0]
            for oy,ox in ((.25,.25),(.25,.75),(.75,.25),(.75,.75)):
                nx,ny=(x+ox)/size,(y+oy)/size
                corner_x=max(.20-nx,0,nx-.80)
                corner_y=max(.20-ny,0,ny-.80)
                inside=corner_x*corner_x+corner_y*corner_y < .17*.17
                radius=math.hypot(nx-.5,ny-.5)
                rgb=(23,26,20)
                if radius < .365:
                    rgb=(38,45,30) if int(radius*220)%3 else (49,58,37)
                if .325 < radius < .344 or .256 < radius < .266:
                    rgb=(212,237,132)
                if radius < .12:
                    rgb=(212,237,132)
                if radius < .035:
                    rgb=(23,26,20)
                if ny>.82 and .38<nx<.62:
                    rgb=(212,237,132)
                for i,v in enumerate((*rgb,255 if inside else 0)):values[i]+=v
            pixels.extend(v//4 for v in values)
    def chunk(kind,data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b''))


def make_icon(destination):
    destination=Path(destination)
    iconset=destination.parent/'DJIntake.iconset'
    iconset.mkdir(parents=True,exist_ok=True)
    artwork=Path(__file__).resolve().parent.parent/'assets/app-icon.png'
    if artwork.exists():
        subprocess.run(['sips','-z','1024','1024',str(artwork),'--out',str(iconset/'icon_512x512@2x.png')],check=True,stdout=subprocess.DEVNULL)
    else:
        png(iconset/'icon_512x512@2x.png',1024)
    for size in (16,32,128,256,512):
        for scale in (1,2):
            target=iconset/(f'icon_{size}x{size}'+('@2x' if scale==2 else '')+'.png')
            if target.name=='icon_512x512@2x.png':continue
            subprocess.run(['sips','-z',str(size*scale),str(size*scale),str(iconset/'icon_512x512@2x.png'),'--out',str(target)],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['iconutil','-c','icns',str(iconset),'-o',str(destination)],check=True)
    return destination

if __name__=='__main__':
    import sys
    make_icon(sys.argv[1])
