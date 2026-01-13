'''
Trace Analyser:
-Listens for start event
-Consumes cached traces
-Calculates peak height, area, width (according to settings) and adds to events cache
-Copies latest trace with peak measurements
-Signals when new events chunk is ready
'''

import multiprocessing as mp
from multiprocessing import shared_memory, Lock
import threading
import numpy as np
import time
import warnings

from instrument_configuration import traces_cache_size, dtype, max_events_in_traces_cache, trace_n_points, n_channels_trace, adc_rate
from settings import max_events_in_cache, n_channels_per_event, channel_dict, event_channels_pnn, analyser_target_repeat_time

class TraceAnalyser(mp.Process):
    def __init__(self, use_dummy_data=False,
                 traces_cache_name=None,
                 traces_cache_lock=None,
                 index_head_traces_cache=None,
                 index_tail_traces_cache=None,
                 events_cache_name=None,
                 events_cache_lock=None,
                 index_head_events_cache=None,
                 index_tail_events_cache=None,
                 oscilloscope_traces_queue=None,
                 pipe_connection=None):
        super().__init__()
        if use_dummy_data:
            self.use_dummy_data = True
            self.dummy_data_source = 0
        else:
            self.use_dummy_data = False

        # pipe connection
        self.pipe_connection = pipe_connection

        # Traces cache
        self.traces_cache = None
        self.traces_cache_name = traces_cache_name
        self.traces_cache_lock = traces_cache_lock
        self.max_events_in_traces_cache = max_events_in_traces_cache
        self.trace_n_points = trace_n_points
        self.n_channels_trace = n_channels_trace
        self.n_time_points_in_event = int(trace_n_points//n_channels_trace)

        # Events cache
        self.events_cache = None
        self.events_cache_name = events_cache_name
        self.events_cache_lock = events_cache_lock
        self.max_events_in_cache = max_events_in_cache
        self.index_head_traces_cache = index_head_traces_cache
        self.index_tail_traces_cache = index_tail_traces_cache
        self.index_head_events_cache = index_head_events_cache
        self.index_tail_events_cache = index_tail_events_cache

        self.channel_dict = channel_dict
        self.adc_rate = adc_rate
        self.indices_area_channels_in_traces = None
        self.indices_height_channels_in_traces = None
        self.indices_width_channel_in_traces = None
        self.index_time_channel_in_events = None
        self.index_event_id_in_events = None
        self.index_width_channel_in_events = None
        self.indices_area_channels_in_events = None
        self.indices_height_channels_in_events = None
        self.n_channels_per_event = None
        self.set_channels()

        # Oscilloscope traces queue
        self.oscilloscope_traces_queue = oscilloscope_traces_queue


    def run(self):
        # initialise the things that can't be pickled
        self.stop_analyser = threading.Event()

        # Attach to existing shared memory
        shm_traces = shared_memory.SharedMemory(name=self.traces_cache_name)
        with self.traces_cache_lock:
            self.traces_cache = np.ndarray((self.max_events_in_traces_cache * self.trace_n_points), dtype=np.uint16, buffer=shm_traces.buf)
        shm_events = shared_memory.SharedMemory(name=self.events_cache_name)
        with self.events_cache_lock:
            self.events_cache = np.ndarray((self.max_events_in_cache, self.n_channels_per_event), dtype=np.int64, buffer=shm_events.buf)

        # create analysis thread
        thread = threading.Thread(
            target=self.analyse,
            daemon=True
        )

        # main loop waiting for commands from experiment control
        while True:
            try:
                incoming_from_experiment_control = self.pipe_connection.recv()
            except EOFError:
                print("Pipe closed by experiment control; shutting down gracefully.")
                break

            if incoming_from_experiment_control['command'] == 'start':
                # reset events cache to zeros
                with self.events_cache_lock:
                    self.events_cache[:] = 0
                with self.index_head_events_cache.get_lock():
                    self.index_head_events_cache.value = 0
                with self.index_tail_events_cache.get_lock():
                    self.index_tail_events_cache.value = 0
                print('[Trace Analyser] Events cache flushed!')
                self.set_channels()
                while thread.is_alive():
                    print('[Trace Analyser] Waiting until previous analysis thread ends')
                    time.sleep(0.25)
                # create analysis thread
                thread = threading.Thread(
                    target=self.analyse,
                    daemon=True
                )
                thread.start()
                print('[Trace Analyser] Started')
                response_to_experiment_control = {'status': 'OK', 'message': '[Trace Analyser] started'}

            elif incoming_from_experiment_control['command'] == 'stop':
                self.stop_analyser.set()
                while thread.is_alive():
                    print('[Trace Analyser] Waiting until analysis thread ends')
                    time.sleep(0.25)
                response_to_experiment_control = {'status':'OK', 'message':'[Trace Analyser] stopped'}

            elif incoming_from_experiment_control['command'] == 'set_channels':
                self.channel_dict = incoming_from_experiment_control['data']
                self.stop_analyser.set()
                while thread.is_alive():
                    print('[Trace Analyser] Waiting until analysis thread ends')
                    time.sleep(0.25)
                self.set_channels()
                print('[Trace Analyser] Channel configuration set')
                response_to_experiment_control = {'status':'OK', 'message':'[Trace Analyser] channel configuration set'}

            elif incoming_from_experiment_control['command'] == 'quit':
                self.stop_analyser.set()
                while thread.is_alive():
                    print('[Trace Analyser] Waiting until analysis thread ends')
                    time.sleep(0.25)
                response_to_experiment_control = {'status':'OK', 'message':'[Trace Analyser] quitting'}
                self.pipe_connection.send(response_to_experiment_control)
                break

            self.pipe_connection.send(response_to_experiment_control)

        shm_traces.close()
        shm_events.close()
        print('[Trace Analyser] Quit')


    def set_channels(self):
        adc_channels, trigger_channel, area_channels, height_channels, width_channels, scatter_channels, fluorescence_channels, event_channels_pnn, n_channels_per_event = self.channel_dict.values()

        self.indices_area_channels_in_traces = [(True if c in area_channels else False) for c in adc_channels]
        self.indices_height_channels_in_traces = [(True if c in height_channels else False) for c in adc_channels]
        self.indices_width_channel_in_traces = adc_channels.index(trigger_channel)
        self.index_time_channel_in_events = event_channels_pnn.index('Time')
        self.index_event_id_in_events = event_channels_pnn.index('event_id')
        self.index_width_channel_in_events = event_channels_pnn.index(trigger_channel + '-W')
        self.indices_area_channels_in_events = [event_channels_pnn.index(c + '-A') for c in area_channels]
        self.indices_height_channels_in_events = [event_channels_pnn.index(c + '-H') for c in height_channels]
        self.n_channels_per_event = n_channels_per_event

    def analyse(self):
        start_time  = time.perf_counter()
        while True:
            cycle_start_time = time.perf_counter()

            '''
            input cached traces
            for all new events, calculate area, height, width as specified in channel_dict, add all channels to events array as specified
            '''
            with self.index_head_traces_cache.get_lock():
                traces_head = self.index_head_traces_cache.value
            with self.index_tail_traces_cache.get_lock():
                traces_tail = self.index_tail_traces_cache.value

            with self.index_head_events_cache.get_lock():
                events_head = self.index_head_events_cache.value # not used - events cache is not cycled
            with self.index_tail_events_cache.get_lock():
                events_tail = self.index_tail_events_cache.value

            n_new_events = traces_tail - traces_head
            if traces_head < traces_tail:
                queue_begin_index = traces_head % self.max_events_in_traces_cache
                queue_end_index = traces_tail % self.max_events_in_traces_cache
                slice_begin = queue_begin_index * self.trace_n_points
                slice_end = queue_end_index * self.trace_n_points
                with self.traces_cache_lock:
                    if queue_end_index > queue_begin_index:
                        blob_np = self.traces_cache[slice_begin:slice_end]
                    else:
                        blob_np_back = self.traces_cache[slice_begin:]  # put get back of queue array
                        blob_np_front = self.traces_cache[:slice_end]  # get front of queue array
                        blob_np = np.concatenate((blob_np_back, blob_np_front))

                blob_reshaped = blob_np.reshape(-1, self.n_channels_trace, self.n_time_points_in_event)

                # calculate area, height, width as defined in channel_dict and write to events_cache
                areas = blob_reshaped[:, self.indices_area_channels_in_traces, :].sum(axis=2)
                heights = blob_reshaped[:, self.indices_height_channels_in_traces, :].max(axis=2)
                widths = self.calculate_width(blob_reshaped[:, self.indices_width_channel_in_traces, :])
                times = np.ones(n_new_events, dtype=np.int64) * int((time.perf_counter() - start_time) * 1000)
                event_ids = np.array(range(events_tail, events_tail + n_new_events))
                with self.events_cache_lock:
                    self.events_cache[events_tail:events_tail + n_new_events, self.indices_area_channels_in_events] = areas
                    self.events_cache[events_tail:events_tail + n_new_events, self.indices_height_channels_in_events] = heights
                    self.events_cache[events_tail:events_tail + n_new_events, self.index_width_channel_in_events] = widths
                    self.events_cache[events_tail:events_tail + n_new_events, self.index_time_channel_in_events] = times
                    self.events_cache[events_tail:events_tail + n_new_events, self.index_event_id_in_events] = event_ids

                    ### debug print latest events
                    #print(self.events_cache[events_tail:events_tail + n_new_events])

                #update head of traces cache and tail of events cache
                events_tail += n_new_events
                print(f'[Trace Analyser] analysed {n_new_events} events (traces cache old head:{traces_head}, new head and tail:{traces_tail}), (events cache head:{events_head}, tail:{events_tail})')
                traces_head = traces_tail

                with self.index_head_traces_cache.get_lock():
                    self.index_head_traces_cache.value = traces_head
                with self.index_tail_events_cache.get_lock():
                    self.index_tail_events_cache.value = events_tail

                last_event_traces = blob_reshaped[-1, :, :]
                self.oscilloscope_traces_queue.put({'event_id':event_ids[-1], 'time':times[-1], 'traces':last_event_traces})

            else:
                print(f'[Trace Analyser] awaiting traces (traces cache head:{traces_head}, tail:{traces_tail})')

            # stop if stop analyser event is set
            if self.stop_analyser.is_set():
                break
            # stop if events cache full
            if events_tail + n_new_events > self.max_events_in_cache:
                warnings.warn("[Trace Analyser] Events cache is full, stopping trace analyser")
                break

            # Calculate elapsed time and sleep precisely
            elapsed = time.perf_counter() - cycle_start_time
            #print(f'[Trace Analyser] analysis elapsed time {elapsed}') # for debugging
            sleep_time = max(0, analyser_target_repeat_time - elapsed)
            time.sleep(sleep_time)

        self.stop_analyser.clear()
        print('[Trace Analyser] Stopped')

    def calculate_width(self, traces):
        n_traces, n_time_points = traces.shape
        widths = np.zeros(n_traces)
        for n in range(n_traces):
            half_height = traces[n].max() * 0.5
            rising = np.argmax(traces[n] > half_height)
            falling = rising + np.argmin(traces[n][rising:] > half_height)
            widths[n] = falling - rising

        widths *= int(self.adc_rate * 1000) # nanoseconds
        return widths

if __name__ == '__main__':
    mp.set_start_method("spawn")

    # Allocate shared memory block, plus head and tail indices
    traces_cache_shm = shared_memory.SharedMemory(create=True, size=np.zeros(traces_cache_size, dtype=dtype).nbytes)
    traces_cache_lock = Lock()
    index_head_traces_cache = mp.Value('i', 0)
    index_tail_traces_cache = mp.Value('i', 0)

    events_cache_shm = shared_memory.SharedMemory(create=True, size=np.zeros((max_events_in_cache, n_channels_per_event), dtype=np.int64).nbytes)
    events_cache_lock = Lock()
    index_head_events_cache = mp.Value('i', 0)
    index_tail_events_cache = mp.Value('i', 0)

    # oscilloscope traces
    oscilloscope_traces_queue = mp.Queue()
    # command pipes
    pipe_experiment_instrument_e, pipe_experiment_instrument_i = mp.Pipe()
    pipe_experiment_analyser_e, pipe_experiment_analyser_a = mp.Pipe()

    '''
    Firstly, set up instrument
    '''
    # start instrument dummy
    from instrument_driver import Instrument
    instrument = Instrument(
        use_dummy_instrument=True,
        traces_cache_name=traces_cache_shm.name,
        traces_cache_lock=traces_cache_lock,
        index_head_traces_cache=index_head_traces_cache,
        index_tail_traces_cache=index_tail_traces_cache,
        pipe_connection=pipe_experiment_instrument_i
    )
    instrument.start()

    '''
    Secondly, set up analyst
    '''
    trace_analyser = TraceAnalyser(
        traces_cache_name=traces_cache_shm.name,
        traces_cache_lock=traces_cache_lock,
        index_head_traces_cache=index_head_traces_cache,
        index_tail_traces_cache=index_tail_traces_cache,
        events_cache_name=events_cache_shm.name,
        events_cache_lock=events_cache_lock,
        index_head_events_cache=index_head_events_cache,
        index_tail_events_cache=index_tail_events_cache,
        oscilloscope_traces_queue=oscilloscope_traces_queue,
        pipe_connection=pipe_experiment_analyser_a
    )
    trace_analyser.start()


    '''
    Thirdly, send commands and read data
    
    connect instrument
    start instrument
    start analyser
    stop analyser
    set channels
    start analyser again
    stop instrument
    stop analyser
    quit analyser
    quit instrument
    '''
    # connect instrument
    pipe_experiment_instrument_e.send({'command':'connect'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    # start instrument
    pipe_experiment_instrument_e.send({'command':'start'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    # start analyser
    pipe_experiment_analyser_e.send({'command':'start'})
    response = pipe_experiment_analyser_e.recv()
    print(response)


    #wait for a bit
    time.sleep(1)

    # #stop analyser
    # pipe_experiment_analyser_e.send({'command':'stop'})
    # response = pipe_experiment_analyser_e.recv()
    # print(response)
    #
    # #set channels
    # pipe_experiment_analyser_e.send({'command':'set_channels', 'data':channel_dict})
    # response = pipe_experiment_analyser_e.recv()
    # print(response)
    #
    # # wait for a bit
    # time.sleep(1)
    #
    # # start analyser again
    # pipe_experiment_analyser_e.send({'command':'start'})
    # response = pipe_experiment_analyser_e.recv()
    # print(response)
    #
    # # wait for a bit
    # time.sleep(1)

    #stop instrument
    pipe_experiment_instrument_e.send({'command':'stop'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    #stop analyser
    pipe_experiment_analyser_e.send({'command':'stop'})
    response = pipe_experiment_analyser_e.recv()
    print(response)

    #quit analyser
    pipe_experiment_analyser_e.send({'command':'quit'})
    response = pipe_experiment_analyser_e.recv()
    print(response)

    #quit instrument
    pipe_experiment_instrument_e.send({'command':'quit'})
    response = pipe_experiment_instrument_e.recv()
    print(response)

    trace_analyser.join()
    instrument.join()

    # inspect event data output
    import pandas as pd
    shm_events = shared_memory.SharedMemory(name=events_cache_shm.name)
    with events_cache_lock:
        events_cache = np.ndarray((max_events_in_cache, n_channels_per_event), dtype=np.int64, buffer=shm_events.buf)
    with index_head_events_cache.get_lock():
        events_head = index_head_events_cache.value  # not used - events cache is not cycled
    with index_tail_events_cache.get_lock():
        events_tail = index_tail_events_cache.value
    print([events_head, events_tail])
    with events_cache_lock:
        events_df = pd.DataFrame(data=events_cache[events_head:events_tail], columns=event_channels_pnn)
        print(events_df.head(5))
        #events_df.to_csv('/home/ssr/Downloads/events.csv', index=False)

    traces_cache_shm.close()
    events_cache_shm.close()
    traces_cache_shm.unlink()
    events_cache_shm.unlink()