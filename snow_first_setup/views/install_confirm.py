# install_confirm.py
#
# Confirmation and installer step for install mode.

from gi.repository import Gtk, GLib, Adw

_ = __builtins__["_"]

import snow_first_setup.core.backend as backend


@Gtk.Template(resource_path="/org/frostyard/FirstSetup/gtk/install-confirm.ui")
class VanillaInstallConfirm(Adw.Bin):
    __gtype_name__ = "VanillaInstallConfirm"

    device_label = Gtk.Template.Child()
    fs_label = Gtk.Template.Child()
    fde_label = Gtk.Template.Child()
    image_combo = Gtk.Template.Child()
    root_password_group = Gtk.Template.Child()
    root_password_entry = Gtk.Template.Child()
    root_password_confirm_entry = Gtk.Template.Child()
    confirm_checkbox = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window

        # cached input values (accessed from worker thread in finish)
        self.__image_text = ""
        self.__image_target = None
        self.__confirm_checked = False
        self.__root_password = ""
        self.__root_password_confirm = ""

        # connect signals to update readiness
        try:
            self.confirm_checkbox.connect("toggled", self.__on_input_changed)
            self.cancel_button.connect("clicked", self.__on_cancel_clicked)
            self.root_password_entry.connect("changed", self.__on_input_changed)
            self.root_password_confirm_entry.connect("changed", self.__on_input_changed)
        except Exception:
            pass

        # load images into combo
        self.__load_images()

        # Connect notify::selected after loading images
        try:
            self.image_combo.connect("notify::selected", self.__on_input_changed)
        except Exception:
            pass

    def set_page_active(self):
        # populate labels from window properties
        device = getattr(self.__window, "install_target_device", None)
        fs = getattr(self.__window, "install_target_fs", None)
        fde_enabled = getattr(self.__window, "install_fde_enabled", False)
        # Widgets may not be available in some runtime states; guard against None
        if getattr(self, 'device_label', None) is not None:
            if device:
                self.device_label.set_text(device)
            else:
                self.device_label.set_text(_("<no device selected>"))
        if getattr(self, 'fs_label', None) is not None:
            if fs:
                self.fs_label.set_text(fs)
            else:
                self.fs_label.set_text(_("<none>"))
        if getattr(self, 'fde_label', None) is not None:
            if fde_enabled:
                tpm_enabled = getattr(self.__window, "install_tpm_enabled", False)
                if tpm_enabled:
                    self.fde_label.set_text(_("Enabled (TPM auto-unlock)"))
                else:
                    self.fde_label.set_text(_("Enabled"))
            else:
                self.fde_label.set_text(_("Disabled"))

        # reset checkbox only (keep image selection intact)
        try:
            self.confirm_checkbox.set_active(False)
        except Exception:
            pass
        self.__confirm_checked = False

        # Clear password fields
        try:
            self.root_password_entry.set_text("")
            self.root_password_confirm_entry.set_text("")
            self.__root_password = ""
            self.__root_password_confirm = ""
        except Exception:
            pass

        # Trigger __on_input_changed to populate __image_target from current combo selection
        self.__on_input_changed()

        # require user action to enable Next
        self.__window.set_ready(False)

    def set_page_inactive(self):
        return

    def __on_input_changed(self, *args):
        # cache values from widgets (this handler runs on the main thread)
        try:
            selected_idx = self.image_combo.get_selected()
            if selected_idx != Gtk.INVALID_LIST_POSITION and hasattr(self, "_VanillaInstallConfirm__images_list"):
                display = self.__images_list[selected_idx]
                print(f"[DEBUG] __on_input_changed: display={display}")
                self.__image_text = display.strip()
                # map display name to target reference if available
                if hasattr(self, "_VanillaInstallConfirm__image_map") and self.__image_text in self.__image_map:
                    self.__image_target = self.__image_map[self.__image_text]
                    print(f"[DEBUG] Mapped '{self.__image_text}' -> '{self.__image_target}'")
                else:
                    self.__image_target = self.__image_text
                    print(f"[DEBUG] No map found, using display as target: '{self.__image_target}'")
            else:
                self.__image_text = ""
                self.__image_target = None
                print("[DEBUG] No display text, clearing target")
        except Exception as e:
            print(f"[DEBUG] Exception in __on_input_changed: {e}")
            self.__image_text = ""
            self.__image_target = None
        try:
            self.__confirm_checked = self.confirm_checkbox.get_active()
        except Exception:
            self.__confirm_checked = False

        # Update password fields visibility and cache passwords
        self.__update_password_visibility()
        try:
            self.__root_password = self.root_password_entry.get_text()
            self.__root_password_confirm = self.root_password_confirm_entry.get_text()
        except Exception:
            self.__root_password = ""
            self.__root_password_confirm = ""

        print(f"[DEBUG] Final state: image_target={self.__image_target}, confirm={self.__confirm_checked}")
        self.__validate()

    def __update_password_visibility(self):
        """Show password fields only for cayo or snowdrift images"""
        try:
            # Check if the target image is cayo or snowdrift
            needs_root_password = False
            if self.__image_target:
                # Check both the target string and the display text
                target_lower = self.__image_target.lower()
                text_lower = self.__image_text.lower()
                needs_root_password = 'cayo' in target_lower or 'snowdrift' in target_lower or 'cayo' in text_lower or 'snowdrift' in text_lower

            self.root_password_group.set_visible(needs_root_password)
            print(f"[DEBUG] Root password visibility: {needs_root_password} (target={self.__image_target}, text={self.__image_text})")
        except Exception as e:
            print(f"[DEBUG] Exception in __update_password_visibility: {e}")

    def __validate(self):
        # enable Next only if image target specified and confirmation checked
        ok = False
        try:
            ok = bool(self.__image_target) and self.__confirm_checked and self.__image_target != _("No images found")

            # If root password is visible, validate that passwords match and are not empty
            if ok and self.root_password_group.get_visible():
                passwords_valid = (
                    self.__root_password and
                    self.__root_password_confirm and
                    self.__root_password == self.__root_password_confirm
                )
                ok = ok and passwords_valid
                print(f"[DEBUG] Password validation: passwords_valid={passwords_valid}, pw_len={len(self.__root_password)}, confirm_len={len(self.__root_password_confirm)}, match={self.__root_password == self.__root_password_confirm}")
        except Exception as e:
            print(f"[DEBUG] Exception in __validate: {e}")
            ok = False
        self.__window.set_ready(ok)

    def finish(self):
        # Do not run install here; progress page will handle it.
        # Ensure parameters exist so we can proceed to progress page.
        print(f"[DEBUG] finish() called, checking params...")
        print(f"[DEBUG] self.__image_target = {self.__image_target}")
        print(f"[DEBUG] self.__image_text = {self.__image_text}")
        print(f"[DEBUG] self.__confirm_checked = {self.__confirm_checked}")

        device = getattr(self.__window, "install_target_device", None)
        fs = getattr(self.__window, "install_target_fs", None)
        image = self.__image_target  # Direct access instead of getattr

        print(f"[DEBUG] Retrieved: device={device}, fs={fs}, image={image}")

        if not device or not fs or not image:
            print("[DEBUG] fail validation failed; device=", device, "fs=", fs, "image=", image)
            return False
        # Persist selected image target on the window so the progress page can access it.
        try:
            self.__window.install_target_image = image
            print(f"[DEBUG] Successfully set window.install_target_image = {image}")

            # Store root password if it was collected
            if self.root_password_group.get_visible() and self.__root_password:
                self.__window.install_root_password = self.__root_password
                print(f"[DEBUG] Successfully set window.install_root_password (length={len(self.__root_password)})")
            else:
                self.__window.install_root_password = None
                print(f"[DEBUG] No root password needed or collected")
        except Exception as e:
            print("[exception] Failed to set install parameters:", e)
            pass
        return True

    def __on_cancel_clicked(self, *args):
        app = self.__window.get_application()
        if app:
            app.quit()

    def __load_images(self):
        # File search order
        import os, json
        candidates = [
            "/usr/share/snow/images.json",
            "/etc/snow/images.json",
            os.path.abspath(os.path.join(self.__window.moduledir, "images.json")),
        ]
        print("Loading images from candidates:", candidates)
        images = []  # list of display strings
        image_map = {}  # display -> target reference
        for path in candidates:
            print("Checking path:", path)
            if os.path.exists(path):
                print("Found image list at:", path)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Accept formats: list[str], {images:[str]}, list[dict], {images:[{..}]}
                    # Normalize to list of image description dicts or entries
                    if isinstance(data, dict) and "images" in data:
                        raw_list = data["images"]
                    else:
                        raw_list = data if isinstance(data, list) else []

                    # Handle formats:
                    # 1. List[str]
                    # 2. List[dict] with keys reference/image/ref/name
                    # 3. List[dict] whose entries are nested objects keyed by a short name containing target/display_name
                    def _format_description(desc: str) -> str:
                        if not desc:
                            return ""
                        d = desc.strip()
                        lower = d.lower()
                        # Transform patterns for nicer short form
                        if lower.startswith("bootc enabled"):
                            rest = d[len("Bootc enabled"):].strip()
                            # Ensure capitalisation of first word in rest
                            return f"{rest} + bootc"
                        # Generic 'with' replacement: 'X with Y' -> 'X (+ Y)' left for future; keep original
                        return d

                    for entry in raw_list:
                        if isinstance(entry, str):
                            images.append(entry)
                            image_map[entry] = entry
                        elif isinstance(entry, dict):
                            # Case 3: nested objects keyed by name
                            nested_objects = [v for v in entry.values() if isinstance(v, dict) and ("target" in v or "reference" in v or "image" in v or "ref" in v)]
                            if nested_objects and all(isinstance(v, dict) for v in entry.values()):
                                for key, val in entry.items():
                                    if not isinstance(val, dict):
                                        continue
                                    target = val.get("target") or val.get("reference") or val.get("image") or val.get("ref")
                                    if not target:
                                        continue
                                    base_display = val.get("display_name") or val.get("name") or key
                                    desc_display = _format_description(val.get("description"))
                                    display = base_display if not desc_display else f"{base_display} ({desc_display})"
                                    images.append(display)
                                    image_map[display] = target
                                continue
                            # Case 2: flat dict with reference fields
                            target = None
                            for k in ["reference", "image", "ref", "target"]:
                                if k in entry and isinstance(entry[k], str):
                                    target = entry[k]
                                    break
                            if target:
                                base_display = entry.get("display_name") or entry.get("name") or target
                                desc_display = _format_description(entry.get("description"))
                                display = base_display if not desc_display else f"{base_display} ({desc_display})"
                                images.append(display)
                                image_map[display] = target
                except Exception:
                    continue
                if images:
                    break

        # Store image_map and images list BEFORE populating combo so __on_input_changed can access it
        self.__image_map = image_map
        self.__images_list = images
        print(f"[DEBUG] Image map created with {len(image_map)} entries: {list(image_map.keys())}")

        # Populate combo with StringList model for AdwComboRow
        try:
            string_list = Gtk.StringList()
            for img in images:
                string_list.append(img)
            self.image_combo.set_model(string_list)
            if images:
                self.image_combo.set_selected(0)
                # Manually trigger __on_input_changed to populate __image_target
                self.__on_input_changed()
        except Exception as e:
            print(f"[DEBUG] Exception populating combo: {e}")
            pass

        # If no images found, add a disabled placeholder
        if not images:
            try:
                string_list = Gtk.StringList()
                string_list.append(_("No images found"))
                self.image_combo.set_model(string_list)
                self.image_combo.set_selected(0)
                self.__images_list = [_("No images found")]
            except Exception:
                pass
