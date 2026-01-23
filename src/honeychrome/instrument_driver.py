
'''
instrument communicator

Connects to instrument
Configures instrument
Listens for start event
Listens for stop event
Applies cache condition
Sets sample pump rate
Sets sheath pump pressure
Sets gains
Sets laser

test instrument data generator

Shared memory: cache, head, tail, instrument settings
'''

import multiprocessing as mp
from multiprocessing import shared_memory, Lock
import ft4222
from ft4222.SPI import Cpha, Cpol
from ft4222.SPIMaster import Mode, Clock, SlaveSelect
from bitarray import bitarray
import threading
import numpy as np
import time
import warnings

from honeychrome.instrument_configuration import traces_cache_size, dtype, max_events_in_traces_cache, trace_n_points, operation_register, operation_memory, dummy_bytes, memory_start_address, memory_end_address, transfer_target_repeat_time, registers_map

class Instrument(mp.Process):
    def __init__(self, use_dummy_instrument=False,
                 debug=False,
                 traces_cache_name=None,
                 traces_cache_lock=None,
                 index_head_traces_cache=None, index_tail_traces_cache=None,
                 pipe_connection=None):
        super().__init__()
        if use_dummy_instrument:
            self.use_dummy_instrument = True
            self.dummy_memory_head = 0 #only use if dummy
            self.max_events_in_memory_per_pop = 500
            self.dummy_instrument = None
        else:
            self.use_dummy_instrument = False

        self.debug = debug

        self.devA = None
        self.devB = None

        self.configuration = None
        self.pipe_connection = pipe_connection
        self.index_head_traces_cache = index_head_traces_cache
        self.index_tail_traces_cache = index_tail_traces_cache
        self.traces_cache_name = traces_cache_name
        self.traces_cache = None
        self.traces_cache_lock = traces_cache_lock
        self.max_events_in_traces_cache = max_events_in_traces_cache
        self.trace_n_points = trace_n_points
        self.stop_transfer = None
        self.thread = None


    def run(self):
        from honeychrome.controller_components.dummy_instrument import DummyInstrument
        self.dummy_instrument = DummyInstrument()

        # initialise the things that can't be pickled
        self.stop_transfer = threading.Event()
        # initialise transfer thread
        self.thread = threading.Thread(
            target=self.transfer,
            daemon=True
        )

        # Attach to existing shared memory
        shm = shared_memory.SharedMemory(name=self.traces_cache_name)
        with self.traces_cache_lock:
            self.traces_cache = np.ndarray((self.max_events_in_traces_cache * self.trace_n_points), dtype=np.uint16, buffer=shm.buf)

        # main loop waiting for commands from experiment control
        while True:
            try:
                incoming_from_experiment_control = self.pipe_connection.recv()
            except EOFError:
                print("Pipe closed by experiment control; shutting down gracefully.")
                break

            if incoming_from_experiment_control['command'] == 'connect':
                response_to_experiment_control = self.connect_to_instrument()
            elif incoming_from_experiment_control['command'] == 'start':
                response_to_experiment_control = self.start_acquisition()
            elif incoming_from_experiment_control['command'] == 'stop':
                response_to_experiment_control = self.stop_acquisition()
            elif incoming_from_experiment_control['command'] == 'set':
                response_to_experiment_control = self.change_instrument_settings(incoming_from_experiment_control['data'])
            elif incoming_from_experiment_control['command'] == 'quit':
                response_to_experiment_control = {'source':'[Instrument driver]', 'status':'OK', 'message':' Quitting'}
                self.pipe_connection.send(response_to_experiment_control)
                break

            self.pipe_connection.send(response_to_experiment_control)

        while self.thread.is_alive():
            print('[Instrument driver] Waiting until transfer thread ends')
            time.sleep(0.25)

        shm.close()
        print('[Instrument driver] Quit')


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

    def start_acquisition(self):
        # TODO send registers to start pumps etc, initialise data collection in FPGA
        """Start transfer in a separate thread"""
        self.thread = threading.Thread(
            target=self.transfer,
            daemon=True
        )
        self.thread.start()
        print('[Instrument driver] Acquisition started')
        return {'source':'[Instrument driver]', 'status':'OK', 'message':'Acquisition started'}

    def stop_acquisition(self):
        # TODO send registers to stop pumps etc, stop data collection in FPGA
        self.stop_transfer.set()
        return {'source':'[Instrument driver]', 'status':'OK', 'message':'Acquisition ended'}

    def change_instrument_settings(self, data):
        # TODO send registers to set pumps in FPGA etc
        print(data)
        return {'source':'[Instrument driver]', 'status':'OK', 'message':'Instrument configuration changed'}

    def transfer(self):
        while True:
            start_time = time.perf_counter()
            memory_head, memory_tail, n_events_in_memory = self.get_memory_head_tail_n_events()
            if n_events_in_memory > 0:
                if self.use_dummy_instrument:
                    blob_np = self.dummy_instrument.generate_traces(n_events_in_memory)
                else:
                    blob_np = self.pop_from_memory(memory_head, memory_tail)
                if self.debug == True:
                    print(f'[Instrument driver] transferred memory: (head: {memory_head}, tail: {memory_tail}), n_events_in_memory {n_events_in_memory}, blob retrieved {blob_np.shape}')

                self.push_to_traces_cache(n_events_in_memory, blob_np)
            else:
                time.sleep(0.1)

            if self.stop_transfer.is_set():
                self.stop_transfer.clear()
                break

            # Calculate elapsed time and sleep precisely
            elapsed = time.perf_counter() - start_time
            sleep_time = max(0., transfer_target_repeat_time - elapsed)
            time.sleep(sleep_time)


    def get_memory_head_tail_n_events(self):
        if self.use_dummy_instrument:
            # n = self.max_events_in_memory_per_pop
            n = 1000 * transfer_target_repeat_time
            n_events_in_memory = np.random.randint(n)
            memory_head = self.dummy_memory_head
            memory_tail = (memory_head + n_events_in_memory * self.trace_n_points) % memory_end_address
        else:
            self.register_select()

            byte_string_to_write = operation_register + registers_map['MEMHEAD'].to_bytes(2) + dummy_bytes
            byte_string_output = self.devA.spiMaster_MultiReadWrite(0, byte_string_to_write, 4)
            memory_head = int.from_bytes(byte_string_output)

            byte_string_to_write = operation_register + registers_map['MEMTAIL'].to_bytes(2) + dummy_bytes
            byte_string_output = self.devA.spiMaster_MultiReadWrite(0, byte_string_to_write, 4)
            memory_tail = int.from_bytes(byte_string_output)

            byte_string_to_write = operation_register + registers_map['NEVENTS'].to_bytes(2) + dummy_bytes
            byte_string_output = self.devA.spiMaster_MultiReadWrite(0, byte_string_to_write, 4)
            n_events_in_memory = int.from_bytes(byte_string_output)

        return memory_head, memory_tail, n_events_in_memory

    def pop_from_memory(self, memory_head, memory_tail):
        """
        Read out memory starting at memory_head, keep going until memory_tail read, wrap if necessary
        return numpy array blob
        """
        if memory_tail > memory_head:
            blob_np = np.frombuffer(self.read_from_memory(memory_head, memory_tail - memory_head), dtype=np.uint16)
        elif memory_tail < memory_head:
            blob_np = np.concatenate((
                np.frombuffer(self.read_from_memory(memory_head, memory_end_address - memory_head), dtype=np.uint16),
                np.frombuffer(self.read_from_memory(memory_start_address, memory_tail), dtype=np.uint16)
            ))
        if self.use_dummy_instrument:
            self.dummy_memory_head = memory_tail

        return blob_np

    def read_from_memory(self, start_address, total_bytes, chunk_size=65535):
        self.memory_select()

        # read out block of memory in chunks
        data = bytearray(total_bytes)
        bytes_read = 0
        capture_address = start_address
        while bytes_read < total_bytes:
            # Calculate how many bytes to read in this chunk
            remaining = total_bytes - bytes_read
            current_chunk = min(chunk_size, remaining)
            capture_address += current_chunk

            # Write address and read the chunk
            byte_string = operation_memory + capture_address.to_bytes(3) + dummy_bytes
            chunk = self.devA.spiMaster_MultiReadWrite(0, byte_string, current_chunk)
            data.extend(chunk)
            bytes_read += len(chunk)

        return bytes(data)

    def push_to_traces_cache(self, n_traces_from_memory, blob_np):
        with self.index_tail_traces_cache.get_lock():
            tail = self.index_tail_traces_cache.value
        with self.index_head_traces_cache.get_lock():
            head = self.index_head_traces_cache.value

        cache_new_tail = tail + n_traces_from_memory
        if cache_new_tail <= head + self.max_events_in_traces_cache:

            queue_begin_index = tail % self.max_events_in_traces_cache
            queue_end_index = cache_new_tail % self.max_events_in_traces_cache
            slice_begin = queue_begin_index * self.trace_n_points
            slice_end = queue_end_index * self.trace_n_points
            with self.traces_cache_lock:
                if queue_end_index >= queue_begin_index:
                    try:
                        self.traces_cache[slice_begin:slice_end] = blob_np #todo fix: this crashes in long acquisition
                    except ValueError as e:
                        warnings.warn(str(e))
                else:
                    # note number of events that didn't fit is queue_end_index
                    switch_index = (self.max_events_in_traces_cache - queue_begin_index) * self.trace_n_points
                    self.traces_cache[slice_begin:] = blob_np[:switch_index]  # put first events into back of queue array
                    self.traces_cache[:slice_end] = blob_np[switch_index:]  # put last events into front of queue array

            with self.index_tail_traces_cache.get_lock():
                self.index_tail_traces_cache.value = cache_new_tail

            if self.debug == True:
                print(f'[Instrument driver] pushed data to traces cache (head:{head}, tail:{cache_new_tail})')
        else:
            warnings.warn("[Instrument driver] Traces cache is full, data dropped")
            pass



