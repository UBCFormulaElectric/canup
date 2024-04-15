"""
boards.py
-----------------
Config info about boards that can be updated.

"""

from typing import List
import os
import dataclasses

KB = 1024  # bytes


@dataclasses.dataclass(frozen=True)
class FlashSector:
    id: int
    base_address: int
    size: int
    write_protect: bool = False

    @property
    def max_address(self) -> int:
        return self.base_address + self.size - 1


@dataclasses.dataclass(frozen=True)
class Microcontroller:
    name: str
    flash_sectors: List[FlashSector]


@dataclasses.dataclass(frozen=True)
class Board:
    name: str
    start_update_can_id: int
    update_ack_can_id: int
    mcu: Microcontroller
    path: str


STM32F412_MCU = Microcontroller(
    name="STM32F412xx",
    # Referenced from ST RM0402.
    # (https://www.st.com/resource/en/reference_manual/dm00180369-stm32f412-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf)
    flash_sectors=[
        FlashSector(
            id=sector_id,
            base_address=base,
            size=size_kb * KB,
            write_protect=write_protect,
        )
        for sector_id, base, size_kb, write_protect in [
            # Sectors 0-4 taken up by bootloader code, so mark them as write-protect.
            (0, 0x08000000, 16, True),  # Sector 0
            (1, 0x08004000, 16, True),  # Sector 1
            (2, 0x08008000, 16, True),  # Sector 2
            (3, 0x0800C000, 16, True),  # Sector 3
            (4, 0x08010000, 64, True),  # Sector 4
            (5, 0x08020000, 128, False),  # Sector 5
            (6, 0x08040000, 128, False),  # Sector 6
            (7, 0x08060000, 128, False),  # Sector 7
            (8, 0x08080000, 128, False),  # Sector 8
            (9, 0x080A0000, 128, False),  # Sector 9
            (10, 0x080C0000, 128, False),  # Sector 10
            (11, 0x080E0000, 128, False),  # Sector 11
        ]
    ],
)

STM32H733_MCU = Microcontroller(
    name="STM32H733xx",
    # Referenced from ST RM0468.
    # (https://www.st.com/resource/en/reference_manual/rm0468-stm32h723733-stm32h725735-and-stm32h730-value-line-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
    flash_sectors=[
        FlashSector(
            id=sector_id,
            base_address=base,
            size=size_kb * KB,
            write_protect=write_protect,
        )
        for sector_id, base, size_kb, write_protect in [
            # Sectors 0 is taken up by bootloader code, so mark it as write-protect.
            (0, 0x08000000, 128, True),  # Sector 0
            (1, 0x08020000, 128, False),  # Sector 1
            (2, 0x08040000, 128, False),  # Sector 2
            (3, 0x08060000, 128, False),  # Sector 3
            (4, 0x08080000, 128, False),  # Sector 4
            (5, 0x080A0000, 128, False),  # Sector 5
            (6, 0x080C0000, 128, False),  # Sector 6
            (7, 0x080E0000, 128, False),  # Sector 7
        ]
    ],
)

quadruna_VC = Board(
    name="VC",
    start_update_can_id=1210,
    update_ack_can_id=1211,
    mcu=STM32H733_MCU,
    path=os.path.join("firmware", "quadruna", "VC", "quadruna_VC_app_metadata.hex"),
)
quadruna_BMS = Board(
    name="BMS",
    start_update_can_id=1200,
    update_ack_can_id=1201,
    mcu=STM32H733_MCU,
    path=os.path.join("firmware", "quadruna", "BMS", "quadruna_BMS_app_metadata.hex"),
)
quadruna_FSM = Board(
    name="FSM",
    start_update_can_id=1220,
    update_ack_can_id=1221,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "quadruna", "FSM", "quadruna_FSM_app_metadata.hex"),
)
quadruna_RSM = Board(
    name="RSM",
    start_update_can_id=1230,
    update_ack_can_id=1231,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "quadruna", "RSM", "quadruna_RSM_app_metadata.hex"),
)
quadruna_CRIT = Board(
    name="CRIT",
    start_update_can_id=1240,
    update_ack_can_id=1241,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "quadruna", "CRIT", "quadruna_CRIT_app_metadata.hex"),
)
h7dev = Board(
    name="h7dev",
    start_update_can_id=1300,
    update_ack_can_id=1301,
    mcu=STM32H733_MCU,
    path=os.path.join("firmware", "dev", "h7dev", "h7dev_app_metadata.hex"),
)

CONFIGS = {
    "quadruna_VC": [quadruna_VC],
    "quadruna_BMS": [quadruna_BMS],
    "quadruna_FSM": [quadruna_FSM],
    "quadruna_RSM": [quadruna_RSM],
    "quadruna_CRIT": [quadruna_CRIT],
    "quadruna": [quadruna_VC, quadruna_BMS, quadruna_FSM, quadruna_RSM, quadruna_CRIT],
    "h7dev": [h7dev],
}
