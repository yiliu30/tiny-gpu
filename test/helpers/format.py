import json
import os
from typing import List, Optional
from .logger import logger


FULL_TRACE = os.environ.get("TINY_GPU_FULL_TRACE") == "1"


def _bits_int(bits: str) -> Optional[int]:
    bits = bits.lower()
    if any(bit in "xz" for bit in bits):
        return None
    return int(bits, 2) if bits else 0


def _signal_int(signal) -> Optional[int]:
    return _bits_int(str(signal.value))


def _packed_ints(signal, width: int, count: int) -> List[Optional[int]]:
    bits = str(signal.value).lower().zfill(width * count)
    values = [
        _bits_int(bits[index:index + width])
        for index in range(0, width * count, width)
    ]
    return list(reversed(values))


def _full_trace_state(dut) -> dict:
    dispatch = dut.dispatch_instance
    program_controller = dut.program_memory_controller
    data_controller = dut.data_memory_controller
    return {
        "data_controller": {
            "current_consumer": _packed_ints(data_controller.current_consumer, 3, 4),
            "serving": _signal_int(data_controller.channel_serving_consumer),
            "state": _packed_ints(data_controller.controller_state, 3, 4),
        },
        "data_memory": {
            "read_address": _packed_ints(dut.data_mem_read_address, 8, 4),
            "read_data": _packed_ints(dut.data_mem_read_data, 8, 4),
            "read_ready": _packed_ints(dut.data_mem_read_ready, 1, 4),
            "read_valid": _packed_ints(dut.data_mem_read_valid, 1, 4),
            "write_address": _packed_ints(dut.data_mem_write_address, 8, 4),
            "write_data": _packed_ints(dut.data_mem_write_data, 8, 4),
            "write_ready": _packed_ints(dut.data_mem_write_ready, 1, 4),
            "write_valid": _packed_ints(dut.data_mem_write_valid, 1, 4),
        },
        "dcr": {"thread_count": _signal_int(dut.thread_count)},
        "dispatch": {
            "blocks_dispatched": _signal_int(dispatch.blocks_dispatched),
            "blocks_done": _signal_int(dispatch.blocks_done),
            "core_block_id": _packed_ints(dispatch.core_block_id, 8, 2),
            "core_reset": _packed_ints(dispatch.core_reset, 1, 2),
            "core_start": _packed_ints(dispatch.core_start, 1, 2),
            "core_thread_count": _packed_ints(dispatch.core_thread_count, 3, 2),
            "done": _signal_int(dispatch.done),
            "start_execution": _signal_int(dispatch.start_execution),
        },
        "done": _signal_int(dut.done),
        "fetchers": {
            "read_address": _packed_ints(dut.fetcher_read_address, 8, 2),
            "read_data": _packed_ints(dut.fetcher_read_data, 16, 2),
            "read_ready": _packed_ints(dut.fetcher_read_ready, 1, 2),
            "read_valid": _packed_ints(dut.fetcher_read_valid, 1, 2),
        },
        "lsu_relay": {
            "read_address": _packed_ints(dut.lsu_read_address, 8, 8),
            "read_data": _packed_ints(dut.lsu_read_data, 8, 8),
            "read_ready": _packed_ints(dut.lsu_read_ready, 1, 8),
            "read_valid": _packed_ints(dut.lsu_read_valid, 1, 8),
            "write_address": _packed_ints(dut.lsu_write_address, 8, 8),
            "write_data": _packed_ints(dut.lsu_write_data, 8, 8),
            "write_ready": _packed_ints(dut.lsu_write_ready, 1, 8),
            "write_valid": _packed_ints(dut.lsu_write_valid, 1, 8),
        },
        "program_controller": {
            "current_consumer": _packed_ints(program_controller.current_consumer, 1, 1),
            "serving": _signal_int(program_controller.channel_serving_consumer),
            "state": _packed_ints(program_controller.controller_state, 3, 1),
        },
        "program_memory": {
            "read_address": _packed_ints(dut.program_mem_read_address, 8, 1),
            "read_data": _packed_ints(dut.program_mem_read_data, 16, 1),
            "read_ready": _packed_ints(dut.program_mem_read_ready, 1, 1),
            "read_valid": _packed_ints(dut.program_mem_read_valid, 1, 1),
        },
    }

def format_register(register: int) -> str:
    if register < 13:
        return f"R{register}"
    if register == 13:
        return f"%blockIdx"
    if register == 14:
        return f"%blockDim"
    if register == 15:
        return f"%threadIdx"
    
