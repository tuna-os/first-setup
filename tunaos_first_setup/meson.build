pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
moduledir = join_paths(pkgdatadir, 'tunaos_first_setup')
gnome = import('gnome')

gnome.compile_resources('tunaos-first-setup',
  'tunaos-first-setup.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: moduledir,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)
conf.set('moduledir', moduledir)

configure_file(
  input: 'tunaos-first-setup.in',
  output: 'tunaos-first-setup',
  install_mode: 'rwxr-xr-x',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
)

subdir('core')
subdir('scripts')
subdir('views')

tunaos_first_setup_sources = [
  '__init__.py',
  'application.py',
  'main.py',
  'window.py',
  'dialog.py',
  'apps.json',
  'core.json',
]

install_data(tunaos_first_setup_sources, install_dir: moduledir)
