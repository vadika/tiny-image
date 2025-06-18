# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository contains tools for creating tiny Linux initrd images for QEMU/kernel testing and debugging. The main tool `make-tiny-image.py` creates minimal initrd images containing busybox and optionally additional binaries and kernel modules.

## Commands

### Creating Basic Initrd
```bash
# Create basic initrd with busybox shell
./make-tiny-image.py

# Create initrd that runs a specific command instead of shell
./make-tiny-image.py --run 'cat /proc/cpuinfo'
./make-tiny-image.py --run poweroff
```

### Adding Binaries and Dependencies
```bash
# Include additional binaries (automatically resolves shared library dependencies)
./make-tiny-image.py hwloc-info lstopo-no-graphics

# Copy extra files from host
./make-tiny-image.py --copy /etc/redhat-release
```

### Kernel Modules
```bash
# Include kernel modules with dependencies
./make-tiny-image.py --kmod lpc_ich --kmod iTCO_wdt --kmod i2c_i801

# Specify kernel version for modules
./make-tiny-image.py --kmod somemodule --kver 6.0.8-300.fc37.x86_64
```

### Testing with QEMU
```bash
# Run the generated initrd
./run-tiny-image.sh

# Or manually with specific options
qemu-system-x86_64 \
    -kernel /boot/vmlinuz-$(uname -r) \
    -initrd tiny-initrd.img \
    -append 'console=ttyS0 quiet' \
    -m 1000 -display none -serial stdio -accel kvm
```

## Architecture

### Core Components

- **make-tiny-image.py**: Main Python script that builds initrd images
  - `make_busybox()`: Sets up busybox environment and creates init script
  - `get_deps()` / `install_deps()`: Resolves and copies shared library dependencies
  - `make_binaries()`: Copies requested binaries into initrd
  - `make_kmods()`: Handles kernel module copying with dependency resolution
  - `make_image()`: Orchestrates the build process and creates cpio archive

- **run-tiny-image.sh**: Convenience wrapper for running QEMU with standard options

### Key Features

- **Automatic dependency resolution**: Uses `ldd` to find and copy required shared libraries
- **Kernel module support**: Recursively resolves kernel module dependencies using `modinfo`
- **Custom init script**: Generates init script that sets up basic /dev nodes, mounts proc/sysfs, loads modules, and runs specified command
- **File copying**: Supports copying arbitrary files from host to initrd with path mapping

### Boot Process

1. Init script creates device nodes (/dev/console, /dev/null, etc.)
2. Mounts /proc and /sys filesystems  
3. Loads specified kernel modules with `insmod`
4. Executes the specified command (default: interactive shell)
5. Powers off system when command exits

## Usage Patterns

This tool is designed for rapid QEMU/kernel testing cycles where full OS boot overhead is unacceptable. Typical use cases include:

- Testing kernel module functionality
- Debugging QEMU device emulation
- Comparing KVM vs TCG behavior
- Running simple commands in minimal Linux environment

The generated initrd boots in under 1 second with KVM acceleration, making it suitable for iterative development workflows.