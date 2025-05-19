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


def goto_bootloader(board_config: boards.Board):
    """
    Pushes all boards to bootloader mode.
    :throws: TimeoutError if the boards do not respond
    :return: None
    """
    bus.send(
        can.Message(
            arbitration_id=board_config.bootloader_id_range_start | 0x1,
            data=[],
            is_extended_id=True,
        ),
        timeout=10,
    )
    while True:
        msg = bus.recv()
        if msg.arbitration_id == board_config.bootloader_id_range_start | 0x0:
            return


def goto_app(board_config: boards.Board):
    bus.send(
        can.Message(
            arbitration_id=board_config.bootloader_id_range_start | 0x3,
            data=[],
            is_extended_id=True,
        ),
        timeout=10,
    )
    while True:
        msg = bus.recv()
        if msg.arbitration_id == board_config.app_id_range_start + 0x0:
            return


def update(configs: List[boards.Board], build_dir: str) -> None:
    """Update and handle UI."""
    num_boards = len(configs)

    # push all boards into bootloader
    with Live(Group(status, progress), transient=True) as live:
        live.console.log("Putting all boards into bootloader mode")
        # first put everybody into bootloader mode
        for board in configs:
            try:
                goto_bootloader(board)
            except TimeoutError:
                live.console.log(
                    f"[red]Failed to put {board.name} into bootloader mode"
                )
                raise

        live.console.log(
            f"Updating firmware for boards: [blue bold]{', '.join(board.name for board in configs)}"
        )
        for b_idx, board in enumerate(configs):
            # TODO do this in parallel
            progress.update(
                task_id=steps_task,
                total=0,
                completed=0,
                description=f"Starting update for {board.name}",
            )
            status.update(
                f"Updating board [yellow]{b_idx + 1}/{num_boards}[/]: [blue bold]{board.name}"
            )
            bootloader.Bootloader(
                bus=bus,
                board=board,
                ui_callback=ui_callback,
                ih=intelhex.IntelHex(os.path.join(build_dir, board.path)),
            ).update()
            live.console.log(f"[green]{board.name} updated successfully")

        live.console.log(
            f"[bold green]Firmware update successfully ({num_boards} board{'s' if num_boards > 1 else ''} updated)"
        )

        # push all boards out of bootlader
        live.console.log("Pushing all boards out of bootloader mode")
        for board in configs:
            try:
                goto_app(board)
            except TimeoutError:
                live.console.log(
                    f"[red]Failed to put {board.name} into application mode"
                )
                raise
        live.console.log(
            f"[bold green]All boards pushed out of bootloader mode successfully"
        )


def erase(configs: List[boards.Board]) -> None:
    """Erase and handle UI."""
    # push all boards into bootloader
    num_boards = len(configs)

    with Live(Group(status, progress), transient=True) as live:
        live.console.log("Putting all boards into bootloader mode")
        for board in configs:
            try:
                goto_bootloader(board)
            except TimeoutError:
                live.console.log(
                    f"[red]Failed to put {board.name} into bootloader mode"
                )
                raise

        live.console.log(
            f"Erasing with config: [blue bold]{', '.join(board.name for board in configs)}"
        )
        for b_idx, board in enumerate(configs):
            # TODO do this in parallel
            status.update(f"Sending board {board.name} to bootloader")
            status.update(
                f"Erasing board [yellow]{b_idx + 1}/{num_boards}[/]: [blue bold]{board.name}"
            )
            bootloader.Bootloader(bus=bus, board=board, ui_callback=ui_callback).erase()
            live.console.log(f"[green]{board.name} erased successfully")

        live.console.log(
            f"[bold green]Erase successful ({num_boards} board{'s' if num_boards > 1 else ''} erased)"
        )

        live.console.log("Pushing all boards out of bootloader mode")
        # push all boards out of bootlader
        for board in configs:
            try:
                goto_app(board)
            except TimeoutError:
                live.console.log(
                    f"[red]Failed to put {board.name} into application mode"
                )
                raise
        live.console.log(
            f"[bold green]All boards pushed out of bootloader mode successfully"
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
        set(
            [
                boards.CONFIGS[config_name.strip()]
                for config_name in args.config.split(",")
            ]
        )
    )
    with can.interface.Bus(
            interface=args.bus, channel=args.channel, bitrate=args.bit_rate
    ) as bus:
        if args.erase:
            erase(configs=c)
        else:
            update(configs=c, build_dir=args.build)
