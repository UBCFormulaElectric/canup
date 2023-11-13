"""
update.py
-----------------
Main driver script used to update code over the CAN bus.

"""
import argparse
import bootloader
import intelhex
import can
import boards
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bus", type=str, default="pcan", help="python-can bus type")
    parser.add_argument(
        "--channel", type=str, default="PCAN_USBBUS1", help="python-can channel"
    )
    parser.add_argument("--bit_rate", type=int, default=500000, help="CAN bus bit rate")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        required=True,
        help="Config to load",
        choices=boards.CONFIGS.keys(),
    )
    parser.add_argument(
        "--build",
        "-b",
        type=str,
        required=True,
        help="Path to Consolidated-Firmware embedded build directory",
    )
    args = parser.parse_args()

    # Load config and binary.
    config = boards.CONFIGS[args.config]
    bin_path = os.path.join(args.build, config.path)
    ih = intelhex.IntelHex(bin_path)

    with can.interface.Bus(
        interface=args.bus, channel=args.channel, bitrate=args.bit_rate
    ) as bus:
        for board in config:
            print(f"Updating: {config.name}")
            boot_interface = bootloader.Bootloader(bus=bus, ih=ih, board=board)
            boot_interface.update()
            print("Updating completed successfully.")
