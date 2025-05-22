"""
update.py
-----------------
Main driver script used to update code over the CAN bus.

"""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
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


def all_goto_bootloader(bootloaders: List[bootloader.Bootloader], live: Live):
    live.console.log("Putting all boards into bootloader mode")
    # first put everybody into bootloader mode
    bootload_task = progress.add_task("Jump to Bootloader")
    for b_idx, bootload_board in enumerate(bootloaders):
        progress.update(
            task_id=bootload_task,
            total=len(bootloaders),
            completed=b_idx,
            description=f"Putting {bootload_board.board.name} into bootloader mode",
        )
        if not bootload_board.goto_bootloader():
            raise TimeoutError(
                f"Failed to send bootloader command to {bootload_board.board.name}"
            )
    progress.remove_task(bootload_task)
    live.console.log(f"[bold green]All boards pushed into bootloader mode successfully")


def all_goto_app(bootloaders: List[bootloader.Bootloader], live: Live):
    live.console.log("Pushing all boards out of bootloader mode")
    app_task = progress.add_task("Jump to App")
    for b_idx, bootload_board in enumerate(bootloaders):
        progress.update(
            task_id=app_task,
            total=len(bootloaders),
            completed=b_idx,
            description=f"Putting {bootload_board.board.name} into application mode",
        )
        if not bootload_board.goto_app():
            raise TimeoutError(
                "Failed to send application command to {bootload_board.board.name}"
            )
    progress.remove_task(app_task)
    live.console.log(
        f"[bold green]All boards pushed out of bootloader mode successfully"
    )


def update_board(bootload_board: bootloader.Bootloader, live: Live):
    steps_task = progress.add_task(
        f"Updating board [blue bold]{bootload_board.board.name}"
    )
    bootload_board.update(
        ui_callback=lambda description, total, completed: progress.update(
            task_id=steps_task,
            total=total,
            description=description,
            completed=completed,
        )
    )
    live.console.log(f"[green]{bootload_board.board.name} updated successfully")
    progress.remove_task(steps_task)


def update(configs: List[boards.Board], build_dir: str) -> None:
    """Update and handle UI."""
    bootloaders: List[bootloader.Bootloader] = [
        bootloader.Bootloader(
            bus=bus,
            board=board,
            ih=intelhex.IntelHex(os.path.join(build_dir, board.path)),
        )
        for board in configs
    ]

    # push all boards into bootloader
    with Live(Group(status, progress), transient=True) as live:
        # push all boards into bootloader
        all_goto_bootloader(bootloaders, live)
        live.console.log(
            f"Updating firmware for boards: [blue bold]{', '.join(board.name for board in configs)}"
        )
        with ThreadPoolExecutor(max_workers=(len(configs))) as executor:
            executor.map(update_board, [(b, live) for b in bootloaders])
        live.console.log(
            f"[bold green]Firmware update successfully ({len(configs)} board{'s' if len(configs) > 1 else ''} updated)"
        )
        # push all boards out of bootloader
        all_goto_app(bootloaders, live)


def erase_board(bootloader_board: bootloader.Bootloader, live: Live):
    steps_task = progress.add_task(
        f"Erasing board [blue bold]{bootloader_board.board.name}"
    )
    bootloader_board.erase(
        ui_callback=lambda description, total, completed: progress.update(
            task_id=steps_task,
            total=total,
            description=description,
            completed=completed,
        )
    )
    live.console.log(f"[green]{bootloader_board.board.name} erased successfully")
    progress.remove_task(steps_task)


def erase(configs: List[boards.Board]) -> None:
    """Erase and handle UI."""
    # push all boards into bootloader
    bootloaders = [
        bootloader.Bootloader(
            bus=bus,
            board=board,
        )
        for board in configs
    ]
    with Live(Group(status, progress), transient=True) as live:
        all_goto_bootloader(bootloaders, live)
        live.console.log(
            f"Erasing with config: [blue bold]{', '.join(board.name for board in configs)}"
        )
        with ThreadPoolExecutor(max_workers=(len(configs))) as executor:
            executor.map(update_board, [(b, live) for b in bootloaders])
        live.console.log(
            f"[bold green]Erase successful ({len(configs)} board{'s' if len(configs) > 1 else ''} erased)"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bus", type=str, default="pcan", help="python-can bus type")
    parser.add_argument(
        "--channel", type=str, default="PCAN_USBBUS1", help="python-can channel"
    )
    parser.add_argument(
        "--bit_rate", type=int, default=1000000, help="CAN bus bit rate"
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        required=True,
        help="Config to load. Note that you can specify multiple with comma separation.",
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
    c = list(
        {
            board
            for config_name in args.config.split(",")
            for board in boards.CONFIGS[config_name.strip()]
        }
    )
    with can.interface.Bus(
        interface=args.bus, channel=args.channel, bitrate=args.bit_rate
    ) as bus:
        if args.erase:
            erase(configs=c)
        else:
            update(configs=c, build_dir=args.build)
