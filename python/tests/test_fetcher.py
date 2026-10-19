from tiny_gpu import isa
from tiny_gpu.fetcher import Fetcher


def test_fetcher_request_ready_and_decode_reset_sequence():
    fetcher = Fetcher()
    fetching = fetcher.evaluate(
        reset=False,
        core_state=isa.CORE_FETCH,
        current_pc=7,
        mem_read_ready=0,
        mem_read_data=0,
    )
    assert (fetching.state, fetching.mem_read_valid, fetching.mem_read_address) == (
        isa.FETCHER_FETCHING,
        1,
        7,
    )
    fetcher.state = fetching.state
    fetcher.mem_read_valid = fetching.mem_read_valid

    fetched = fetcher.evaluate(
        reset=False,
        core_state=isa.CORE_FETCH,
        current_pc=7,
        mem_read_ready=1,
        mem_read_data=0xABCD,
    )
    assert (fetched.state, fetched.mem_read_valid, fetched.instruction) == (
        isa.FETCHER_FETCHED,
        0,
        0xABCD,
    )
    fetcher.state = fetched.state
    fetcher.mem_read_valid = fetched.mem_read_valid
    fetcher.instruction = fetched.instruction

    idle = fetcher.evaluate(
        reset=False,
        core_state=isa.CORE_DECODE,
        current_pc=7,
        mem_read_ready=0,
        mem_read_data=0,
    )
    assert idle.state == isa.FETCHER_IDLE


def test_fetched_to_idle_on_decode_edge():
    fetcher = Fetcher()
    fetcher.state = isa.FETCHER_FETCHED
    output = fetcher.evaluate(
        reset=False,
        core_state=isa.CORE_DECODE,
        current_pc=0,
        mem_read_ready=0,
        mem_read_data=0,
    )
    assert output.state == isa.FETCHER_IDLE

