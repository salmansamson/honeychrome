from multiprocessing import Process, Pipe
import time

def guard1(conn):
    for round_num in range(3):
        msg_to_send = f"Area A round {round_num+1} is clear ✅"
        print(f"Guard 1 sending: {msg_to_send}")
        conn.send(msg_to_send)

        msg_received = conn.recv()
        print(f"Guard 1 received: {msg_received}")
        time.sleep(5)
    conn.close()

def guard2(conn):
    for round_num in range(3):
        print(f"Guard 2 waiting")
        msg_received = conn.recv()
        print(f"Guard 2 received: {msg_received}")

        msg_to_send = f"Area B round {round_num+1} is clear ✅"
        print(f"Guard 2 sending: {msg_to_send}")
        conn.send(msg_to_send)
        time.sleep(1)
    conn.close()

if __name__ == "__main__":
    conn1, conn2 = Pipe()  # duplex=True by default

    p1 = Process(target=guard1, args=(conn1,))
    p2 = Process(target=guard2, args=(conn2,))

    p1.start()
    p2.start()

    p1.join()
    p2.join()