if __name__ == '__main__':
    mp.set_start_method("spawn")

    # Allocate shared memory block, plus head and tail indices
    traces_cache_shm = shared_memory.SharedMemory(create=True, size=np.zeros(traces_cache_size, dtype=dtype).nbytes)
    traces_cache_lock = Lock()
    index_head_traces_cache = mp.Value('i', 0)
    index_tail_traces_cache = mp.Value('i', 0)

    pipe_experiment_instrument_e, pipe_experiment_instrument_i = mp.Pipe()

    # start instrument dummy
    instrument = Instrument(
        use_dummy_instrument=True,
        debug=True,
        traces_cache_name=traces_cache_shm.name,
        traces_cache_lock=traces_cache_lock,
        index_head_traces_cache=index_head_traces_cache,
        index_tail_traces_cache=index_tail_traces_cache,
        pipe_connection=pipe_experiment_instrument_i
    )
    instrument.start()

    pipe_experiment_instrument_e.send({'command':'connect'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    pipe_experiment_instrument_e.send({'command':'start'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    pipe_experiment_instrument_e.send({'command':'set', 'data':'TODO insert settings update here'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    #wait for a bit
    time.sleep(1)

    pipe_experiment_instrument_e.send({'command':'stop'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    #wait for a bit
    time.sleep(3)

    pipe_experiment_instrument_e.send({'command':'quit'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    instrument.join()