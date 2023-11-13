"""
boards.py
-----------------
Config info about boards that can be updated.

"""
from typing import List
import dataclasses
import os


KB = 1024  # bytes


@dataclasses.dataclass(frozen=True)
class FlashSector:
    id: int
    base_address: int
    size: int
    writeable: bool = False


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
            id=sector_id, base_address=base, size=size_kb * KB, writeable=writeable
        )
        for sector_id, base, size_kb, writeable in [
            (0, 0x08000000, 16, False),  # Sector 0
            (1, 0x08004000, 16, False),  # Sector 1
            (2, 0x08008000, 16, False),  # Sector 2
            (3, 0x0800C000, 16, False),  # Sector 3
            (4, 0x08010000, 64, False),  # Sector 4
            (5, 0x08020000, 128, False),  # Sector 5
            (6, 0x08040000, 128, True),  # Sector 6
            (7, 0x08060000, 128, True),  # Sector 7
            (8, 0x08080000, 128, True),  # Sector 8
            (9, 0x080A0000, 128, True),  # Sector 9
            (10, 0x080C0000, 128, True),  # Sector 10
            (11, 0x080E0000, 128, True),  # Sector 11
        ]
    ],
)

BMS = Board(
    name="BMS",
    start_update_can_id=1000,
    update_ack_can_id=1001,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "thruna", "BMS", "BMS.elf.hex"),
)
DCM = Board(
    name="DCM",
    start_update_can_id=1010,
    update_ack_can_id=1011,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "thruna", "DCM", "DCM.elf.hex"),
)
FSM = Board(
    name="FSM",
    start_update_can_id=1020,
    update_ack_can_id=1021,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "thruna", "FSM", "FSM.elf.hex"),
)
PDM = Board(
    name="PDM",
    start_update_can_id=1030,
    update_ack_can_id=1031,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "thruna", "PDM", "PDM.elf.hex"),
)
DIM = Board(
    name="DIM",
    start_update_can_id=1040,
    update_ack_can_id=1031,
    mcu=STM32F412_MCU,
    path=os.path.join("firmware", "thruna", "DIM", "DIM.elf.hex"),
)

CONFIGS = {
    "BMS": [BMS],
    "DCM": [DCM],
    "FSM": [FSM],
    "PDM": [PDM],
    "DIM": [DIM],
    "thruna": [BMS, DCM, FSM, PDM, DIM],
}
