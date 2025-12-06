#!/usr/bin/env bash
# Bash script replicating install_create_rootfs functionality
# Assumptions:
# - target_arch: x86_64
# - boot partition: required
# - Block setup can be 'direct' or 'tpm2-luks'

set -euo pipefail

# Constants (from baseline.rs and install.rs)
readonly BOOTPN_SIZE_MB=510
readonly EFIPN_SIZE_MB=512
readonly CFS_EFIPN_SIZE_MB=2048
readonly RUN_BOOTC="/run/bootc"
readonly RW_KARG="rw"

# Discoverable Partition Specification UUIDs
readonly BIOS_BOOT_GUID="21686148-6449-6E6F-744E-656564454649"
readonly ESP_GUID="c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
readonly ROOT_X86_64_GUID="4f68bce3-e8cd-4db1-96e7-fbcaf984b709"

# Global variables
DEVICE=""
WIPE=false
BLOCK_SETUP="direct"  # direct or tpm2-luks
FILESYSTEM="btrfs"     # ext4, xfs, or btrfs
ROOT_SIZE=""
COMPOSEFS_ENABLED=true
LUKS_NAME="root"
PASSPHRASE=""
RECOVERY_KEY=""
IMAGE="ghcr.io/frostyard/snow"
KARGS=()

usage() {
    cat <<EOF
Usage: $0 --device DEVICE [OPTIONS]

Options:
    --device DEVICE         Target block device (required)
    --wipe                  Automatically wipe all existing data
    --block-setup SETUP     Block setup: direct or tpm2-luks (default: direct)
    --filesystem FS         Filesystem type: ext4 or btrfs (default: btrfs)
    --root-size SIZE        Root partition size (e.g., 20G, 50000M)
    --composefs             Enable composefs (larger EFI partition)
    --passphrase PASS       Passphrase for TPM2-LUKS encryption (required for tpm2-luks)
    --karg KARG             Additional kernel argument (can be specified multiple times)
    -h, --help              Show this help message

Example:
    $0 --device /dev/vda --wipe --filesystem btrfs --block-setup tpm2-luks --passphrase "my-secret"
EOF
    exit 0
}

log() {
    logfile="/tmp/install-to-disk-$(basename "$DEVICE")"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" >> "$logfile"
}

error() {
    log "ERROR: $*"
    exit 1
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --device)
                DEVICE="$2"
                shift 2
                ;;
            --wipe)
                WIPE=true
                shift
                ;;
            --block-setup)
                BLOCK_SETUP="$2"
                shift 2
                ;;
            --filesystem)
                FILESYSTEM="$2"
                shift 2
                ;;
            --root-size)
                ROOT_SIZE="$2"
                shift 2
                ;;
            --composefs)
                COMPOSEFS_ENABLED=true
                shift
                ;;
            --passphrase)
                PASSPHRASE="$2"
                shift 2
                ;;
            --karg)
                KARGS+=("$2")
                shift 2
                ;;
            -h|--help)
                usage
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done

    [[ -z "$DEVICE" ]] && error "Device is required (--device)"
    [[ -b "$DEVICE" ]] || error "Device $DEVICE is not a block device"
}

# Check if device is mounted
check_mounted() {
    local dev="$1"
    if findmnt --source "$dev" --mountpoint / >/dev/null 2>&1; then
        error "Device $dev is mounted in pid1 mount namespace"
    fi
    # Check all partitions
    for part in "${dev}"*[0-9]; do
        [[ -b "$part" ]] || continue
        if findmnt --source "$part" >/dev/null 2>&1; then
            error "Partition $part is mounted"
        fi
    done
}

# Wipe filesystem signatures
wipefs_device() {
    local dev="$1"
    log "Wiping device $dev"
    wipefs -a "$dev" || error "Failed to wipe $dev"
}

# Wipe device and partitions
wipe_device() {
    local dev="$1"

    # Wipe all partitions first
    for part in "${dev}"*[0-9]; do
        [[ -b "$part" ]] || continue
        wipefs_device "$part"
    done

    # Wipe the main device
    wipefs_device "$dev"
}

# Wait for udev to settle
udev_settle() {
    sleep 0.2
    udevadm settle || error "Failed to run udevadm settle"
}

