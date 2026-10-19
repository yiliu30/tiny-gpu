from tiny_gpu import isa
from tiny_gpu.controller import Controller


def commit(controller, **overrides):
    values = dict(
        reset=False,
        consumer_read_valid=[0] * controller.num_consumers,
        consumer_read_address=[0] * controller.num_consumers,
        consumer_write_valid=[0] * controller.num_consumers,
        consumer_write_address=[0] * controller.num_consumers,
        consumer_write_data=[0] * controller.num_consumers,
        mem_read_ready=[0] * controller.num_channels,
        mem_read_data=[0] * controller.num_channels,
        mem_write_ready=[0] * controller.num_channels,
    )
    values.update(overrides)
    outputs = controller.evaluate(**values)
    controller.commit(outputs)
    return outputs


def test_ascending_read_before_write_and_duplicate_assignment_prevention():
    controller = Controller(num_consumers=4, num_channels=2)
    outputs = commit(
        controller,
        consumer_read_valid=[0, 1, 1, 0],
        consumer_read_address=[0, 11, 12, 0],
        consumer_write_valid=[0, 1, 0, 0],
        consumer_write_address=[0, 21, 0, 0],
        consumer_write_data=[0, 22, 0, 0],
    )
    assert outputs.mem_read_valid == [1, 1]
    assert outputs.mem_read_address == [11, 12]
    assert outputs.mem_write_valid == [0, 0]
    assert outputs.current_consumer == [1, 2]
    assert outputs.serving == 0b110


def test_single_channel_services_one_consumer_at_a_time():
    controller = Controller(num_consumers=8, num_channels=1)
    first = commit(
        controller,
        consumer_read_valid=[1, 1, 0, 0, 0, 0, 0, 0],
        consumer_read_address=[3, 4, 0, 0, 0, 0, 0, 0],
    )
    assert first.mem_read_address == [3]
    second = commit(
        controller,
        consumer_read_valid=[1, 1, 0, 0, 0, 0, 0, 0],
        consumer_read_address=[3, 4, 0, 0, 0, 0, 0, 0],
        mem_read_ready=[1],
        mem_read_data=[30],
    )
    assert second.consumer_read_ready[0] == 1
    assert second.state == [isa.CONTROLLER_READ_RELAYING]


def test_consumer_deassertion_returns_channel_idle_and_clears_ready():
    controller = Controller(num_consumers=2, num_channels=1)
    commit(
        controller,
        consumer_read_valid=[1, 0],
        consumer_read_address=[5, 0],
    )
    commit(
        controller,
        consumer_read_valid=[1, 0],
        consumer_read_address=[5, 0],
        mem_read_ready=[1],
        mem_read_data=[55],
    )
    released = commit(controller, consumer_read_valid=[0, 0], consumer_read_address=[0, 0])
    assert released.state == [isa.CONTROLLER_IDLE]
    assert released.consumer_read_ready == [0, 0]
    assert released.serving == 0


def test_write_request_relay_and_release():
    controller = Controller(num_consumers=2, num_channels=1)
    request = commit(
        controller,
        consumer_write_valid=[0, 1],
        consumer_write_address=[0, 17],
        consumer_write_data=[0, 99],
    )
    assert request.mem_write_valid == [1]
    assert request.mem_write_address == [17]
    assert request.mem_write_data == [99]

    acknowledged = commit(
        controller,
        consumer_write_valid=[0, 1],
        consumer_write_address=[0, 17],
        consumer_write_data=[0, 99],
        mem_write_ready=[1],
    )
    assert acknowledged.consumer_write_ready == [0, 1]
    assert acknowledged.state == [isa.CONTROLLER_WRITE_RELAYING]

    released = commit(controller, consumer_write_valid=[0, 0])
    assert released.consumer_write_ready == [0, 0]
    assert released.serving == 0
    assert released.state == [isa.CONTROLLER_IDLE]


def test_reset_clears_channel_and_ownership_state():
    controller = Controller(num_consumers=2, num_channels=2)
    commit(controller, consumer_read_valid=[1, 1], consumer_read_address=[1, 2])
    outputs = commit(controller, reset=True)
    assert outputs.state == [isa.CONTROLLER_IDLE, isa.CONTROLLER_IDLE]
    assert outputs.serving == 0
    assert outputs.mem_read_valid == [0, 0]

