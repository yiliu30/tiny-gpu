from tiny_gpu.memory import ExternalMemory


def test_reads_precede_writes_in_same_memory_phase():
    memory = ExternalMemory(channels=1)
    memory.load([10])
    response = memory.service(
        read_valid=(1,),
        read_address=(0,),
        write_valid=(1,),
        write_address=(0,),
        write_data=(20,),
    )
    assert response.read_data == (10,)
    assert memory.memory[0] == 20


def test_inactive_channels_return_zero_ready_and_data():
    memory = ExternalMemory(channels=2)
    memory.load([7, 8])
    response = memory.service(read_valid=(1, 0), read_address=(1, 0))
    assert response.read_ready == (1, 0)
    assert response.read_data == (8, 0)