# Create filesystem
mkfs_with_uuid() {
    local dev="$1"
    local fs="$2"
    local label="$3"
    local uuid
    local size

    uuid=$(cat /proc/sys/kernel/random/uuid)
    size=$(lsblk -b -d -n -o SIZE "$dev" | numfmt --to=iec-i --suffix=B)

    log "Creating $label filesystem ($fs) on device $dev (size=$size)"

    case "$fs" in
        ext4)
            mkfs.ext4 -U "$uuid" -L "$label" -O verity "$dev" >/dev/null || error "Failed to create ext4"
            ;;
        btrfs)
            mkfs.btrfs -U "$uuid" -L "$label" "$dev" >/dev/null || error "Failed to create btrfs"
            ;;
        *)
            error "Unsupported filesystem: $fs"
            ;;
    esac

    log "Created filesystem with UUID: $uuid"
    echo "$uuid"
}

# Setup TPM2-LUKS encryption
setup_tpm2_luks() {
    local dev="$1"
    local uuid
    local keyfile

    [[ -z "$PASSPHRASE" ]] && error "Passphrase is required for tpm2-luks (use --passphrase)"

    uuid=$(cat /proc/sys/kernel/random/uuid)
    keyfile=$(mktemp)

    trap 'rm -f "$keyfile"' RETURN

    echo -n "$PASSPHRASE" > "$keyfile"

    log "Initializing LUKS for root"
    echo -n "$PASSPHRASE" | cryptsetup luksFormat \
        --uuid "$uuid" \
        --key-file "$keyfile" \
        "$dev" || error "Failed to initialize LUKS"


    # TODO: should we skip this if we're not in secure boot mode?
    # not much point in having a TPM unlock tied to pcr7 if we're not in secure boot mode.
    # we should also check if the TPM is available and functional.
    log "Enrolling root device with TPM"
    # if no pcrs are specified, use the default set by systemd-cryptenroll
    # which is only 7. Then we'll end up with a passphrase unlock,
    # a recovery key, and the TPM unlock. The recovery key will be printed out
    # and should be saved by the user.

    # first the recovery key, then the TPM
    local recovery_output
    recovery_output=$(systemd-cryptenroll \
        --recovery-key \
        --unlock-key-file="$keyfile" \
        "$dev") || error "Failed to enroll recovery key"

    log "Recovery key output: $recovery_output"

    # Extract the recovery key from the output (it's typically after "recovery key is:")
    RECOVERY_KEY=$(echo "$recovery_output" | grep -i "recovery key" | sed -n 's/.*:\s*//p' | tr -d '[:space:]')

    # If the above didn't work, try to extract any line that looks like a recovery key
    if [[ -z "$RECOVERY_KEY" ]]; then
        RECOVERY_KEY=$(echo "$recovery_output" | grep -E '^[a-z0-9]{4,}-[a-z0-9]{4,}' | head -1)
    fi

    systemd-cryptenroll \
        --tpm2-device=auto \
        --unlock-key-file="$keyfile" \
        "$dev" || error "Failed to enroll TPM"

    log "Opening root LUKS device"
    log "Recovery key: $RECOVERY_KEY"
    cryptsetup luksOpen "$dev" "$LUKS_NAME" || error "Failed to open LUKS device"

    echo "/dev/mapper/$LUKS_NAME|$uuid|$RECOVERY_KEY"
}

# Create partition table
create_partitions() {
    local dev="$1"
    local sfdisk_input=""
    local partno=0
    local label_id
    local esp_size

    label_id=$(cat /proc/sys/kernel/random/uuid)

    if [[ "$COMPOSEFS_ENABLED" == true ]]; then
        esp_size=$CFS_EFIPN_SIZE_MB
    else
        esp_size=$EFIPN_SIZE_MB
    fi

    sfdisk_input="label: gpt\n"
    sfdisk_input+="label-id: $label_id\n"

    # BIOS boot partition (x86_64)
    ((partno++))
    sfdisk_input+="size=1MiB, bootable, type=$BIOS_BOOT_GUID, name=\"BIOS-BOOT\"\n"

    # EFI System Partition
    ((partno++))
    sfdisk_input+="size=${esp_size}MiB, type=$ESP_GUID, name=\"EFI-SYSTEM\"\n"

    # Root partition
    ((partno++))
    if [[ -n "$ROOT_SIZE" ]]; then
        sfdisk_input+="size=$ROOT_SIZE, type=$ROOT_X86_64_GUID, name=\"root\"\n"
    else
        sfdisk_input+="type=$ROOT_X86_64_GUID, name=\"root\"\n"
    fi

    log "Initializing partitions"
    echo -e "$sfdisk_input" | sfdisk --wipe=always "$dev" >/dev/null || error "Failed to partition device"

    log "Created partition table"
    echo "$partno"  # Return root partition number
}

