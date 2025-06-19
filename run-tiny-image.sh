#!/bin/bash

# Detect architecture
ARCH=$(uname -m)
case "$ARCH" in
    x86_64|i386|i686)
        QEMU_BIN="qemu-system-x86_64"
        QEMU_ARCH_OPTS=""
        CONSOLE="ttyS0"
        ;;
    aarch64|arm64)
        QEMU_BIN="qemu-system-aarch64"
        QEMU_ARCH_OPTS="-M virt -cpu cortex-a57"
        CONSOLE="ttyAMA0"
        ;;
    armv7*|armv6*)
        QEMU_BIN="qemu-system-arm"
        QEMU_ARCH_OPTS="-M virt"
        CONSOLE="ttyAMA0"
        ;;
    *)
        echo "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

# Use custom kernel if available, otherwise fall back to system kernel
if [ -f "tiny-kernel" ]; then
    KERNEL="tiny-kernel"
    echo "Using custom built kernel: $KERNEL"
else
    KERNEL="/boot/vmlinuz-$(uname -r)"
    echo "Using system kernel: $KERNEL"
fi

# Check for KVM support
ACCEL_OPTS=""
if [ -e /dev/kvm ]; then
    ACCEL_OPTS="-accel kvm"
    echo "Using KVM acceleration"
else
    echo "KVM not available, using TCG (slower)"
fi

# Run QEMU
$QEMU_BIN \
    $QEMU_ARCH_OPTS \
    -kernel "$KERNEL" \
    -initrd tiny-initrd.img \
    -append "console=$CONSOLE" \
    -m 1000 -display none -serial stdio $ACCEL_OPTS 
