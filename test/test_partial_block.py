import cocotb
from cocotb.triggers import RisingEdge

from .helpers.format import format_cycle
from .helpers.memory import Memory
from .helpers.setup import setup


@cocotb.test()
async def test_partial_block(dut):
    program_memory = Memory(
        dut=dut,
        addr_bits=8,
        data_bits=16,
        channels=1,
        name="program",
    )
    program = [
        0b1001000100000111,  # CONST R1, #7
        0b1111000000000000,  # RET
    ]

    data_memory = Memory(dut=dut, addr_bits=8, data_bits=8, channels=4, name="data")

    await setup(
        dut=dut,
        program_memory=program_memory,
        program=program,
        data_memory=data_memory,
        data=[],
        threads=5,
    )

    for cycle in range(60):
        data_memory.run()
        program_memory.run()
        await cocotb.triggers.ReadOnly()
        format_cycle(dut, cycle)
        await RisingEdge(dut.clk)

