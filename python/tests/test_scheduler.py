from tiny_gpu import isa
from tiny_gpu.scheduler import Scheduler


def evaluate(scheduler, **overrides):
    values = dict(
        reset=False,
        start=0,
        decoded_mem_read_enable=0,
        decoded_mem_write_enable=0,
        decoded_ret=0,
        fetcher_state=isa.FETCHER_IDLE,
        lsu_state=[isa.LSU_IDLE] * 4,
        next_pc=[0, 0, 0, 17],
    )
    values.update(overrides)
    return scheduler.evaluate(**values)


def test_stage_sequence_and_ret():
    scheduler = Scheduler()
    scheduler.core_state = evaluate(scheduler, start=1).core_state
    assert scheduler.core_state == isa.CORE_FETCH
    scheduler.core_state = evaluate(scheduler, fetcher_state=isa.FETCHER_FETCHED).core_state
    assert scheduler.core_state == isa.CORE_DECODE
    scheduler.core_state = evaluate(scheduler).core_state
    assert scheduler.core_state == isa.CORE_REQUEST
    scheduler.core_state = evaluate(scheduler).core_state
    assert scheduler.core_state == isa.CORE_WAIT
    scheduler.core_state = evaluate(scheduler).core_state
    assert scheduler.core_state == isa.CORE_EXECUTE
    scheduler.core_state = evaluate(scheduler).core_state
    assert scheduler.core_state == isa.CORE_UPDATE
    done = evaluate(scheduler, decoded_ret=1)
    assert (done.core_state, done.done) == (isa.CORE_DONE, 1)


def test_wait_blocks_while_any_lane_memory_operation_is_active():
    scheduler = Scheduler()
    scheduler.core_state = isa.CORE_WAIT
    assert evaluate(scheduler, lsu_state=[1, 0, 0, 0]).core_state == isa.CORE_WAIT
    assert evaluate(scheduler, lsu_state=[0, 2, 0, 0]).core_state == isa.CORE_WAIT
    assert evaluate(scheduler, lsu_state=[0, 0, 3, 0]).core_state == isa.CORE_EXECUTE


def test_update_uses_last_lane_next_pc_even_if_lane_is_inactive():
    scheduler = Scheduler()
    scheduler.core_state = isa.CORE_UPDATE
    output = evaluate(scheduler, next_pc=[40, 41, 42, 43])
    assert output.current_pc == 43
