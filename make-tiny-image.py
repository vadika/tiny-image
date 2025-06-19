#!/usr/bin/env python3
#
# Copyright (C) 2020 Red Hat, Inc.
#
# SPDX-License-Identifier: GPL-2.0-or-later

import re
import sys
import glob
import argparse
import os
import os.path
import stat
import subprocess
from tempfile import TemporaryDirectory
from shutil import copy
import urllib.request
import tarfile
import json

def which(exe):
    path = os.environ['PATH']

    if exe[0] == '.':
        exe = os.path.abspath(exe)
    if exe[0] == '/':
        return exe

    for p in path.split(os.pathsep):
        f = os.path.join(p, exe)
        if os.path.isfile(f):
            return f
    else:
        raise Exception("Cannot find '%s' in '%s'" % (exe, path))

def make_busybox(tmpdir, runcmd, loadmods, skip_busybox=False):
    bin = os.path.join(tmpdir, "bin")
    os.makedirs(bin, exist_ok=True)

    if not skip_busybox:
        try:
            busyboxbin = which("busybox")
        except Exception as e:
            print("WARNING: busybox not found. Creating minimal init without busybox.")
            print("To install busybox: apt-get install busybox-static (or busybox)")
            skip_busybox = True
    
    if not skip_busybox:
        subprocess.check_call([busyboxbin, "--install", "-s", bin])
        shlink = os.path.join(tmpdir, "bin", "sh")
        busyboxin = os.readlink(shlink)
        busyboxout = os.path.join(tmpdir, busyboxin[1:])

        install_deps(tmpdir, [busyboxbin])

        bbbin = os.path.dirname(busyboxout)
        os.makedirs(bbbin, exist_ok=True)
        if os.path.exists(busyboxout):
            os.unlink(busyboxout)
        copy(busyboxin, busyboxout)

    init = os.path.join(tmpdir, "init")
    with open(init, "w") as fh:
        print("""#!/bin/sh

mkdir /proc /sys
mount -t proc none /proc
mount -t sysfs none /sys

mount -n -t tmpfs none /dev
mknod -m 622 /dev/console c 5 1
mknod -m 666 /dev/null c 1 3
mknod -m 666 /dev/zero c 1 5
mknod -m 666 /dev/ptmx c 5 2
mknod -m 666 /dev/tty c 5 0
mknod -m 666 /dev/ttyS0 c 4 64
mknod -m 666 /dev/ttyAMA0 c 204 64
mknod -m 444 /dev/random c 1 8
mknod -m 444 /dev/urandom c 1 9
""", file=fh)

        for mod in loadmods:
            print("insmod %s" % mod, file=fh)

        print("""%s
poweroff -f
""" % runcmd, file=fh)
    os.chmod(init, stat.S_IRWXU)

def get_deps(binary):
    try:
        os.environ["LC_ALL"] = "C"
        out = subprocess.check_output(["ldd", binary], stderr=subprocess.STDOUT).decode("utf8")
        deps = []
        for line in out.split("\n"):
            m = re.search("=> (/[^ ]+)", line)
            if m is not None:
                deps.append(m.group(1))
            else:
                m = re.match(r"\s*(/[^ ]+)\s+\(.*\)\s*$", line)
                if m is not None:
                    deps.append(m.group(1))
        return deps
    except subprocess.CalledProcessError as ex:
        out = ex.output.decode("utf8")
        if "not a dynamic executable" in out:
            return []
        raise



def install_deps(tmpdir, binaries):
    seen = {}
    libs = []

    for binary in binaries:
        src = which(binary)
        libs.extend(get_deps(src))

    while len(libs):
        todo = libs
        libs = []
        for lib in todo:
            if lib in seen:
                continue

            dir = os.path.dirname(lib)
            libdir = os.path.join(tmpdir, dir[1:])
            os.makedirs(libdir, exist_ok=True)
            dst = os.path.join(tmpdir, lib[1:])
            copy(lib, dst)
            print("Copy lib %s -> %s"% (lib, dst))
            seen[lib] = True
            libs.extend(get_deps(lib))

