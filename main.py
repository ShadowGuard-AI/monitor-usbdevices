import psutil
import argparse
import logging
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

def get_connected_usb_devices():
    """
    Returns a list of connected USB devices with their details.
    """
    usb_devices = []
    try:
        for disk in psutil.disk_partitions():
            if "removable" in disk.opts and disk.fstype:  # Check for removable disks and filesystem type
                try:
                    # Accessing disk usage can sometimes cause OSError (e.g., permission denied)
                    disk_usage = psutil.disk_usage(disk.mountpoint)
                    device_info = {
                        "device": disk.device,
                        "mountpoint": disk.mountpoint,
                        "fstype": disk.fstype,
                        "total": disk_usage.total,
                        "used": disk_usage.used,
                        "free": disk_usage.free
                    }
                    usb_devices.append(device_info)

                    # Attempt to get vendor and product IDs (OS-specific)
                    try:
                        if os.name == 'nt': # Windows
                            import wmi
                            c = wmi.WMI()
                            for usb in c.Win32_DiskDrive():
                                if disk.device in usb.Name:
                                    device_info["vendor_id"] = usb.Manufacturer
                                    device_info["product_id"] = usb.Model
                                    device_info["serial_number"] = usb.SerialNumber
                        elif os.name == 'posix': #Linux, macOS
                            import subprocess
                            try:
                                # lsusb requires sudo access to list vendor and product IDs without root
                                lsusb_output = subprocess.check_output(["lsusb", "-v"], universal_newlines=True, timeout=5).splitlines()
                                for line in lsusb_output:
                                    if disk.device.replace('/dev/', '') in line:  # Simple match, adjust as needed
                                        for detail_line in lsusb_output[lsusb_output.index(line):]:
                                            if "idVendor" in detail_line:
                                                device_info["vendor_id"] = detail_line.split("0x")[1].strip()
                                            if "idProduct" in detail_line:
                                                device_info["product_id"] = detail_line.split("0x")[1].strip()
                                            if "iSerial" in detail_line:
                                                device_info["serial_number"] = detail_line.split(' ')[-1]
                                                break

                            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                                logging.warning(f"lsusb command not found or failed: {e}.  Vendor and product IDs may be unavailable.")
                    except ImportError as e:
                        logging.warning(f"WMI or subprocess modules not found {e}. Vendor and product IDs will be unavailable.")

                except OSError as e:
                    logging.warning(f"Error accessing disk usage for {disk.device}: {e}")
                except Exception as e:
                    logging.error(f"An unexpected error occurred while processing disk {disk.device}: {e}")
    except Exception as e:
        logging.error(f"Error getting disk partitions: {e}")
    return usb_devices

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

    # Configure logging level based on command-line argument
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logging.info("Starting USB device monitoring...")

    # Initialize an empty set to store previously connected devices
    previous_devices = set()

    try:
        while True:
            # Get currently connected USB devices
            current_devices = get_connected_usb_devices()
            current_device_identifiers = {dev['device'] for dev in current_devices}  # use device as unique identifier

            # Check for newly connected devices
            new_devices = current_device_identifiers - previous_devices
            for device in current_devices:
                if device['device'] in new_devices:
                    log_device_event("Connected", device)
            
            # Check for disconnected devices
            disconnected_devices = previous_devices - current_device_identifiers
            for device_id in disconnected_devices:
                # Since we don't have full device info for disconnected device, create a minimal info dict
                # so that log doesn't throw exception
                log_device_event("Disconnected", {"device": device_id})
            
            # Update the set of previously connected devices
            previous_devices = current_device_identifiers.copy()

            # Sleep for the specified interval
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logging.info("Stopping USB device monitoring...")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        logging.info("USB device monitoring stopped.")

if __name__ == "__main__":
    main()

# Example Usage:
# To run the script: python usb_monitor.py
# To run with debug logging: python usb_monitor.py -d
# To specify a log file: python usb_monitor.py -l /path/to/my_usb_log.log
# To change the check interval: python usb_monitor.py -i 10