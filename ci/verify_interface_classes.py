#!/usr/bin/env python3
"""Reject any changes to Java interface class files during method splitting."""
import struct
import sys
import zipfile
from classdump import read_pool

def verify(original, transformed):
    count=0
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(transformed) as after:
        names=set(after.namelist())
        for name in before.namelist():
            if not name.endswith(".class"): continue
            data=before.read(name)
            _,offset=read_pool(data)
            access=struct.unpack_from(">H",data,offset)[0]
            if access & 0x0200:
                count+=1
                if name not in names or after.read(name)!=data:
                    raise ValueError("Interface changed during splitting: "+name)
    if not count: raise ValueError("No interfaces found in source jar")
    return count

if __name__ == "__main__":
    print("INTERFACE_PRESERVATION_PASS count=",verify(sys.argv[1],sys.argv[2]))