def format_instruction(instruction: str) -> str:
    opcode = instruction[0:4]
    rd = format_register(int(instruction[4:8], 2))
    rs = format_register(int(instruction[8:12], 2))
    rt = format_register(int(instruction[12:16], 2))
    n = "N" if instruction[4] == 1 else ""
    z = "Z" if instruction[5] == 1 else ""
    p = "P" if instruction[6] == 1 else ""
    imm = f"#{int(instruction[8:16], 2)}"

    if opcode == "0000":
        return "NOP"
    elif opcode == "0001":
        return f"BRnzp {n}{z}{p}, {imm}"
    elif opcode == "0010":
        return f"CMP {rs}, {rt}"
    elif opcode == "0011":
        return f"ADD {rd}, {rs}, {rt}"
    elif opcode == "0100":
        return f"SUB {rd}, {rs}, {rt}"
    elif opcode == "0101":
        return f"MUL {rd}, {rs}, {rt}"
    elif opcode == "0110":
        return f"DIV {rd}, {rs}, {rt}"
    elif opcode == "0111":
        return f"LDR {rd}, {rs}"
    elif opcode == "1000":
        return f"STR {rs}, {rt}"
    elif opcode == "1001":
        return f"CONST {rd}, {imm}"
    elif opcode == "1111":
        return "RET"
    return "UNKNOWN"

def format_core_state(core_state: str) -> str:
    core_state_map = {
        "000": "IDLE",
        "001": "FETCH",
        "010": "DECODE",
        "011": "REQUEST",
        "100": "WAIT",
        "101": "EXECUTE",
        "110": "UPDATE",
        "111": "DONE"
    }
    return core_state_map[core_state]

def format_fetcher_state(fetcher_state: str) -> str:
    fetcher_state_map = {
        "000": "IDLE",
        "001": "FETCHING",
        "010": "FETCHED"
    }
    return fetcher_state_map[fetcher_state]

def format_lsu_state(lsu_state: str) -> str:
    lsu_state_map = {
        "00": "IDLE",
        "01": "REQUESTING",
        "10": "WAITING",
        "11": "DONE"
    }
    return lsu_state_map[lsu_state]

def format_memory_controller_state(controller_state: str) -> str:
    controller_state_map = {
        "000": "IDLE",
        "010": "READ_WAITING",
        "011": "WRITE_WAITING",
        "100": "READ_RELAYING",
        "101": "WRITE_RELAYING"
    }
    return controller_state_map[controller_state]

def format_registers(registers: List[str]) -> str:
    formatted_registers = []
    for i, reg_value in enumerate(registers):
        decimal_value = int(reg_value, 2)  # Convert binary string to decimal
        reg_idx = 15 - i # Register data is provided in reverse order
        formatted_registers.append(f"{format_register(reg_idx)} = {decimal_value}")
    formatted_registers.reverse()
    return ', '.join(formatted_registers)

def format_cycle(dut, cycle_id: int, thread_id: Optional[int] = None):
    if FULL_TRACE:
        thread_id = None
    logger.debug(f"\n================================== Cycle {cycle_id} ==================================")

    for core in dut.cores:
        # Not exactly accurate, but good enough for now
        if int(str(dut.thread_count.value), 2) <= core.i.value * dut.THREADS_PER_BLOCK.value:
            continue

        logger.debug(f"\n+--------------------- Core {core.i.value} ---------------------+")

        instruction = str(core.core_instance.instruction.value)
        logger.debug(f"Instruction Bits: {int(instruction, 2):016b}")
        for thread in core.core_instance.threads:
            if int(thread.i.value) < int(str(core.core_instance.thread_count.value), 2): # if enabled
                block_idx = core.core_instance.block_id.value
                block_dim = int(core.core_instance.THREADS_PER_BLOCK)
                thread_idx = thread.register_instance.THREAD_ID.value
                idx = block_idx * block_dim + thread_idx

                rs = int(str(thread.register_instance.rs.value), 2)
                rt = int(str(thread.register_instance.rt.value), 2)

                reg_input_mux = int(str(core.core_instance.decoded_reg_input_mux.value), 2)
                alu_out = int(str(thread.alu_instance.alu_out.value), 2)
                lsu_out = int(str(thread.lsu_instance.lsu_out.value), 2)
                constant = int(str(core.core_instance.decoded_immediate.value), 2)

                if (thread_id is None or thread_id == idx):
                    logger.debug(f"\n+-------- Thread {idx} --------+")

                    logger.debug("PC:", int(str(core.core_instance.current_pc.value), 2))
                    logger.debug("Instruction:", format_instruction(instruction))
                    logger.debug("Core State:", format_core_state(str(core.core_instance.core_state.value)))
                    logger.debug("Fetcher State:", format_fetcher_state(str(core.core_instance.fetcher_state.value)))
                    logger.debug("LSU State:", format_lsu_state(str(thread.lsu_instance.lsu_state.value)))
                    logger.debug("Registers:", format_registers([str(item.value) for item in thread.register_instance.registers]))
                    logger.debug(f"RS = {rs}, RT = {rt}")

                    if FULL_TRACE:
                        logger.debug("ALU Out:", alu_out)
                        logger.debug("LSU Out:", lsu_out)
                        logger.debug("Constant:", constant)
                        logger.debug("NZP:", _signal_int(thread.pc_instance.nzp))
                    else:
                        if reg_input_mux == 0:
                            logger.debug("ALU Out:", alu_out)
                        if reg_input_mux == 1:
                            logger.debug("LSU Out:", lsu_out)
                        if reg_input_mux == 2:
                            logger.debug("Constant:", constant)

        logger.debug("Core Done:", str(core.core_instance.done.value))

    if FULL_TRACE:
        logger.debug("Trace State:", json.dumps(_full_trace_state(dut), sort_keys=True))
