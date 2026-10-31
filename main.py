import psutil
import argparse
import logging
import subprocess
import sys
import time
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse():
    """
    Sets up the command-line argument parser.
    """
    parser = argparse.ArgumentParser(description="Monitor USB device connections and disconnections.")
    parser.add_argument("-i", "--interval", type=int, default=5, help="Interval in seconds to check for USB device changes.")
    parser.add_argument("-l", "--log_file", type=str, default="usb_monitor.log", help="Path to the log file.")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging.")
    return parser.parse_args()

def get_lsusb_blocks():
    """
    Runs lsusb once and parses its output into one record per device block.

    Each block is keyed by the ID on its device line. Only the hex part of
    each ID is stored, without the name text that follows it on the line.
    Returns an empty list when lsusb is unavailable.
    """
    try:
        lsusb_output = subprocess.check_output(["lsusb", "-v"], universal_newlines=True, timeout=5).splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as e:
        logging.warning(f"lsusb command not found or failed: {e}.  Vendor and product IDs may be unavailable.")
        return []

    blocks = []
    current = None
    for line in lsusb_output:
        if line.startswith("Bus "):
            if current is not None:
                blocks.append(current)
            current = {"text": line}
            # The device line carries the ID as ID <vendor>:<product>.
            if " ID " in line:
                id_part = line.split(" ID ", 1)[1].split()[0]
                if ":" in id_part:
                    vendor, product = id_part.split(":", 1)
                    current["vendor_id"] = vendor
                    current["product_id"] = product
            continue
        if current is None:
            continue
        current["text"] += "\n" + line
        stripped = line.strip()
        if stripped.startswith("idVendor") and "0x" in stripped:
            current["vendor_id"] = stripped.split("0x", 1)[1].split()[0]
        elif stripped.startswith("idProduct") and "0x" in stripped:
            current["product_id"] = stripped.split("0x", 1)[1].split()[0]
        elif stripped.startswith("iSerial"):
            parts = stripped.split()
            if len(parts) >= 3:
                current["serial_number"] = parts[-1]
    if current is not None:
        blocks.append(current)
    return blocks

def get_connected_usb_devices():
    """
    Returns a tuple of a list of connected removable storage volumes and a
    flag telling whether the partition source could be read at all. An
    unreadable source returns an empty list with the flag set to False, so
    the caller can tell it apart from a machine with no removable volumes.
    """
    usb_devices = []
    try:
        partitions = psutil.disk_partitions()
    except Exception as e:
        logging.error(f"Could not read the partition source: {e}")
        return [], False

    # The lsusb listing is fetched once per call, not once per device.
    lsusb_blocks = get_lsusb_blocks() if os.name == 'posix' else []

    for disk in partitions:
        if "removable" not in disk.opts or not disk.fstype:
            continue
        device_info = {
            "device": disk.device,
            "mountpoint": disk.mountpoint,
            "fstype": disk.fstype,
        }
        try:
            if os.name == 'nt':  # Windows
                import wmi
                c = wmi.WMI()
                for usb in c.Win32_DiskDrive():
                    if disk.device in usb.Name:
                        device_info["vendor_id"] = usb.Manufacturer
                        device_info["product_id"] = usb.Model
                        device_info["serial_number"] = usb.SerialNumber
            elif os.name == 'posix':  # Linux, macOS
                device_name = disk.device.replace('/dev/', '')
                for block in lsusb_blocks:
                    if device_name in block.get("text", ""):
                        if "vendor_id" in block:
                            device_info["vendor_id"] = block["vendor_id"]
                        if "product_id" in block:
                            device_info["product_id"] = block["product_id"]
                        if "serial_number" in block:
                            device_info["serial_number"] = block["serial_number"]
                        break
        except ImportError as e:
            logging.warning(f"WMI module not found {e}. Vendor and product IDs will be unavailable.")
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing disk {disk.device}: {e}")
        usb_devices.append(device_info)
    return usb_devices, True

def log_device_event(event_type, device_info):
    """
    Logs a USB device connection or disconnection event.
    """
    log_message = f"USB Device {event_type}: Device: {device_info.get('device', 'N/A')}, Mountpoint: {device_info.get('mountpoint', 'N/A')}, " \
                  f"Filesystem: {device_info.get('fstype', 'N/A')}, Vendor ID: {device_info.get('vendor_id', 'N/A')}, " \
                  f"Product ID: {device_info.get('product_id', 'N/A')}, Serial Number: {device_info.get('serial_number', 'N/A')}"
    logging.info(log_message)

def main():
    """
    Main function to monitor USB device connections and disconnections.
    """
    args = setup_argparse()

    if args.interval <= 0:
        logging.error("Error: Interval must be a positive integer.")
        print("Error: Interval must be a positive integer.")
        return 1

    # Configure logging level based on command-line argument
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Attach the log file the operator named, so events go to that file as
    # well as to the console.
    try:
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setLevel(logging.DEBUG if args.debug else logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger('').addHandler(file_handler)
    except OSError as e:
        logging.error(f"Error: Could not open log file {args.log_file}: {e}")
        print(f"Error: Could not open log file {args.log_file}: {e}")
        return 1

    logging.info("Starting USB device monitoring...")

    # Capture the starting set as a silent baseline. Devices already
    # present are not reported as new connections. Keep the last full
    # record per device so a later disconnect line still carries its
    # vendor, product, serial, and mountpoint.
    baseline_devices, baseline_ok = get_connected_usb_devices()
    if not baseline_ok:
        logging.warning("Warning: the device source is failing; no removable volumes can be read.")
    previous_devices = {dev['device'] for dev in baseline_devices}
    previous_records = {dev['device']: dev for dev in baseline_devices}

    try:
        while True:
            current_devices, source_ok = get_connected_usb_devices()
            if not source_ok:
                logging.warning("Warning: the device source is failing; this cycle read no devices because the source could not be read, not because no devices are present.")
                time.sleep(args.interval)
                continue
            current_device_identifiers = {dev['device'] for dev in current_devices}

            new_devices = current_device_identifiers - previous_devices
            for device in current_devices:
                if device['device'] in new_devices:
                    log_device_event("Connected", device)

            disconnected_devices = previous_devices - current_device_identifiers
            for device_id in disconnected_devices:
                log_device_event("Disconnected", previous_records.get(device_id, {"device": device_id}))

            previous_devices = current_device_identifiers.copy()
            previous_records = {dev['device']: dev for dev in current_devices}

            time.sleep(args.interval)
    except KeyboardInterrupt:
        logging.info("Stopping USB device monitoring...")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return 1
    finally:
        logging.info("USB device monitoring stopped.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

# Example Usage:
# To run the script: python3 main.py
# To run with debug logging: python3 main.py -d
# To specify a log file: python3 main.py -l /path/to/my_usb_log.log
# To change the check interval: python3 main.py -i 10
