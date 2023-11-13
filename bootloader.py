"""
bootloader.py
-----------------
Class used to interface with a embedded CAN bootloader.

"""
from typing import Callable, Optional
import boards
import can
import time
import alive_progress
import intelhex
import math

# CAN command message IDs.
ERASE_SECTOR_CAN_ID = 1100
PROGRAM_CAN_ID = 1101
VERIFY_CAN_ID = 1102

# CAN reply message IDs.
ERASE_SECTOR_COMPLETE_ID = 1110
APP_VALIDITY_ID = 1111


class Bootloader:
    def __init__(
        self, bus: can.Bus, ih: intelhex.IntelHex, board: boards.Board, timeout: int = 5
    ) -> None:
        self.bus = bus
        self.ih = ih
        self.board = board
        self.timeout = timeout

    def start_update(self) -> bool:
        """
        Command a board's bootloader to enter update mode by sending the
        "start update" commmand. Await a response.

        Returns:
            True if the bootloader acknowledged the command within the timeout,
            false otherwise.

        """

        def _validator(msg: can.Message) -> bool:
            """Validate that we've received the "update ack" msg."""
            return msg.arbitration_id == self.board.update_ack_can_id

        self.bus.send(
            can.Message(
                arbitration_id=self.board.start_update_can_id,
                data=[],
                is_extended_id=False,
            )
        )
        return (
            self._await_can_msg(validator=_validator, timeout=self.timeout) is not None
        )

    def erase_flash(self) -> bool:
        """
        Erase all flash sectors one by one that would contain the binary. Flash
        memory must first be erased before it can be programmed. Erasing sets all bytes to 0xFF.

        Returns:
            True if the bootloader acknowledged the commands within the timeout,
            false otherwise.

        """

        def _validator(msg: can.Message):
            """Validate that we've received the "erase complete" msg."""
            return msg.arbitration_id == ERASE_SECTOR_COMPLETE_ID

        def _intersect(a_min, a_max, b_min, b_max):
            """1-D intersection to check if an app's hex and a flash sector share any addresses."""
            return a_max >= b_min and b_max >= a_min

        # To speedup programming, only erase the sectors used by the app.
        flash_sectors_to_erase = [
            sector
            for sector in self.board.mcu.flash_sectors
            if _intersect(
                a_min=self.ih.minaddr(),
                a_max=self.ih.minaddr() + self.size_bytes(),
                b_min=sector.base_address,
                b_max=sector.base_address + sector.size,
            )
        ]

        with alive_progress.alive_bar(
            total=len(flash_sectors_to_erase), title="Erasing FLASH sectors"
        ) as erase_bar:
            for sector in flash_sectors_to_erase:
                if not sector.writeable:
                    raise RuntimeError(
                        "Attempted to write to a readonly memory sector!"
                    )

                self.bus.send(
                    can.Message(
                        arbitration_id=ERASE_SECTOR_CAN_ID,
                        data=[sector.id],
                        is_extended_id=False,
                    )
                )
                erase_bar()

                if not self._await_can_msg(validator=_validator, timeout=self.timeout):
                    return False

        return True

    def program(self) -> None:
        """
        Program the binary into flash. There is no CAN handshake here to reduce
        latency during programming. Also, the bootloader will verify the app's code is valid
        by computing a checksum.

        """
        with alive_progress.alive_bar(
            total=self.size_bytes(), title="Programming code"
        ) as program_bar:
            for address in range(
                self.ih.minaddr(), self.ih.minaddr() + self.size_bytes(), 8
            ):
                data = [self.ih[address + i] for i in range(0, 8)]
                self.bus.send(
                    can.Message(
                        arbitration_id=PROGRAM_CAN_ID, data=data, is_extended_id=False
                    )
                )
                program_bar(8)
                time.sleep(1e-6)

    def verify(self) -> bool:
        """
        Query the bootloader is programming was successful. To do this, 2 checksums are computed:
        1. At compile time, a checksum of the app hex is calculated and added to the generated image's hex.
        2. The bootloader can independly calculate a checksum of the app code in its flash memory.

        If these match, we can conclude with confidence the data programmed into flash by the bootloader
        matches the binary built by the compiler.

        Returns:
            Whether or not the bootloader verified the app, within the timeout.

        """

        def _validator(msg: can.Message):
            """Validate that we've received the "app validity" msg, and the app is valid."""
            return msg.arbitration_id == APP_VALIDITY_ID and msg.data[0] == 0x01

        self.bus.send(
            can.Message(arbitration_id=VERIFY_CAN_ID, data=[], is_extended_id=False)
        )
        return self._await_can_msg(_validator) is not None

    def update(self) -> bool:
        """
        Run the update procedure for this bootloader.

        Returns:
            Whether or not the update was successful.

        """
        # TODO: Make this pretty!
        assert self.start_update()
        assert self.erase_flash()
        self.program()
        assert self.verify()
        print("Application verified successfully.")

    def _await_can_msg(
        self, validator=Callable[[can.Message], bool], timeout: int = 5
    ) -> Optional[can.Message]:
        """
        Helper function to await a CAN msg response within a timeout, with a validator function.

        """
        start = time.time()
        while time.time() - start < timeout:
            rx_msg = self.bus.recv(timeout=1)
            if rx_msg:
                if (validator and validator(rx_msg)) or validator is None:
                    return rx_msg

        return None

    def size_bytes(self) -> int:
        """
        Get the size of the binary. We send 2 4-byte words at a time during programming, so the size
        up to nearest 8 bytes for convenience.

        Returns:
            Size, in bytes.

        """
        return int(math.ceil((self.ih.maxaddr() - self.ih.minaddr()) / 8) * 8)
