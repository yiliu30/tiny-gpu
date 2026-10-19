"""Compute core; mirrors ``src/core.sv``."""

from __future__ import annotations

from typing import Sequence

from . import isa
from .alu import Alu
from .decoder import Decoder, DecoderOutputs
from .fetcher import Fetcher, FetcherOutputs
from .pc import PcUnit
from .registers import RegisterFile
from .scheduler import Scheduler, SchedulerOutputs
from .stubs import IdleLsu, LsuOutputs
from .trace import TraceRecord


class Core:
    """One compute core containing shared control and per-lane execution units."""

    def __init__(self, *, threads_per_block: int = 4, lsu_factory=IdleLsu) -> None:
        """Create shared control plus one arithmetic, register, and program-counter unit per lane."""

        self.threads_per_block = threads_per_block

        self.reset = 0
        self.start = 0
        self.block_id = 0
        self.thread_count = threads_per_block

        self.program_mem_read_valid = 0
        self.program_mem_read_address = 0
        self.program_mem_read_ready = 0
        self.program_mem_read_data = 0

        self.data_mem_read_valid = [0] * threads_per_block
        self.data_mem_read_address = [0] * threads_per_block
        self.data_mem_read_ready = [0] * threads_per_block
        self.data_mem_read_data = [0] * threads_per_block
        self.data_mem_write_valid = [0] * threads_per_block
        self.data_mem_write_address = [0] * threads_per_block
        self.data_mem_write_data = [0] * threads_per_block
        self.data_mem_write_ready = [0] * threads_per_block

        self.fetcher = Fetcher()
        self.decoder = Decoder()
        self.scheduler = Scheduler(threads_per_block=threads_per_block)

        self.alus = [Alu() for _ in range(threads_per_block)]
        self.lsus = [lsu_factory() for _ in range(threads_per_block)]
        self.registers = [
            RegisterFile(threads_per_block=threads_per_block, thread_id=lane)
            for lane in range(threads_per_block)
        ]
        self.pcs = [PcUnit() for _ in range(threads_per_block)]

        self._staged: tuple | None = None

    @property
    def core_state(self) -> int:
        """Return the scheduler's current core state code."""

        return self.scheduler.core_state

    @property
    def current_pc(self) -> int:
        """Return the shared program counter used to fetch the current instruction."""

        return self.scheduler.current_pc

    @property
    def done(self) -> int:
        """Return whether every active lane has reached the return instruction."""

        return self.scheduler.done

    @property
    def fetcher_state(self) -> int:
        """Return the instruction fetcher's current state code."""

        return self.fetcher.state

    @property
    def instruction(self) -> int:
        """Return the most recently fetched 16-bit instruction."""

        return self.fetcher.instruction

    @property
    def lsu_state(self) -> list[int]:
        """Return the load-store state for every lane."""

        return [lsu.state for lsu in self.lsus]

    @property
    def next_pc(self) -> list[int]:
        """Return the staged next program counter for every lane."""

        return [pc.next_pc for pc in self.pcs]

    def evaluate_clocked(self) -> None:
        """Evaluate every clocked core component while all of them still see old state."""

        decoder_now = self.decoder.outputs

        fetcher_next = self.fetcher.evaluate(
            reset=bool(self.reset),
            core_state=self.core_state,
            current_pc=self.current_pc,
            mem_read_ready=self.program_mem_read_ready,
            mem_read_data=self.program_mem_read_data,
        )
        decoder_next = self.decoder.evaluate(
            reset=bool(self.reset),
            core_state=self.core_state,
            instruction=self.instruction,
        )
        scheduler_next = self.scheduler.evaluate(
            reset=bool(self.reset),
            start=self.start,
            decoded_mem_read_enable=decoder_now.mem_read_enable,
            decoded_mem_write_enable=decoder_now.mem_write_enable,
            decoded_ret=decoder_now.ret,
            fetcher_state=self.fetcher_state,
            lsu_state=self.lsu_state,
            next_pc=self.next_pc,
        )

        alu_next: list[int] = []
        lsu_next: list[LsuOutputs] = []
        register_next = []
        pc_next = []
        for lane in range(self.threads_per_block):
            enable = lane < self.thread_count
            alu_out = self.alus[lane].evaluate(
                reset=bool(self.reset),
                enable=enable,
                core_state=self.core_state,
                arithmetic_mux=decoder_now.alu_arithmetic_mux,
                output_mux=decoder_now.alu_output_mux,
                rs=self.registers[lane].rs,
                rt=self.registers[lane].rt,
            )
            alu_next.append(alu_out)

            lsu_out = self.lsus[lane].evaluate(
                reset=bool(self.reset),
                enable=enable,
                core_state=self.core_state,
                decoded_mem_read_enable=decoder_now.mem_read_enable,
                decoded_mem_write_enable=decoder_now.mem_write_enable,
                rs=self.registers[lane].rs,
                rt=self.registers[lane].rt,
                mem_read_ready=self.data_mem_read_ready[lane],
                mem_read_data=self.data_mem_read_data[lane],
                mem_write_ready=self.data_mem_write_ready[lane],
            )
            lsu_next.append(lsu_out)

            register_next.append(
                self.registers[lane].evaluate(
                    reset=bool(self.reset),
                    enable=enable,
                    block_id=self.block_id,
                    core_state=self.core_state,
                    reg_write_enable=decoder_now.reg_write_enable,
                    reg_input_mux=decoder_now.reg_input_mux,
                    rd_address=decoder_now.rd_address,
                    rs_address=decoder_now.rs_address,
                    rt_address=decoder_now.rt_address,
                    immediate=decoder_now.immediate,
                    alu_out=self.alus[lane].alu_out,
                    lsu_out=self.lsus[lane].lsu_out,
                )
            )
            pc_next.append(
                self.pcs[lane].evaluate(
                    reset=bool(self.reset),
                    enable=enable,
                    core_state=self.core_state,
                    decoded_nzp=decoder_now.nzp,
                    decoded_immediate=decoder_now.immediate,
                    nzp_write_enable=decoder_now.nzp_write_enable,
                    pc_mux=decoder_now.pc_mux,
                    alu_out=self.alus[lane].alu_out,
                    current_pc=self.current_pc,
                )
            )

        self._staged = (
            fetcher_next,
            decoder_next,
            scheduler_next,
            alu_next,
            lsu_next,
            register_next,
            pc_next,
        )

    def commit(self) -> None:
        """Publish all staged core updates together at the simulated clock edge."""

        if self._staged is None:
            raise RuntimeError("evaluate_clocked() must run before commit()")
        (
            fetcher_next,
            decoder_next,
            scheduler_next,
            alu_next,
            lsu_next,
            register_next,
            pc_next,
        ) = self._staged

        self.fetcher.state = fetcher_next.state
        self.fetcher.mem_read_valid = fetcher_next.mem_read_valid
        self.fetcher.mem_read_address = fetcher_next.mem_read_address
        self.fetcher.instruction = fetcher_next.instruction

        self.decoder.outputs = decoder_next

        self.scheduler.current_pc = scheduler_next.current_pc
        self.scheduler.core_state = scheduler_next.core_state
        self.scheduler.done = scheduler_next.done

        for lane in range(self.threads_per_block):
            self.alus[lane].alu_out = alu_next[lane]
            lsu_outputs = lsu_next[lane]
            lsu = self.lsus[lane]
            lsu.state = lsu_outputs.state
            lsu.lsu_out = lsu_outputs.lsu_out
            lsu.mem_read_valid = lsu_outputs.mem_read_valid
            lsu.mem_read_address = lsu_outputs.mem_read_address
            lsu.mem_write_valid = lsu_outputs.mem_write_valid
            lsu.mem_write_address = lsu_outputs.mem_write_address
            lsu.mem_write_data = lsu_outputs.mem_write_data

            register_outputs = register_next[lane]
            self.registers[lane].rs = register_outputs.rs
            self.registers[lane].rt = register_outputs.rt
            self.registers[lane].values = list(register_outputs.values)

            pc_outputs = pc_next[lane]
            self.pcs[lane].nzp = pc_outputs.nzp
            self.pcs[lane].next_pc = pc_outputs.next_pc

            self.data_mem_read_valid[lane] = lsu.mem_read_valid
            self.data_mem_read_address[lane] = lsu.mem_read_address
            self.data_mem_write_valid[lane] = lsu.mem_write_valid
            self.data_mem_write_address[lane] = lsu.mem_write_address
            self.data_mem_write_data[lane] = lsu.mem_write_data

        self.program_mem_read_valid = self.fetcher.mem_read_valid
        self.program_mem_read_address = self.fetcher.mem_read_address
        self._staged = None

    def observe(self, cycle: int, *, compatibility: bool = True) -> list[TraceRecord]:
        """Capture one trace record per active lane before the next clock edge."""

        decoded = isa.split_instruction(self.instruction)
        records = []
        for lane in range(min(self.thread_count, self.threads_per_block)):
            alu_out = None
            lsu_out = None
            constant = None
            if not compatibility or self.decoder.outputs.reg_input_mux == isa.REG_ARITHMETIC:
                alu_out = self.alus[lane].alu_out
            elif self.decoder.outputs.reg_input_mux == isa.REG_MEMORY:
                lsu_out = self.lsus[lane].lsu_out
            else:
                constant = self.decoder.outputs.immediate

            records.append(
                TraceRecord(
                    cycle=cycle,
                    core=0,
                    lane=lane,
                    thread_id=(self.block_id * self.threads_per_block + lane) & 0xFF,
                    core_state=isa.CORE_STATE_NAMES[self.core_state],
                    fetcher_state=isa.FETCHER_STATE_NAMES[self.fetcher_state],
                    pc=self.current_pc,
                    instruction_bits=self.instruction,
                    decoded=decoded,
                    done=self.done,
                    lsu_state=isa.LSU_STATE_NAMES[self.lsus[lane].state],
                    registers={
                        name: value
                        for name, value in zip(isa.REGISTER_NAMES, self.registers[lane].values)
                    },
                    rs=self.registers[lane].rs,
                    rt=self.registers[lane].rt,
                    alu_out=alu_out,
                    lsu_out=lsu_out,
                    constant=constant,
                )
            )
        return records
