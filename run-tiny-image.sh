#!/bin/bash
qemu-system-x86_64 \
    -kernel /boot/vmlinuz-$(uname -r) \
    -initrd tiny-initrd.img \
    -append 'console=ttyS0 quiet' \
    -m 1000 -display none -serial stdio  -accel kvm 