# Get partition device path
get_partition() {
    local dev="$1"
    local partno="$2"
    local part

    # Handle different naming schemes
    if [[ "$dev" =~ nvme|loop|mmcblk ]]; then
        part="${dev}p${partno}"
    else
        part="${dev}${partno}"
    fi

    echo "$part"
}

# Main installation function
install_create_rootfs() {
    local esp_partno=2
    local root_partno=
    local rootdev
    local root_uuid
    local root_part
    local esp_part
    local mntdir="$RUN_BOOTC/mounts"
    local physical_root_path="$mntdir/rootfs"
    local bootfs="$mntdir/boot"
    local efifs
    local root_kargs=()

    log "Starting rootfs installation"
    log "Block setup: $BLOCK_SETUP"
    log "Filesystem: $FILESYSTEM"

    # Verify device is not mounted
    check_mounted "$DEVICE"

    # Wipe if requested
    if [[ "$WIPE" == true ]]; then
        wipe_device "$DEVICE"
    else
        # Check for existing partitions
        if lsblk -n -o NAME "$DEVICE" | grep -q "$(basename "$DEVICE")"; then
            if [[ $(lsblk -n -o NAME "$DEVICE" | wc -l) -gt 1 ]]; then
                error "Detected existing partitions on $DEVICE; use wipefs or --wipe"
            fi
        fi
    fi

    # Clean up mount directory
    if [[ -d "$mntdir" ]]; then
        rm -rf "$mntdir"
    fi
    mkdir -p "$physical_root_path"
    mkdir -p "$bootfs"

    # Create partitions
    root_partno=$(create_partitions "$DEVICE")

    # Wait for udev
    udev_settle

    # Get partition paths
    root_part=$(get_partition "$DEVICE" "$root_partno")
    esp_part=$(get_partition "$DEVICE" "$esp_partno")

    log "Root partition: $root_part"
    log "ESP partition: $esp_part"

    # Setup root device (with or without LUKS)
    if [[ "$BLOCK_SETUP" == "tpm2-luks" ]]; then
        local luks_result
        luks_result=$(setup_tpm2_luks "$root_part")
        rootdev="${luks_result%%|*}"
        local luks_rest="${luks_result#*|}"
        local luks_uuid="${luks_rest%%|*}"
        RECOVERY_KEY="${luks_rest#*|}"
        root_kargs+=("luks.uuid=$luks_uuid")
        root_kargs+=("luks.options=discard,tpm2-device=auto,headless=true")
        root_kargs+=("rd.luks.options=discard")
    else
        rootdev="$root_part"
    fi


    # Create root filesystem
    root_uuid=$(mkfs_with_uuid "$rootdev" "$FILESYSTEM" "root")

    # Create EFI System Partition
    log "Creating ESP filesystem"
    mkfs.fat "$esp_part" -n "EFI-SYSTEM" >/dev/null || error "Failed to create ESP"

    # Mount filesystems
    log "Mounting root filesystem"
    mount "$rootdev" "$physical_root_path" || error "Failed to mount root"

    log "Mounting boot filesystem"
    # first create the mount point
    mkdir -p "$physical_root_path/boot" || error "Failed to create boot mount point"


    # Create EFI directory
    efifs="$physical_root_path/boot"
    mkdir -p "$efifs" || error "Failed to create EFI directory"
    mount "$esp_part" "$efifs" || error "Failed to mount esp partition"

    # Build kernel arguments
    local all_kargs=("root=UUID=$root_uuid" "$RW_KARG")
    all_kargs+=("${root_kargs[@]}")
    all_kargs+=("${KARGS[@]}")

    # Output results
    log "Installation complete"
    echo ""
    echo "=== Installation Summary ==="
    echo "Device: $DEVICE"
    echo "Root UUID: $root_uuid"
    echo "Root device: $rootdev"
    echo "Filesystem: $FILESYSTEM"
    echo "Physical root path: $physical_root_path"
    if [[ "$BLOCK_SETUP" == "tpm2-luks" ]]; then
        echo "LUKS device: $LUKS_NAME"
    fi
    if [[ "$BLOCK_SETUP" == "tpm2-luks" ]]; then
        echo "Recovery key: ${RECOVERY_KEY}"
    fi
    echo ""
    echo "Kernel arguments:"
    printf "  %s\n" "${all_kargs[@]}"
    echo ""
    echo "Mount points:"
    echo "  Root: $physical_root_path"
    echo "  EFI:  $efifs"

    # this is where we would proceed with the actual installation
    # Build bootc command with individual --karg arguments
    local bootc_cmd=(
        bootc install to-filesystem
        --composefs-backend
        --bootloader systemd
        --skip-finalize
        --source-imgref "docker://$IMAGE"
    )

    # Add each kernel argument individually
    for karg in "${all_kargs[@]}"; do
        bootc_cmd+=(--karg "$karg")
    done

    bootc_cmd+=("$physical_root_path")

    log "Running bootc install command"
    log "${bootc_cmd[@]}"

    "${bootc_cmd[@]}" || error "Failed to install container"

    # todo: write the recovery key to a file in /tmp so the installer can
    # display it to the user without having to rewrite the installer to handle
    # these scripts having output to the user.
    if [[ "$BLOCK_SETUP" == "tpm2-luks" ]]; then
        local recovery_file="/tmp/recovery-key-$(basename "$DEVICE")"
        echo "$RECOVERY_KEY" > "$recovery_file" || error "Failed to write recovery key to file"
        log "Recovery key written to $recovery_file"


        # replicate a debian secureboot efi setup
        mkdir -p "$physical_root_path/boot/efi/EFI/snow"
        cp /usr/lib/shim/shimx64.efi.signed "$physical_root_path/boot/EFI/snow/shimx64.efi"
        cp /usr/lib/shim/fbx64.efi.signed "$physical_root_path/boot/EFI/snow/fbx64.efi"
        cp /usr/lib/shim/mmx64.efi.signed "$physical_root_path/boot/EFI/snow/mmx64.efi"
        cp /usr/lib/systemd/boot/efi/systemd-bootx64.efi.signed "$physical_root_path/boot/EFI/snow/grubx64.efi"

        # create a new boot entry for shim
        efibootmgr --create --disk "$DEVICE" --part 2 --loader '\EFI\snow\shimx64.efi' --label "Snow Secure Boot"

        sgdiskout=$(sgdisk --print "$DEVICE" || error "Failed to get sgdisk output")
        log "sgdisk output:\n$sgdiskout"
        bootout=$(ls -la "$physical_root_path/boot" || error "Failed to get boot output")
        log "boot output:\n$bootout"
        rootout=$(ls -la "$physical_root_path" || error "Failed to get root  output")
        log "root filesystem output:\n$rootout"

        # finally uncomment the line in loader.conf that sets the timeout
        # so that the boot menu appears, allowing the user to edit the kargs
        # if needed to unlock the disk
        sed -i 's/^#timeout/timeout/' "$physical_root_path/boot/loader/loader.conf" || error "Failed to modify loader.conf"
        umount "$physical_root_path/boot" || error "Failed to unmount esp partition"
    fi

    sgdiskout=$(sgdisk --print "$DEVICE" || error "Failed to get sgdisk output")
    log "sgdisk output:\n$sgdiskout"
    bootout=$(ls -la "$physical_root_path/boot" || error "Failed to get boot efi output")
    log "boot efi output:\n$bootout"

    # clean up and unmount everything
    umount -R "$physical_root_path" || error "Failed to unmount root filesystem"
    rm -rf "$mntdir" || error "Failed to clean up mount directory"
    if [[ "$BLOCK_SETUP" == "tpm2-luks" ]]; then
        cryptsetup luksClose "$LUKS_NAME" || error "Failed to close LUKS device"
    fi
}

# Main entry point
main() {
    parse_args "$@"

    # Check for required commands
    local required_cmds=(sfdisk wipefs mkfs.ext4 mkfs.btrfs mkfs.fat udevadm lsblk findmnt)
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "Required command not found: $cmd"
        fi
    done

    if [[ "$BLOCK_SETUP" == "tpm2-luks" ]]; then
        command -v cryptsetup >/dev/null 2>&1 || error "cryptsetup required for tpm2-luks"
        command -v systemd-cryptenroll >/dev/null 2>&1 || error "systemd-cryptenroll required for tpm2-luks"
    fi

    # Must run as root
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
    fi

    install_create_rootfs
}

main "$@"
