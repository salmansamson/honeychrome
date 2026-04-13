import ft4222
from ft4222.SPI import Cpha, Cpol
from ft4222.SPIMaster import Mode, Clock, SlaveSelect
from bitarray import bitarray

class Cytkit:
    def __init__(self):
        pass


    def connect_to_instrument(self):
        self.devA = ft4222.openByDescription('FT4222 A')
        # self.devB = ft4222.openByDescription('FT4222 B')
        #self.devA.spiMaster_Init(Mode.QUAD, Clock.DIV_2, Cpol.IDLE_LOW, Cpha.CLK_LEADING, SlaveSelect.SS0) # for registers
        # self.devA.spiMaster_Init(Mode.QUAD, Clock.DIV_2, Cpol.IDLE_LOW, Cpha.CLK_LEADING, SlaveSelect.SS1) # for memory
        self.configure_instrument()
        print('[Instrument driver] Connected')
        return {'source':'[Instrument driver]', 'status':'OK', 'message':'Connected to instrument'}

    def register_select(self):
        # call this every time to write to or read from registers
        self.devA.spiMaster_Init(Mode.QUAD, Clock.DIV_2, Cpol.IDLE_LOW, Cpha.CLK_LEADING, SlaveSelect.SS0) # for registers

    def memory_select(self):
        # call this every time to read from memory
        self.devA.spiMaster_Init(Mode.QUAD, Clock.DIV_2, Cpol.IDLE_LOW, Cpha.CLK_LEADING, SlaveSelect.SS0) # for memory
        # TODO why doesn't SS1 work?

    def configure_instrument(self):
        self.register_select()

        fan_enable = True
        pump_sheath_enable = True
        pump_sample_enable = True
        laser_enable = True
        data_to_write = bitarray([False, False, False, False, fan_enable, pump_sheath_enable, pump_sample_enable, laser_enable]).tobytes()
        byte_string = operation_register + registers_map['ENABLES'].to_bytes(2) + dummy_bytes + data_to_write
        self.devA.spiMaster_MultiReadWrite(0, byte_string, 0)