def make_binaries(tmpdir, binaries):
    bindir = os.path.join(tmpdir, "bin")

    for binary in binaries:
        src = which(binary)
        dst = os.path.join(tmpdir, "bin", os.path.basename(src))
        if os.path.exists(dst):
            os.unlink(dst)
        dstdir = os.path.dirname(dst)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)

        print("Copy bin %s -> %s" % (src, dst))
        copy(src, dst)

    install_deps(tmpdir, binaries)


def kmod_deps(modfile):
    out = subprocess.check_output(["modinfo", modfile], stderr=subprocess.STDOUT).decode("utf8")
    for line in out.split("\n"):
        if line.startswith("depends: "):
            deps = line[8:].strip()
            if deps == "":
                return []
            return [a.replace("-", "_") for a in deps.split(",")]


def copy_kmod(tmpdir, kmoddir, allmods, mod):
    src = os.path.join(kmoddir, allmods[mod])
    dstdir = os.path.join(tmpdir, "lib", "modules")
    if not os.path.exists(dstdir):
        os.makedirs(dstdir)
    dst = os.path.join(dstdir, os.path.basename(allmods[mod]))
    if os.path.exists(dst):
        return
    print("Copy kmod %s -> %s" % (src, dst))
    copy(src, dst)

    loadmods = []
    for depmod in kmod_deps(src):
        loadmods.extend(copy_kmod(tmpdir, kmoddir, allmods, depmod))

    loadmods.append(os.path.join("/lib", "modules",
                                 os.path.basename(allmods[mod])))
    return loadmods


def make_kmods(tmpdir, kmods, kver):
    print(kver)
    kmoddir = os.path.join("/lib", "modules", kver, "kernel")
    if not os.path.exists(kmoddir):
        if len(kmods) > 0:
            print("Warning: kmod dir '%s' does not exist, skipping kernel modules" % kmoddir)
        return []

    allmods = {}
    for path in glob.glob(kmoddir + "/**/*.ko*", recursive=True):
        mod = os.path.basename(path).split(".")[0]
        mod = mod.replace("-", "_")
        allmods[mod] = path

    loadmods = []
    for mod in kmods:
        if mod not in allmods:
            print("Warning: kmod '%s' does not exist, skipping" % mod)
            continue
        loadmods.extend(copy_kmod(tmpdir, kmoddir, allmods, mod))
    return loadmods

def build_kernel(tmpdir, kernel_version=None, config_file=None):
    """Build a minimal kernel from source"""
    import platform
    
    if kernel_version is None:
        # Get latest stable kernel version
        print("Fetching latest stable kernel version...")
        with urllib.request.urlopen("https://www.kernel.org/releases.json") as response:
            releases = json.load(response)
            kernel_version = releases['latest_stable']['version']
    
    print(f"Building kernel {kernel_version}")
    
    # Download kernel source
    major_version = kernel_version.split('.')[0]
    kernel_url = f"https://cdn.kernel.org/pub/linux/kernel/v{major_version}.x/linux-{kernel_version}.tar.xz"
    kernel_tar = os.path.join(tmpdir, f"linux-{kernel_version}.tar.xz")
    
    print(f"Downloading kernel from {kernel_url}")
    urllib.request.urlretrieve(kernel_url, kernel_tar)
    
    # Extract kernel source
    print("Extracting kernel source...")
    with tarfile.open(kernel_tar, 'r:xz') as tar:
        tar.extractall(tmpdir)
    
    kernel_dir = os.path.join(tmpdir, f"linux-{kernel_version}")
    
    # Detect architecture
    machine = platform.machine()
    if machine in ['x86_64', 'i386', 'i686']:
        arch = 'x86'
        kernel_target = 'bzImage'
        kernel_path = "arch/x86/boot/bzImage"
    elif machine.startswith('arm'):
        arch = 'arm'
        kernel_target = 'zImage'
        kernel_path = "arch/arm/boot/zImage"
    elif machine == 'aarch64':
        arch = 'arm64'
        kernel_target = 'Image'
        kernel_path = "arch/arm64/boot/Image"
    else:
        # Default fallback
        arch = machine
        kernel_target = 'vmlinux'
        kernel_path = "vmlinux"
    
    print(f"Detected architecture: {machine} -> {arch}")
    
    # Configure kernel
    if config_file and os.path.exists(config_file):
        print(f"Using config file: {config_file}")
        copy(config_file, os.path.join(kernel_dir, ".config"))
        subprocess.run(["make", "ARCH=" + arch, "olddefconfig"], cwd=kernel_dir, check=True)
    else:
        # Use architecture-specific minimal config if available
        script_dir = os.path.dirname(__file__)
        if arch == 'x86':
            minimal_config = os.path.join(script_dir, "minimal.config")
        elif arch == 'arm64':
            minimal_config = os.path.join(script_dir, "minimal-arm64.config")
        else:
            minimal_config = None
            
        if minimal_config and os.path.exists(minimal_config):
            print(f"Using minimal config: {minimal_config}")
            copy(minimal_config, os.path.join(kernel_dir, ".config"))
            subprocess.run(["make", "ARCH=" + arch, "olddefconfig"], cwd=kernel_dir, check=True)
        else:
            print("Using tinyconfig")
            subprocess.run(["make", "ARCH=" + arch, "tinyconfig"], cwd=kernel_dir, check=True)
    
    # Build kernel
    print(f"Building kernel target: {kernel_target} (this may take a while)...")
    num_jobs = os.cpu_count() or 1
    subprocess.run(["make", f"-j{num_jobs}", "ARCH=" + arch, kernel_target], cwd=kernel_dir, check=True)
    
    # Copy built kernel
    kernel_image = os.path.join(kernel_dir, kernel_path)
    if os.path.exists(kernel_image):
        output_kernel = os.path.join(os.getcwd(), "tiny-kernel")
        copy(kernel_image, output_kernel)
        print(f"Kernel built successfully: {output_kernel}")
        return output_kernel
    else:
        raise Exception(f"Kernel build failed: {kernel_path} not found")

