# user_home.py
#
# Copyright 2024 mirkobrombin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundationat version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from gi.repository import Gtk, Adw, Gio

_ = __builtins__["_"]


@Gtk.Template(resource_path="/org/frostyard/FirstSetup/gtk/user-home.ui")
class VanillaUserHome(Adw.Bin):
    __gtype_name__ = "VanillaUserHome"

    view_stack = Gtk.Template.Child()
    view_switcher_title = Gtk.Template.Child()
    view_switcher_bar = Gtk.Template.Child()
    system_page = Gtk.Template.Child()
    updates_page = Gtk.Template.Child()
    applications_page = Gtk.Template.Child()
    maintenance_page = Gtk.Template.Child()
    help_page = Gtk.Template.Child()

    def __init__(self, window, **kwargs):
        super().__init__(**kwargs)
        self.__window = window

        # Bind the view stack to the switchers
        self.view_switcher_title.set_stack(self.view_stack)
        self.view_switcher_bar.set_stack(self.view_stack)

        # Build the preference groups dynamically
        self.__build_system_page()
        self.__build_updates_page()
        self.__build_applications_page()
        self.__build_maintenance_page()
        self.__build_help_page()

    def __build_system_page(self):
        """Build the System tab preference groups"""
        # System Information group
        system_info_group = Adw.PreferencesGroup()
        system_info_group.set_title(_("System Information"))
        system_info_group.set_description(_("View system details and hardware information"))

        # Create an expander row for OS release information
        os_expander = Adw.ExpanderRow()
        os_expander.set_title(_("Operating System Details"))

        # Read /etc/os-release and dynamically add rows to the expander
        try:
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        # Remove quotes from value
                        value = value.strip('"').strip("'")
                        # Convert key to readable format (e.g., PRETTY_NAME -> Pretty Name)
                        readable_key = key.replace('_', ' ').title().replace('Url', 'URL')
                        row = Adw.ActionRow(title=readable_key, subtitle=value)

                        # Make URL rows clickable
                        if key.endswith('URL'):
                            row.set_activatable(True)
                            row.add_suffix(Gtk.Image.new_from_icon_name("adw-external-link-symbolic"))
                            row.connect("activated", self.__on_url_row_activated, value)

                        os_expander.add_row(row)
        except FileNotFoundError:
            # Fallback if /etc/os-release doesn't exist
            row = Adw.ActionRow(title=_("OS Information"), subtitle=_("Not available"))
            os_expander.add_row(row)
        except Exception as e:
            row = Adw.ActionRow(title=_("Error"), subtitle=str(e))
            os_expander.add_row(row)

        system_info_group.add(os_expander)
        self.system_page.add(system_info_group)

        # System Settings group
        system_settings_group = Adw.PreferencesGroup()
        system_settings_group.set_title(_("System Settings"))
        system_settings_group.set_description(_("Configure system-wide preferences"))
        self.system_page.add(system_settings_group)

    def __build_updates_page(self):
        """Build the Updates tab preference groups"""
        # System Updates group
        updates_status_group = Adw.PreferencesGroup()
        updates_status_group.set_title(_("System Updates"))
        updates_status_group.set_description(_("Check for and install system updates"))
        self.updates_page.add(updates_status_group)

        # Update Settings group
        updates_settings_group = Adw.PreferencesGroup()
        updates_settings_group.set_title(_("Update Settings"))
        updates_settings_group.set_description(_("Configure update preferences"))
        self.updates_page.add(updates_settings_group)

    def __build_applications_page(self):
        """Build the Applications tab preference groups"""
        # Installed Applications group
        applications_installed_group = Adw.PreferencesGroup()
        applications_installed_group.set_title(_("Installed Applications"))
        applications_installed_group.set_description(_("Manage your installed applications"))
        self.applications_page.add(applications_installed_group)

        # Application Sources group
        applications_sources_group = Adw.PreferencesGroup()
        applications_sources_group.set_title(_("Preconfigured Bundles"))
        applications_sources_group.set_description(_("Install and manage preconfigured application bundles"))
        self.applications_page.add(applications_sources_group)

    def __build_maintenance_page(self):
        """Build the Maintenance tab preference groups"""
        # System Cleanup group
        maintenance_cleanup_group = Adw.PreferencesGroup()
        maintenance_cleanup_group.set_title(_("System Cleanup"))
        maintenance_cleanup_group.set_description(_("Clean up temporary files and free up disk space"))
        self.maintenance_page.add(maintenance_cleanup_group)

        # System Optimization group
        maintenance_optimization_group = Adw.PreferencesGroup()
        maintenance_optimization_group.set_title(_("System Optimization"))
        maintenance_optimization_group.set_description(_("Optimize system performance"))
        self.maintenance_page.add(maintenance_optimization_group)

    def __build_help_page(self):
        """Build the Help tab preference groups"""
        # Help Resources group
        help_resources_group = Adw.PreferencesGroup()
        help_resources_group.set_title(_("Help Resources"))
        help_resources_group.set_description(_("Access help and support resources"))
        self.help_page.add(help_resources_group)

    def __on_url_row_activated(self, row, url):
        """Open URL in default browser when a URL row is clicked"""
        try:
            Gio.AppInfo.launch_default_for_uri(url, None)
        except Exception as e:
            print(f"Error opening URL: {e}")

    def set_page_active(self):
        self.__window.set_ready(True)

    def set_page_inactive(self):
        return

    def finish(self):
        return True
