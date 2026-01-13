import multiprocessing as mp
from multiprocessing import shared_memory
import time
import random
import numpy as np


class Producer(mp.Process):
    def __init__(self, queue, shm_name, shape, dtype, ready, consumed, finished_first_stage):
        super().__init__()
        self.queue = queue
        self.shm_name = shm_name
        self.shape = shape
        self.dtype = dtype
        self.ready = ready        # Event to signal data ready
        self.consumed = consumed  # Event to signal consumer finished
        self.finished_first_stage = finished_first_stage

    def run(self):
        print(dir())
        # Attach to existing shared memory
        shm = shared_memory.SharedMemory(name=self.shm_name)
        arr = np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)

        for i in range(5):
            self.consumed.wait()   # Wait until consumer is done with old data
            self.consumed.clear()

            # Produce new data in shared memory
            arr[:] = np.random.rand(*self.shape)
            print(f"[Producer] Wrote batch {i}")

            self.ready.set()       # Signal consumer new data is ready
            time.sleep(0.5)

        # Final signal: no more data (write NaNs or similar convention)
        arr[:] = 0
        self.ready.set()
        self.finished_first_stage.set()
        print(f"[Producer] set finished_first_stage event")

        shm.close()

        for i in range(5):
            item = random.randint(1, 100)
            print(f"[Producer] Enqueued {item}")
            self.queue.put(item)
            time.sleep(0.2)  # simulate work

        # Signal consumer to stop
        print(f"[Producer] Enqueued Stop")
        self.queue.put(None)


class Consumer(mp.Process):
    def __init__(self, queue, shm_name, shape, dtype, ready, consumed, finished_first_stage):
        super().__init__()
        self.queue = queue
        self.shm_name = shm_name
        self.shape = shape
        self.dtype = dtype
        self.ready = ready
        self.consumed = consumed
        self.finished_first_stage = finished_first_stage

    def run(self):
        print(dir())
        shm = shared_memory.SharedMemory(name=self.shm_name)
        arr = np.ndarray(self.shape, dtype=self.dtype, buffer=shm.buf)

        while True:
            self.ready.wait()   # Wait for producer signal
            self.ready.clear()

            print(f"[Consumer] mean={arr.mean():.3f}")
            time.sleep(0.3)

            self.consumed.set()  # Let producer overwrite

            if self.finished_first_stage.is_set():
                print(f"[Consumer] found finished_first_stage.is_set")
                break


        shm.close()

        while True:
            item = self.queue.get()
            if item is None:  # termination signal
                print("[Consumer] Done.")
                break
            print(f"[Consumer] Consumed {item}")
            time.sleep(0.3)  # simulate work


if __name__ == "__main__":
    mp.set_start_method("spawn")
    # Shared queue for communication
    q = mp.Queue()

    # create shared memory block
    shape = (1000, 1000)
    dtype = np.uint16

    # Allocate shared memory block
    shm = shared_memory.SharedMemory(create=True, size=np.zeros(shape, dtype=dtype).nbytes)

    # Events for synchronization
    ready = mp.Event()
    consumed = mp.Event()
    finished_first_stage = mp.Event()
    consumed.set()  # consumer initially "ready"

    producer = Producer(q, shm.name, shape, dtype, ready, consumed, finished_first_stage)
    consumer = Consumer(q, shm.name, shape, dtype, ready, consumed, finished_first_stage)

    producer.start()
    consumer.start()

    producer.join()
    consumer.join()

    shm.close()
    shm.unlink()  # Free system resource