def make_image(tmpdir, output, copyfiles, kmods, kver, binaries, runcmd, build_kernel_opt=None, kernel_config=None):
    # Build kernel if requested
    if build_kernel_opt:
        kernel_version = None if build_kernel_opt == True else build_kernel_opt
        build_kernel(tmpdir, kernel_version, kernel_config)
    
    loadmods = make_kmods(tmpdir, kmods, kver)
    make_busybox(tmpdir, runcmd, loadmods)
    if len(loadmods) > 0 and "insmod" not in binaries:
        binaries.append("insmod")
    make_binaries(tmpdir, binaries)

    for copyfileglob in copyfiles:
        for copyfile in glob.glob(copyfileglob, recursive=True):
            bits = copyfile.split("=")
            src = bits[0]
            if len(bits) == 1:
                dst = os.path.join(tmpdir, bits[0][1:])
            else:
                dst = os.path.join(tmpdir, bits[1][1:])
            dstdir = os.path.dirname(dst)
            os.makedirs(dstdir, exist_ok=True)
            print("Copy extra %s -> %s" % (src, dst))
            copy(src, dst)

    files = glob.iglob(tmpdir + "/**", recursive=True)
    prefix=len(tmpdir) + 1
    files = [f[prefix:] for f in files]
    files = files[1:]
    filelist = "\n".join(files).encode("utf8")

    with open(output, "w") as fh:
        subprocess.run(["cpio", "--quiet", "-o", "-H", "newc"],
                       cwd=tmpdir, input=filelist, stdout=fh)

parser = argparse.ArgumentParser(description='Build a tiny initrd image')
parser.add_argument('--output', default="tiny-initrd.img",
                    help='Filename of output file')
parser.add_argument('--run', default="setsid cttyhack /bin/sh",
                    help='Command to execute in guest (default: "setsid cttyhack /bin/sh")')
parser.add_argument('--copy', action="append", default=[],
                    help='Extra files to copy  /src=/dst')
parser.add_argument('--kmod', action="append", default=[],
                    help='Kernel modules to load')
parser.add_argument('--kver', default=os.uname().release,
                    help='Kernel version to add modules for')
parser.add_argument('--build-kernel', nargs='?', const=True, metavar='VERSION',
                    help='Build a minimal kernel (optionally specify version)')
parser.add_argument('--kernel-config', 
                    help='Path to kernel config file (defaults to minimal.config)')
parser.add_argument('binary', nargs="*",
                    help='List of binaries to include')

args = parser.parse_args()

print (args.output)

with TemporaryDirectory(prefix="make-tiny-image") as tmpdir:
    make_image(tmpdir, args.output, args.copy,
               args.kmod, args.kver, args.binary, args.run,
               args.build_kernel, args.kernel_config)
