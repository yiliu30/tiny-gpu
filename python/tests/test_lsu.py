from tiny_gpu import isa
from tiny_gpu.lsu import Lsu


def evaluate(lsu, **overrides):
    values = dict(
        reset=False,
        enable=True,
        core_state=isa.CORE_REQUEST,
        decoded_mem_read_enable=0,
        decoded_mem_write_enable=0,
        rs=9,
        rt=7,
        mem_read_ready=0,
        mem_read_data=0,
        mem_write_ready=0,
    )
    values.update(overrides)
    return lsu.evaluate(**values)


def advance(lsu, **overrides):
    outputs = evaluate(lsu, **overrides)
    lsu.state = outputs.state
    lsu.lsu_out = outputs.lsu_out
    lsu.mem_read_valid = outputs.mem_read_valid
    lsu.mem_read_address = outputs.mem_read_address
    lsu.mem_write_valid = outputs.mem_write_valid
    lsu.mem_write_address = outputs.mem_write_address
    lsu.mem_write_data = outputs.mem_write_data
    return outputs


def test_load_request_wait_and_done_sequence():
    lsu = Lsu()
    assert advance(lsu, decoded_mem_read_enable=1).state == isa.LSU_REQUESTING
    request = advance(lsu, core_state=isa.CORE_WAIT, decoded_mem_read_enable=1)
    assert (request.state, request.mem_read_valid, request.mem_read_address) == (
        isa.LSU_WAITING,
        1,
        9,
    )
    response = advance(
        lsu,
        core_state=isa.CORE_WAIT,
        decoded_mem_read_enable=1,
        mem_read_ready=1,
        mem_read_data=42,
    )
    assert (response.state, response.mem_read_valid, response.lsu_out) == (
        isa.LSU_DONE,
        0,
        42,
    )
    assert advance(lsu, core_state=isa.CORE_UPDATE, decoded_mem_read_enable=1).state == isa.LSU_IDLE


def test_store_request_carries_rs_and_rt():
    lsu = Lsu()
    advance(lsu, decoded_mem_write_enable=1)
    request = advance(lsu, core_state=isa.CORE_WAIT, decoded_mem_write_enable=1)
    assert (request.mem_write_valid, request.mem_write_address, request.mem_write_data) == (1, 9, 7)
    response = advance(
        lsu,
        core_state=isa.CORE_WAIT,
        decoded_mem_write_enable=1,
        mem_write_ready=1,
    )
    assert (response.state, response.mem_write_valid) == (isa.LSU_DONE, 0)


def test_load_waits_for_multiple_cycles_before_ready():
    lsu = Lsu()
    advance(lsu, decoded_mem_read_enable=1)
    request = advance(lsu, core_state=isa.CORE_WAIT, decoded_mem_read_enable=1)
    assert (request.state, request.mem_read_valid, request.lsu_out) == (
        isa.LSU_WAITING,
        1,
        0,
    )

    for _ in range(2):
        waiting = advance(
            lsu,
            core_state=isa.CORE_WAIT,
            decoded_mem_read_enable=1,
            mem_read_ready=0,
        )
        assert waiting.state == isa.LSU_WAITING
        assert waiting.mem_read_valid == 1
        assert waiting.lsu_out == 0

    response = advance(
        lsu,
        core_state=isa.CORE_WAIT,
        decoded_mem_read_enable=1,
        mem_read_ready=1,
        mem_read_data=42,
    )
    assert (response.state, response.mem_read_valid, response.lsu_out) == (
        isa.LSU_DONE,
        0,
        42,
    )


def test_store_waits_for_multiple_cycles_before_ready():
    lsu = Lsu()
    advance(lsu, decoded_mem_write_enable=1)
    request = advance(lsu, core_state=isa.CORE_WAIT, decoded_mem_write_enable=1)
    assert (request.state, request.mem_write_valid) == (isa.LSU_WAITING, 1)

    for _ in range(2):
        waiting = advance(
            lsu,
            core_state=isa.CORE_WAIT,
            decoded_mem_write_enable=1,
            mem_write_ready=0,
        )
        assert waiting.state == isa.LSU_WAITING
        assert waiting.mem_write_valid == 1
        assert (waiting.mem_write_address, waiting.mem_write_data) == (9, 7)

    response = advance(
        lsu,
        core_state=isa.CORE_WAIT,
        decoded_mem_write_enable=1,
        mem_write_ready=1,
    )
    assert (response.state, response.mem_write_valid) == (isa.LSU_DONE, 0)


def test_disabled_lane_holds_all_outputs():
    lsu = Lsu()
    lsu.state = isa.LSU_WAITING
    lsu.mem_read_valid = 1
    outputs = evaluate(lsu, enable=False, decoded_mem_read_enable=1)
    assert outputs.state == isa.LSU_WAITING
    assert outputs.mem_read_valid == 1

