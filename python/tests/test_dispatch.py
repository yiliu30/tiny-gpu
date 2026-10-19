from tiny_gpu.dispatch import Dispatch


def advance(dispatch, **overrides):
    values = dict(reset=False, start=1, thread_count=8, core_done=[0, 0])
    values.update(overrides)
    outputs = dispatch.evaluate(**values)
    dispatch.commit(outputs)
    return outputs


def test_ceil_block_count_and_initial_burst_dispatch():
    dispatch = Dispatch()
    outputs = advance(dispatch, thread_count=5)
    assert dispatch.blocks_dispatched == 2
    assert outputs.core_start == [1, 1]
    assert outputs.core_block_id == [0, 1]
    assert outputs.core_thread_count == [4, 1]


def test_core_completion_resets_and_dispatches_next_block():
    dispatch = Dispatch()
    advance(dispatch, thread_count=12)
    assert dispatch.blocks_dispatched == 2
    outputs = advance(dispatch, core_done=[1, 1])
    assert dispatch.blocks_done == 2
    assert outputs.core_reset == [1, 1]
    assert outputs.core_start == [0, 0]

    outputs = advance(dispatch, thread_count=12)
    assert outputs.core_start == [1, 0]
    assert outputs.core_block_id == [2, 1]
    assert dispatch.blocks_dispatched == 3


def test_done_after_all_blocks_finish():
    dispatch = Dispatch()
    advance(dispatch, thread_count=4)
    advance(dispatch, thread_count=4, core_done=[1, 0])
    assert dispatch.done == 0
    advance(dispatch, thread_count=4, core_done=[0, 0])
    assert dispatch.done == 1
