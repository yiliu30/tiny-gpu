from tiny_gpu.dcr import Dcr


def test_dcr_write_and_hold():
    dcr = Dcr()
    dcr.clock(reset=False, write_enable=1, data=8)
    assert dcr.value == 8
    dcr.clock(reset=False, write_enable=0, data=3)
    assert dcr.value == 8


def test_dcr_reset_wins():
    dcr = Dcr()
    dcr.value = 8
    dcr.clock(reset=True, write_enable=1, data=3)
    assert dcr.value == 0

