"""
bootloader.py
-----------------
Class used to interface with a embedded CAN bootloader.

"""

from typing import Callable, Optional
import math
import can
import time
import intelhex
import boards

# Keep CAN protocol in sync with:
# Consolidated-Firmware/firmware/boot/shared/config.h

# CAN command message IDs.
ERASE_SECTOR_CAN_ID = 1000
PROGRAM_CAN_ID = 1001
VERIFY_CAN_ID = 1002

# CAN reply message IDs.
ERASE_SECTOR_COMPLETE_CAN_ID = 1010
APP_VALIDITY_CAN_ID = 1011

# Verify response options.
# Keep in sync with:
# Consolidated-Firmware/firmware/boot/bootloader.c
BOOT_STATUS_APP_VALID = 0
BOOT_STATUS_APP_INVALID = 1
BOOT_STATUS_NO_APP = 2

# The minimum amount of data the microcontroller can program at a time.
MIN_PROG_SIZE_BYTES = 32

ALL_PACKETS_VALID = 0xFFFFFFFFFFFFFFFF
WINDOW_SIZE = 64 


class Bootloader:
    def __init__(
        self,
        bus: can.Bus,
        board: boards.Board,
        ui_callback: Callable,
        ih: intelhex.IntelHex = None,
        timeout: int = 5,
    ) -> None:
        self.bus = bus
        self.ih = ih
        self.board = board
        self.timeout = timeout
        self.ui_callback = ui_callback
        self.dropped_packets = set()

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
            return True if msg.arbitration_id == self.board.update_ack_can_id else None

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

    def erase_sectors(self, sectors) -> bool:
        """
        Erase specific sectors of FLASH, sets all bytes to 0xFF. FLASH memory must first be
        erased before it can be programmed.

        Returns:
            True if the bootloader acknowledged the commands within the timeout,
            false otherwise.

        """

        def _validator(msg: can.Message):
            """Validate that we've received the "erase complete" msg."""
            return True if msg.arbitration_id == ERASE_SECTOR_COMPLETE_CAN_ID else None

        erase_size = sum([sector.size for sector in sectors])
        erase_progress = 0

        for sector in sectors:
            if self.ui_callback:
                self.ui_callback("Erasing FLASH sectors", erase_size, erase_progress)

            if sector.write_protect:
                raise RuntimeError("Attempted to write to a readonly memory sector!")

            self.bus.send(
                can.Message(
                    arbitration_id=ERASE_SECTOR_CAN_ID,
                    data=[sector.id],
                    is_extended_id=False,
                )
            )
            if not self._await_can_msg(validator=_validator, timeout=self.timeout):
                return False

            erase_progress += sector.size

        if self.ui_callback:
            self.ui_callback("Erasing FLASH sectors", erase_size, erase_size)

        return True

    def program(self) -> None:
        """
        Program the binary into flash. There is no CAN handshake here to reduce
        latency during programming. Also, the bootloader will verify the app's code is valid
        by computing a checksum.
        """

        # updated changes: built a TCP sequence number inspired packet validity checker. Essentially we have 64 of CAN IDs for each board
        # reserved for bootloading. These can ids represent sequential ids for each packet in a 64 packet window. On the board side, the board expects a 
        # specific can id (starts with 1 and increments up to 64) if it matches then the board sets the respective bit in its return message (1 packet (1 indexed) = 0th bit (0 indexed))
        # after 64 packets it returns a 64 bit message describing if the packet was recieved correctly (1 = yes, 0 = no). Based on this message we can populate a set containing a 
        # tuple (address, msg) after our first tranmission if the set of missed packets is not empty we send a START_RETRANSMISSION MESSAGE which expects sequential CAN ids within the same 1-64 range
        #  however, now for each packet we do not slide our window until a packet has been acked and each packet will have a returned ack status back in comparison to the earlier 64 packs
        # this will continue until the set is empty and then send an end tranmission message  

        packet_in_window_index = 0

        def _validator(msg: can.Message):
            "Validate that mem was programmed successfully"
            print(f"can id is {msg.arbitration_id}")
            if msg.arbitration_id == (self.board.boot_load_bin_can_id + WINDOW_SIZE) and msg.data == ALL_PACKETS_VALID:
                return True
            
            status_msg_int = int.from_bytes(msg.data, byteorder="little")
            dropped_packets_pos = ALL_PACKETS_VALID ^ status_msg_int # this will set create a mask where all the dropped backet positions are 1 and not dropped are 0

            for pos in range(WINDOW_SIZE):
                if dropped_packets_pos & (1 << pos) != 0:
                    # since we increment memory address by 8 bytes at a time and we know that our current address is pointing to the highest 8-byte associated to the window 
                    # we want to save the address assocaited to this particular message
                    self.dropped_packets.add(address - (WINDOW_SIZE - pos) * 8)
                    print(f"Address is {address}\n")
                    print(f"Packet dropped associated to bin address {address - (WINDOW_SIZE - pos) * 8}\n") #debugging
            return True # defaulting to true for debugging 

        for i, address in enumerate(
            range(self.ih.minaddr(), self.ih.minaddr() + self.size_bytes(), 8)
        ):
            if self.ui_callback and i % 128 == 0:
                self.ui_callback("Programming data", self.size_bytes(), i * 8)
            data = [self.ih[address + i] for i in range(0, 8)]

            self.bus.send(
                can.Message(
                    arbitration_id=self.board.boot_load_bin_can_id + packet_in_window_index, data=data, is_extended_id=False
                )
            )
            if packet_in_window_index == WINDOW_SIZE - 1:
                if not self._await_can_msg(validator=_validator, timeout=self.timeout):
                    return False

            packet_in_window_index = (packet_in_window_index + 1) % WINDOW_SIZE 
            # Empirically, this tiny delay between messages seems to improve reliability.
            time.sleep(0.0005)

        if self.ui_callback:
            self.ui_callback("Programming data", self.size_bytes(), self.size_bytes())

    def status(self) -> Optional[int]:
        """
        Query the bootloader if programming was successful. To do this, 2 checksums are computed:
        1. At compile time, a checksum of the app hex is calculated and added to the generated image's hex.
        2. The bootloader can independly calculate a checksum of the app code in its flash memory.

        If these match, we can conclude with confidence the data programmed into flash by the bootloader
        matches the binary built by the compiler.

        Returns:
            Message with bootloader's status, or None if no message was received within the timeout.
            The first byte of the message is one of BOOT_STATUS_*. (NO_APP, APP_INVALID, APP_VALID)

        """

        def _validator(msg: can.Message):
            """Validate that we've received the "app validity" msg, and the app is valid."""
            return True if msg.arbitration_id == APP_VALIDITY_CAN_ID else None

        self.bus.send(
            can.Message(arbitration_id=VERIFY_CAN_ID, data=[], is_extended_id=False)
        )
        rx_msg = self._await_can_msg(_validator)
        if rx_msg is None:
            return None

        return rx_msg.data[0]

    def update(self) -> None:
        """
        Run the update procedure for this bootloader.

        """
        def _intersect(a_min, a_max, b_min, b_max):
            """1-D intersection to check if an app's hex and a flash sector share any addresses."""
            return a_max >= b_min and b_max >= a_min

        if not self.start_update():
            raise RuntimeError(
                f"Bootloader for {self.board.name} did not respond to command to start a firmware update."
            )

        time.sleep(0.1)

        # To speedup programming, only erase the sectors used by the app.
        app_flash_sectors = [
            sector
            for sector in self.board.mcu.flash_sectors
            if _intersect(
                a_min=self.ih.minaddr(),
                a_max=self.ih.minaddr() + self.size_bytes(),
                b_min=sector.base_address,
                b_max=sector.max_address,
            )
        ]
        if not self.erase_sectors(app_flash_sectors):
            raise RuntimeError(
                f"Bootloader for {self.board.name} did not respond to command to erase flash memory."
            )
        time.sleep(0.5)

        self.program()
        time.sleep(0.5)

        self.ui_callback("Verifying programming", self.size_bytes(), 0)
        boot_status = self.status()
        if boot_status is not None:
            if boot_status != BOOT_STATUS_APP_VALID:
                raise RuntimeError(
                    f"Bootloader for {self.board.name} failed to verify application integrity, something went wrong during updating."
                )
        else:
            raise RuntimeError(
                f"Bootloader for {self.board.name} did not respond to command to verify application integrity."
            )

        self.ui_callback("Verifying programming", self.size_bytes(), self.size_bytes())
        time.sleep(0.5)

    def erase(self) -> None:
        """
        Erase this bootloader's application.

        """
        if not self.start_update():
            raise RuntimeError(
                f"Bootloader for {self.board.name} did not respond to erase command."
            )

        writeable_sectors = [
            sector
            for sector in self.board.mcu.flash_sectors
            if not sector.write_protect
        ]
        erase_size = sum([sector.size for sector in writeable_sectors])

        if not self.erase_sectors(writeable_sectors):
            raise RuntimeError(
                f"Bootloader for {self.board.name} did not respond to command to erase flash memory."
            )
        time.sleep(0.5)

        self.ui_callback("Verifying erase", erase_size, 0)
        boot_status = self.status()
        if boot_status is not None:
            if boot_status != BOOT_STATUS_NO_APP:
                raise RuntimeError(
                    f"Bootloader for {self.board.name} failed to verify erase, something went wrong."
                )
        else:
            raise RuntimeError(
                f"Bootloader for {self.board.name} did not respond to command to erase flash."
            )

        self.ui_callback("Verifying erase", erase_size, erase_size)
        time.sleep(0.5)

    def _await_can_msg(
        self, validator=Callable[[can.Message], Optional[bool]], timeout: int = 5
    ) -> Optional[can.Message]:
        """
        Helper function to await a CAN msg response within a timeout, with a validator function.

        """
        start = time.time()
        while time.time() - start < timeout:
            rx_msg = self.bus.recv(timeout=1)
            if rx_msg:
                if validator:
                    if validator(rx_msg) is True:
                        return rx_msg
                    if validator(rx_msg) is False:
                        return False

        return None

    def size_bytes(self) -> int:
        """
        Get the size of the binary. This **must** be a multiple of 32, since the
        STM32H733xx microcontroller can only write 32 bytes at a time. See
        `firmware/boot/bootloader_h7.c` for how this works on the
        microcontroller side.

        Returns:
            Size, in bytes.

        """
        return int(
            math.ceil((self.ih.maxaddr() - self.ih.minaddr()) / MIN_PROG_SIZE_BYTES)
            * MIN_PROG_SIZE_BYTES
        )