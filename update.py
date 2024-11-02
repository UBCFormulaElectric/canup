"""
update.py
-----------------
Main driver script used to update code over the CAN bus.

"""

import argparse
import os
from typing import List

import can
import intelhex
from rich.console import Console, Group
from rich.live import Live
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn

import boards
import bootloader

console = Console()
status = console.status("Status")
progress = Progress(
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    DownloadColumn(),
)
steps_task = progress.add_task("Steps")


def ui_callback(description, total, completed):
    """Callback passed to bootloader to update UI."""
    progress.update(
        task_id=steps_task, total=total, description=description, completed=completed
    )


def update(configs: List[boards.Board], build_dir: str) -> None:
    """Update and handle UI."""
    with Live(Group(status, progress), transient=True) as live:
        config_name = ", ".join(board.name for board in configs)
        num_boards = len(configs)
        live.console.log(f"Updating firmware for boards: [blue bold]{config_name}")

        for i, board in enumerate(configs):
            progress.update(
                task_id=steps_task,
                total=0,
                description=f"Starting update for {board.name}",
                completed=0,
            )
            status.update(
                f"Updating board [yellow]{i+1}/{num_boards}[/]: [blue bold]{board.name}"
            )

            bin_path = os.path.join(build_dir, board.path)
            ih = intelhex.IntelHex(bin_path)
            boot_interface = bootloader.Bootloader(
                bus=bus,
                board=board,
                ui_callback=ui_callback,
                ih=ih,
            )
            boot_interface.update()

            live.console.log(f"[green]{board.name} updated successfully")

        live.console.log(
            f"[bold green]Firmware update successfully ({num_boards} board{'s' if num_boards > 1 else ''} updated)"
        )


def erase(configs: List[boards.Board]) -> None:
    """Erase and handle UI."""
    with Live(Group(status, progress), transient=True) as live:
        config_name = ", ".join(board.name for board in configs)
        num_boards = len(configs)
        live.console.log(f"Erasing with config: [blue bold]{config_name}")

        for i, board in enumerate(configs):
            status.update(
                f"Erasing board [yellow]{i+1}/{num_boards}[/]: [blue bold]{board.name}"
            )

            boot_interface = bootloader.Bootloader(
                bus=bus, board=board, ui_callback=ui_callback
            )
            boot_interface.erase()

            live.console.log(f"[green]{board.name} erased successfully")

        live.console.log(
            f"[bold green]Erase successful ({num_boards} board{'s' if num_boards > 1 else ''} erased)"
        )


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
    )
    parser.add_argument(
        "--build",
        "-b",
        type=str,
        help="Path to Consolidated-Firmware firmware build directory (build_fw_deploy)",
    )
    parser.add_argument("--erase", action="store_true", help="Erase app code")
    args = parser.parse_args()

    # Load config and binary.
    configs = []
    for config_name in args.config.split(","):
        config_name = config_name.strip()
        config = boards.CONFIGS[config_name]

        for board in config:
            if board not in configs:
                configs.append(board)

    with can.interface.Bus(
        interface=args.bus, channel=args.channel, bitrate=args.bit_rate
    ) as bus:
        bus.shutdown
        if args.erase:
            erase(configs=configs)
        else:
            update(configs=configs, build_dir=args.build)
