# install_disk.py
#
# Screen to select the physical disk to install to.

import json
import os
import subprocess

from gi.repository import Gtk, GLib, Adw

_ = __builtins__["_"]

import tunaos_first_setup.core.backend as backend


@Gtk.Template(resource_path="/org/tunaos/FirstSetup/gtk/install-disk.ui")
class VanillaInstallDisk(Adw.Bin):
    __gtype_name__ = "VanillaInstallDisk"

    disks_group = Gtk.Template.Child()
    no_disks_label = Gtk.Template.Child()
    fs_combo = Gtk.Template.Child()
    fde_row = Gtk.Template.Child()
    passphrase_entry = Gtk.Template.Child()
    passphrase_confirm_entry = Gtk.Template.Child()
    tpm_row = Gtk.Template.Child()

    # Variants that cannot use btrfs (EL-based, no btrfs support)
    _NO_BTRFS_VARIANTS = {"albacore", "redfin", "skipjack"}

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window
        self.__selected_device = None
        # Persisted FDE settings
        self.__fde_enabled = False
        self.__fde_passphrase = ""
        self.__fde_passphrase_confirm = ""
        self.__tpm_enabled = False
        # store tuples of (action_row, radio_button)
        self.__rows = []

        # Set filesystem options based on variant
        self.__apply_variant_fs_defaults()

        # wire up FDE switch behavior
        try:
            self.fde_row.connect("notify::active", self.__on_fde_toggled)
        except Exception:
            pass
        # wire up passphrase entry changes
        try:
            self.passphrase_entry.connect("changed", self.__on_passphrase_changed)
            self.passphrase_confirm_entry.connect("changed", self.__on_passphrase_changed)
        except Exception:
            pass
        # wire up TPM switch
        try:
            self.tpm_row.connect("notify::active", self.__on_tpm_toggled)
        except Exception:
            pass

    def __apply_variant_fs_defaults(self):
        """Set filesystem combo based on variant.

        Yellowfin/Bonito: xfs (default), btrfs, ext4
        Albacore/Redfin/Skipjack: xfs (default), ext4 — no btrfs
        """
        variant = backend.get_variant_info()
        variant_id = variant["variant_id"]

        if variant_id in self._NO_BTRFS_VARIANTS:
            # Replace the model with xfs + ext4 only
            try:
                string_list = Gtk.StringList()
                string_list.append("xfs")
                string_list.append("ext4")
                self.fs_combo.set_model(string_list)
                self.fs_combo.set_selected(0)
                self.__fs_map = {0: "xfs", 1: "ext4"}
            except Exception:
                self.__fs_map = None
        else:
            # Default model from UI: xfs, btrfs, btrfs (subvolumes), ext4
            # Select btrfs-subvols (index 2) as default for yellowfin/bonito
            try:
                self.fs_combo.set_selected(2)
            except Exception:
                pass
            self.__fs_map = None

    def set_page_active(self):
        # Refresh available disks each time the page becomes active
        GLib.idle_add(self.refresh_drives)
        # Restore persisted FDE settings to UI
        self.__restore_fde_settings()

    def set_page_inactive(self):
        # Persist current FDE settings before leaving the page
        self.__save_fde_settings()

    def __save_fde_settings(self):
        """Save current FDE UI state to instance variables."""
        try:
            self.__fde_enabled = self.fde_row.get_active()
            self.__fde_passphrase = self.passphrase_entry.get_text()
            self.__fde_passphrase_confirm = self.passphrase_confirm_entry.get_text()
            self.__tpm_enabled = self.tpm_row.get_active()
        except Exception:
            pass

    def __restore_fde_settings(self):
        """Restore persisted FDE settings to UI widgets."""
        try:
            self.fde_row.set_active(self.__fde_enabled)
            self.passphrase_entry.set_text(self.__fde_passphrase)
            self.passphrase_confirm_entry.set_text(self.__fde_passphrase_confirm)
            self.tpm_row.set_active(self.__tpm_enabled)
            # Update visibility based on FDE state
            self.passphrase_entry.set_visible(self.__fde_enabled)
            self.passphrase_confirm_entry.set_visible(self.__fde_enabled)
            self.tpm_row.set_visible(self.__fde_enabled)
            if self.__fde_enabled:
                self.__update_passphrase_validation_ui()
        except Exception:
            pass

    def finish(self):
        # Called when the user presses next. Ensure a device is selected and store it on the window.
        if not self.__selected_device:
            self.__window.set_ready(False)
            return False
        # Store chosen device and filesystem on window for later steps
        self.__window.install_target_device = self.__selected_device
        # Get selected filesystem from AdwComboRow
        fs = None
        try:
            selected_idx = self.fs_combo.get_selected()
            if self.__fs_map:
                fs = self.__fs_map.get(selected_idx)
            else:
                # Default model: 0=xfs, 1=btrfs, 2=btrfs-subvols, 3=ext4
                fs_options = ["xfs", "btrfs", "btrfs-subvols", "ext4"]
                fs = fs_options[selected_idx] if selected_idx < len(fs_options) else "xfs"
        except Exception:
            fs = None
        if not fs:
            fs = "xfs"
        self.__window.install_target_fs = fs

        # Handle Full Disk Encryption selection - save and use persisted values
        self.__save_fde_settings()
        self.__window.install_fde_enabled = self.__fde_enabled
        if self.__fde_enabled:
            self.__window.install_fde_passphrase = self.__fde_passphrase
            self.__window.install_tpm_enabled = self.__tpm_enabled
        else:
            self.__window.install_fde_passphrase = None
            self.__window.install_tpm_enabled = False
        return True

    def _get_live_boot_disk(self):
        """Return the /dev/<disk> path that the live ISO is booted from, or None."""
        try:
            proc = subprocess.run(
                ["findmnt", "-n", "-o", "SOURCE", "/run/initramfs/live"],
                capture_output=True, text=True
            )
            source = proc.stdout.strip()  # e.g. /dev/sda1
            if source and source.startswith("/dev/"):
                proc2 = subprocess.run(
                    ["lsblk", "-no", "PKNAME", source],
                    capture_output=True, text=True
                )
                pkname = proc2.stdout.strip()
                return f"/dev/{pkname}" if pkname else source
        except Exception:
            pass
        return None

    @staticmethod
    def _is_internal(disk: dict) -> bool:
        """Return True if the disk appears to be an internal (non-removable) drive."""
        tran = (disk.get("tran") or "").lower()
        hotplug = disk.get("hotplug", False)
        if tran in ("nvme", "sata", "ata"):
            return True
        if tran == "mmc" and not hotplug:
            return True
        return False

    def refresh_drives(self):
        # Clear previous rows
        for (action_row, _radio) in self.__rows:
            self.disks_group.remove(action_row)
        self.__rows = []
        self.__selected_device = None

        try:
            proc = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,SIZE,MODEL,TYPE,PATH,TRAN,HOTPLUG"],
                capture_output=True, text=True, check=True
            )
            data = json.loads(proc.stdout)
        except Exception:
            self.no_disks_label.set_visible(True)
            self.__window.set_ready(False)
            return

        live_disk = self._get_live_boot_disk()
        dev_mode = os.environ.get("TUNAOS_INSTALLER_DEV", "") == "1"

        disks = []
        for block in data.get("blockdevices", []):
            btype = block.get("type", "")
            if dev_mode:
                if btype not in ("disk", "loop"):
                    continue
            else:
                if btype != "disk":
                    continue
            name = block.get("name", "")
            path = block.get("path") or f"/dev/{name}"
            size = block.get("size") or ""
            model = block.get("model") or ""

            # Skip the disk the live ISO is running from
            if live_disk and path == live_disk:
                continue
            # Skip zero-size devices (empty card readers, etc.)
            if size in ("", "0", "0B"):
                continue

            is_loop = btype == "loop"
            disks.append({
                "path": path,
                "name": name,
                "size": size,
                "model": model,
                "tran": block.get("tran") or "",
                "hotplug": block.get("hotplug", False),
                "internal": self._is_internal(block),
                "is_loop": is_loop,
            })

        # Sort: internal disks first, then external
        disks.sort(key=lambda d: (0 if d["internal"] else 1, d["path"]))

        if not disks:
            self.no_disks_label.set_visible(True)
            self.__window.set_ready(False)
            return

        self.no_disks_label.set_visible(False)

        first_radio = None
        auto_select_radio = None
        auto_select_path = None

        for disk in disks:
            tran = disk["tran"].upper() if disk["tran"] else ""
            label = f"{disk['path']} — {disk['size']}"
            if disk.get("is_loop"):
                label += "  [DEV: loopback]"
            elif tran:
                label += f"  ({tran})"
            subtitle = disk["model"] or ""

            action_row = Adw.ActionRow()
            action_row.set_title(label)
            if subtitle:
                action_row.set_subtitle(subtitle)

            radio = Gtk.CheckButton.new()
            radio.set_valign(Gtk.Align.CENTER)
            radio.set_focusable(False)
            if first_radio is None:
                first_radio = radio
            else:
                radio.set_group(first_radio)
            radio.connect("toggled", self.__on_radio_toggled, disk["path"])

            action_row.add_prefix(radio)
            action_row.set_activatable_widget(radio)

            self.disks_group.add(action_row)
            self.__rows.append((action_row, radio))

            # Pre-select the first internal disk (or first disk if none internal)
            if auto_select_radio is None and (disk["internal"] or len(disks) == 1):
                auto_select_radio = radio
                auto_select_path = disk["path"]

        if auto_select_radio is None and self.__rows:
            auto_select_radio, _ = self.__rows[0]
            auto_select_path = disks[0]["path"]

        # Ensure filesystem combobox has a default
        try:
            if self.fs_combo.get_selected() == Gtk.INVALID_LIST_POSITION:
                self.fs_combo.set_selected(0)
        except Exception:
            pass

        # Auto-select and activate the pre-selected disk
        if auto_select_radio is not None:
            auto_select_radio.set_active(True)
            self.__selected_device = auto_select_path
            for (row, r) in self.__rows:
                if r is auto_select_radio:
                    row.add_css_class("selected")

        self.__update_ready_state()
        return

    def __on_row_activated(self, widget, path):
        # Mark selected device and visually indicate selection
        self.__selected_device = path
        # Update rows to show selection
        # handled via radio toggled handler
        return

    def __on_radio_toggled(self, radio, path):
        if not radio.get_active():
            return
        self.__selected_device = path
        for (row, r) in self.__rows:
            if r is radio:
                row.add_css_class("selected")
            else:
                row.remove_css_class("selected")

        self.__update_ready_state()

    def __validate_passphrase(self):
        """Check if passphrase meets requirements: min 8 chars and both fields match."""
        passphrase = self.passphrase_entry.get_text()
        confirm = self.passphrase_confirm_entry.get_text()
        if len(passphrase) < 8:
            return False
        if passphrase != confirm:
            return False
        return True

    def __update_passphrase_validation_ui(self):
        """Update visual validation state for passphrase fields."""
        passphrase = self.passphrase_entry.get_text()
        confirm = self.passphrase_confirm_entry.get_text()

        # Validate passphrase field: must be at least 8 characters
        if len(passphrase) == 0:
            self.passphrase_entry.add_css_class("error")
        elif len(passphrase) < 8:
            self.passphrase_entry.add_css_class("error")
        else:
            self.passphrase_entry.remove_css_class("error")

        # Validate confirmation field: must match passphrase
        if len(confirm) == 0 or confirm != passphrase:
            self.passphrase_confirm_entry.add_css_class("error")
        else:
            self.passphrase_confirm_entry.remove_css_class("error")

    def __clear_passphrase_validation_ui(self):
        """Clear validation error styling from passphrase fields."""
        try:
            self.passphrase_entry.remove_css_class("error")
            self.passphrase_confirm_entry.remove_css_class("error")
        except Exception:
            pass

    def __update_ready_state(self):
        """Update the window ready state based on disk selection and FDE passphrase validity."""
        if not self.__selected_device:
            self.__window.set_ready(False)
            return
        # If FDE is enabled, passphrase must be valid
        try:
            if self.fde_row.get_active():
                if not self.__validate_passphrase():
                    self.__window.set_ready(False)
                    return
        except Exception:
            pass
        self.__window.set_ready(True)

    def __on_passphrase_changed(self, entry):
        """Called when either passphrase field changes."""
        self.__update_passphrase_validation_ui()
        self.__save_fde_settings()
        self.__update_ready_state()

    def __on_fde_toggled(self, switch, pspec):
        """Enable/disable passphrase fields and TPM row based on FDE selection."""
        fde_active = switch.get_active()
        try:
            # Show/hide encryption-related rows
            self.passphrase_entry.set_visible(fde_active)
            self.passphrase_confirm_entry.set_visible(fde_active)
            self.tpm_row.set_visible(fde_active)
            # If FDE is disabled, reset TPM and clear passphrases
            if not fde_active:
                self.tpm_row.set_active(False)
                self.passphrase_entry.set_text("")
                self.passphrase_confirm_entry.set_text("")
                self.__clear_passphrase_validation_ui()
            else:
                # Show validation state when FDE is enabled
                self.__update_passphrase_validation_ui()
        except Exception:
            pass
        self.__save_fde_settings()
        self.__update_ready_state()

    def __on_tpm_toggled(self, switch, pspec):
        """Called when TPM auto-unlock is toggled."""
        self.__save_fde_settings()
