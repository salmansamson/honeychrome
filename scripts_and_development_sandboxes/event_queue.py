import numpy as np

max_events_in_packet = 100
max_packets_in_queue = 1000
max_events_in_queue = max_events_in_packet * max_packets_in_queue
n_channels = 16
adc_rate = 2.5 # [MHz]
max_event_time = 20 # [us]
n_time_points_in_event = int(adc_rate * max_event_time)
bytes_per_value = 2
event_n_values = n_channels * n_time_points_in_event
event_n_bytes = event_n_values * bytes_per_value
packet_length_in_bytes = max_events_in_packet * event_n_bytes
# e.g. 160000 for 100 events, 16 channels, 20 us --> 50 time points, 2 bytes per value
# e.g. 400000 for 100 events, 16 channels, 50 us --> 125 time points, 2 bytes per value
# e.g. 1600000 for 1000 events, 16 channels, 20 us --> 50 time points, 2 bytes per value

class EventQueue:
    def __init__(self):

        self.queue = np.zeros(max_events_in_queue * event_n_values)
        self.head = 0
        self.tail = 0

    def push(self, n_events_in_packet, blob):

        queue_new_tail = self.tail + n_events_in_packet

        if queue_new_tail <= self.head + max_events_in_queue:
            blob_np = np.frombuffer(blob, dtype=np.uint16)  # bytes_per_sample = 2

            queue_begin_index = self.tail % max_events_in_queue
            queue_end_index = queue_new_tail % max_events_in_queue
            slice_begin = queue_begin_index * event_n_values
            slice_end = queue_end_index * event_n_values
            if queue_end_index >= queue_begin_index:
                self.queue[slice_begin:slice_end] = blob_np
            else:
                # note number of events that didn't fit is queue_end_index
                switch_index = (max_events_in_queue - queue_begin_index) * event_n_values
                self.queue[slice_begin:] = blob_np[:switch_index]  # put first events into back of queue array
                self.queue[:slice_end] = blob_np[switch_index:]  # put last events into front of queue array

            self.tail = queue_new_tail

        else:
            print('Queue full, packet dropped')
            pass

    def pop(self, n_events_in_chunk):
        queue_new_head = self.head + n_events_in_chunk

        if queue_new_head <= self.tail:

            queue_begin_index = self.head % max_events_in_queue
            queue_end_index = queue_new_head % max_events_in_queue
            slice_begin = queue_begin_index * event_n_values
            slice_end = queue_end_index * event_n_values
            if queue_end_index >= queue_begin_index:
                blob_np = self.queue[slice_begin:slice_end]
            else:
                blob_np_back = self.queue[slice_begin:]  # put get back of queue array
                blob_np_front = self.queue[:slice_end]  # get front of queue array
                blob_np = np.vstack((blob_np_back, blob_np_front))

            self.head = queue_new_head
            return blob_np.reshape(n_events_in_chunk, n_channels, n_time_points_in_event)


        else:
            print('Queue empty, nothing returned')
            return np.array([])




if __name__ == "__main__":

    event_queue = EventQueue()
    n_events_in_chunk = 300

    for n in range(5000):
        # get blob
        #n_events_in_packet = max_events_in_packet
        n_events_in_packet = np.random.randint(max_events_in_packet)
        blob = b"\x00" * n_events_in_packet * event_n_bytes
        event_queue.push(n_events_in_packet, blob)
        print([event_queue.head, event_queue.tail, len(blob)])

    for n in range(5000):
        events = event_queue.pop(n_events_in_chunk)
        print([event_queue.head, event_queue.tail, events.shape])
