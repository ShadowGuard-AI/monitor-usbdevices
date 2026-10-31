![Banner](banner.png)

# monitor-usbdevices
Detects and logs connections and disconnections of removable storage volumes only, including device name, mountpoint, filesystem, vendor ID, product ID, and serial number. Other USB devices, such as keyboards, mice, and phones without a mounted filesystem, are not monitored. - Focused on System monitoring and alerts

Platform prerequisites: on Windows, the `wmi` Python module is required for vendor, product, and serial details. On Linux, the `lsusb` tool (from the usbutils package) is required for vendor, product, and serial details. The `psutil` package in requirements.txt is required on every platform. Devices present when the monitor starts are taken as a silent baseline and are not reported as new connections.

## Install
`git clone https://github.com/ShadowStrikeHQ/monitor-usbdevices`

## Usage
`python3 main.py [params]`

## Parameters
- `-h`: Show help message and exit
- `-i`, `--interval`: Interval in seconds to check for USB device changes (default: 5). Must be a positive integer; a non positive value exits 1 at startup.
- `-l`, `--log_file`: Path to the log file (default: usb_monitor.log). Events are written to this file and to the console.
- `-d`, `--debug`: Enable debug logging.

## License
Copyright (c) ShadowStrikeHQ
