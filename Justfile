set dotenv-load := true


default:
    @just --list --unsorted

setup:
    @echo "Setting up development environment..."
    distrobox assemble create
    distrobox enter first-setup

enter:
    @distrobox enter first-setup

build:
    @echo "Building the project..."
    meson setup build
    meson compile -C build

build-deb:
    @echo "Building Debian package..."
    dpkg-buildpackage -us -uc -b

clean:
    @echo "Cleaning build artifacts..."
    dpkg-buildpackage -Tclean

changelog:
    @echo "Generating changelog..."
    gbp dch --release --debian-branch main -N 0.2.8 -D stable

run:
    @echo "Running the application..."
    python3 test.py -d -r

run-configure:
    @echo "Running the application in configuration mode..."
    python3 test.py -d -c

run-install:
    @echo "Running in install mode..."
    python3 test.py -d -i

